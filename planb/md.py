import logging

from planb.utils import is_block, run_cmd


def get_md_info(udev_ctx):
    """
    Capture info on the md devices, and the devices associated with it.

    Args:
        udev_ctx (obj): The udev ctx to use for querying.

    Returns:
        md_info (dict): MD device information.
    """
    from os import listdir

    md_info = dict()

    # Loop through disk pulled from udev.
    for d in udev_ctx.list_devices(subsystem='block', DEVTYPE='disk'):
        if "/dev/disk/by-id/md-uuid" not in d.get('DEVLINKS', ''):
            continue

        devs = []
        info = dict()

        # Set the name based off udev.
        name = d.get('MD_DEVNAME', '')
        if not name:
            name = d.device_node.split('/')[-1]

        # Grab the slave device symlink names.
        for dev in listdir(f"/sys/block/{d.device_node.split('/')[-1]}/slaves/"):
            devs.append(dev)

        # For some reason the listdir reverses the dev order, so sort it.
        devs.sort()

        # Grab the devs, raid level, metadata version, and uuid.
        info.update({"devs": devs, "md_level": d.get('MD_LEVEL'), "md_metadata": d.get('MD_METADATA'),
                     "md_uuid": d.get('MD_UUID')})

        md_info.update({name: info})

    return md_info


def md_check(udev_ctx, bk_md_info):
    """
    Check if the md layout matches the backup's layout, if not fix.

    Args:
        udev_ctx (obj): The udev ctx to use for querying.
        bk_md_info (dict): The loaded backup md_info output.
    """
    from glob import glob
    from re import search

    logger = logging.getLogger('pbr')

    # Run assemble in case disk had to be recovered earlier.
    ret = run_cmd(['/usr/sbin/mdadm', '-v', '--assemble', '--scan'], ret=True)
    if ret.returncode and not ret.returncode == 2:
        logger.warning(f" The command {ret.args} returned in error, stderr: {ret.stderr.decode()}")

    logger.debug(f"bk_md_info: {bk_md_info}")

    # Grab an updated md_info, in case reading the partitions was only needed.
    facts_md_info = get_md_info(udev_ctx)

    if set(bk_md_info.keys()) == set(facts_md_info.keys()):
        for name, info in bk_md_info.items():
            devs1 = set(info.get('devs', ''))
            devs2 = set(facts_md_info[name].get('devs', ''))

            # Check the lens of the devs, if they don't match, then a dev
            # is missing, so we need to re-add it.
            if not len(devs1) == len(devs2):
                logger.debug(f"md: md_check: dev1.difference:{devs1.difference(devs2)}")
                logger.info("Re-adding disk to md raid")
                for d in devs1.difference(devs2):
                    md_re_add(name, d)

    else:
        # If the keys don't match, that means either the md device isn't available,
        # so it will need to be recreated.
        diff = set(bk_md_info.keys()).difference(set(facts_md_info.keys()))
        logger.debug(f"md:md_check: diff:{diff}")

        if diff:
            # Stop any mdraids before trying to recreate.
            globs = glob("/dev/md*")
            if globs:
                cmd = ['/usr/sbin/mdadm', '-v', '--stop']
                for d in globs:
                    if is_block(d):
                        cmd.append(d)

                run_cmd(cmd)

            logger.info("Re-creating md raids")
            for x in diff:
                level = search("([0-9]+)", bk_md_info[x]['md_level']).group()
                meta = bk_md_info[x]['md_metadata']
                uuid = bk_md_info[x]['md_uuid']
                devs = bk_md_info[x]['devs']

                md_create(x, level, meta, len(devs), uuid, devs)


def md_create(name, level, meta, num, uuid, devs):
    """
    Create a new md raid array.

    Args:
        name (str): md_devname
        level (str): The raid level to use.
        meta (str): The metadata version to use.
        num (str): How many devices are in the array.
        uuid (str): The uuid to use when creating the array.
        devs (list): The device names to use in the array.
    """
    from os.path import exists

    # Set the create command, and zero the superblocks.
    cmd = ['mdadm', '-v', '--create', '-R', f"/dev/md/{name}", f"--metadata={meta}", f"--level={level}",
           f"--raid-devices={num}", f"--uuid={uuid}", '--force']
    for d in devs:
        if exists(d):
            run_cmd(['/usr/sbin/mdadm', '-v', '--zero-superblock', '--force', f"/dev/{d}"])

        cmd.append(f"/dev/{d}")

    logging.getLogger('pbr').info(f"  Creating the /dev/md/{name} array")
    run_cmd(cmd)


def md_re_add(name, dev):
    """
    Attempt to re-add the device, if not successfully, just add it.

    Args:
        name (str): MD device name.
        dev (str): Device to add to the array.
    """
    logger = logging.getLogger('pbr')

    logger.info(f"  Re-adding /dev/{dev} to the /dev/md/{name} array")
    ret = run_cmd(['/usr/sbin/mdadm', '-v', '--manage', f"/dev/md/{name}", '--re-add', f"/dev/{dev}"], ret=True)
    if ret.returncode:
        logger.debug(f" {ret.args} returned in error attempting to just add instead: {ret.stderr.decode()}")
        run_cmd(['/usr/sbin/mdadm', '-v', '--manage', f"/dev/md/{name}", '--add', f"/dev/{dev}"])
