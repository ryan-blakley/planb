import logging

from planb.exceptions import ExistsError, GeneralError, RunCMDError
from planb.utils import dev_from_file, get_dev_type, run_cmd


def fmt_fs(dev, fs_uuid, fs_label, fs_type):
    """
    Creates a filesystem on the device specified.

    Args:
        dev (str): Device to format.
        fs_uuid (str): The uuid to set when formatting.
        fs_label (str): The label to set when formatting.
        fs_type (str): The type of filesystem to format the device.
    """
    from os.path import exists
    from re import search

    logger = logging.getLogger('pbr')

    # Check to make sure the path is actually device before continuing.
    if not exists(dev):
        logger.error(f"ERROR: Can't format {dev}, because it isn't a valid device.")
        raise ExistsError()

    logger.info(f"  Formatting {dev} as {fs_type}")

    # Format the devs with the uuid and label if there was one.
    if fs_type == "swap":
        # Check to make sure fs_label isn't None.
        if fs_label:
            cmd = ['/usr/sbin/mkswap', '-U', fs_uuid, '-L', fs_label, dev]
        else:
            cmd = ['/usr/sbin/mkswap', '-U', fs_uuid, dev]

    elif fs_type == "xfs":
        # Check to make sure fs_label isn't None.
        if fs_label:
            cmd = ['/usr/sbin/mkfs.xfs', '-f', '-L', fs_label, '-m', f"uuid={fs_uuid}", dev]
        else:
            cmd = ['/usr/sbin/mkfs.xfs', '-f', '-m', f"uuid={fs_uuid}", dev]

    elif fs_type == "vfat":
        if search("-", fs_uuid):
            uuid = "".join(fs_uuid.split('-'))
        else:
            uuid = fs_uuid

        # Check to make sure fs_label isn't None.
        if fs_label:
            cmd = ['/usr/sbin/mkfs.fat', '-F', '16', '-i', uuid, '-n', fs_label, dev]
        else:
            cmd = ['/usr/sbin/mkfs.fat', '-F', '16', '-i', uuid, dev]

    elif "ext" in fs_type:
        # Check to make sure fs_label isn't None.
        if fs_label:
            cmd = [f"/usr/sbin/mkfs.{fs_type}", '-U', fs_uuid, '-L', fs_label, dev]
        else:
            cmd = [f"/usr/sbin/mkfs.{fs_type}", '-U', fs_uuid, dev]
    else:
        cmd = None

    if cmd:
        ret = run_cmd(cmd, ret=True)

        if ret.returncode:
            stderr = ret.stderr.decode()
            if "is mounted" in stderr:
                logger.error(f" {ret.args} returned in error due to {dev} being mounted. "
                             "Please unmount everything and try again.")
            else:
                logger.error(f" The command {ret.args} returned in error: {ret.stderr.decode()}")

            raise RunCMDError()
    else:
        logger.error(f"Unsupported filesystem {fs_type}, exiting.")
        raise GeneralError()


def get_mnts(udev_ctx):
    """
    Query and store information about anything that's mounted.

    Args:
        udev_ctx (obj): Udev context obj.
    """
    from glob import glob

    mnts = dict()

    def add_entries(dev, mp):
        """
        Add mnt point entries.

        Args:
            dev (str): Device name.
            mp (str): Mount point.
        """
        info = dict()
        vg = None
        parent = None
        md_devname = None

        # If the dev is a zram device, skip adding it.
        if dev.startswith("/dev/zram"):
            return

        udev_info = dev_from_file(udev_ctx, dev)

        if dev.startswith("/dev/dm-"):
            dev = f"/dev/mapper/{udev_info['DM_NAME']}"

        d_type = get_dev_type(udev_info)

        if d_type == "lvm":
            vg = udev_info.get('DM_VG_NAME', '')
            if udev_info.get('MD_DEVNAME', False):
                md_devname = f"/dev/md/{udev_info.get('MD_DEVNAME', None)}"
        elif d_type == "part" or d_type == "part-raid":
            parent = udev_info.find_parent('block').device_node
        elif d_type == "part-mpath":
            parent = f"/dev/mapper/{udev_info['DM_MPATH']}"
        elif d_type == "raid":
            if udev_info['DEVTYPE'] == "partition":
                parent = udev_info.find_parent('block').device_node
            else:
                md_devname = f"/dev/md/{udev_info.get('MD_DEVNAME', None)}"
        # For luks devices that are on lvm, we need to grab the vg name.
        elif d_type == "crypt":
            # If a slave device exist, and it is a dm device, grab the vg name.
            if glob(f"/sys/block/{udev_info['DEVNAME'].split('/')[-1]}/slaves/*/dm/name"):
                dm_parent = glob(f"/sys/block/{udev_info['DEVNAME'].split('/')[-1]}/slaves/*")[0].split('/')[-1]
                vg = dev_from_file(udev_ctx, f"/dev/{dm_parent}").get('DM_VG_NAME', '')
            # Else grab the slave device name and set the parent to it.
            else:
                dm_parent = glob(f"/sys/block/{udev_info['DEVNAME'].split('/')[-1]}/slaves/*")[0].split('/')[-1]
                parent = f"/dev/{dm_parent}"

        info.update({"path": dev,
                     "kname": udev_info['DEVNAME'],
                     "fs_type": udev_info.get('ID_FS_TYPE', None),
                     "fs_uuid": udev_info.get('ID_FS_UUID', None),
                     "fs_label": udev_info.get('ID_FS_LABEL', None),
                     "type": d_type,
                     "vg": vg,
                     "parent": parent,
                     "md_devname": md_devname})

        mnts.update({mp: info})

    def read_strip_filter(_file):
        with open(_file, "r") as f:
            lines = f.readlines()

        lines = [line.strip() for line in lines]
        return [line for line in lines if line.startswith("/") and not line.startswith("//")]

    for x in read_strip_filter("/proc/mounts"):
        split = x.split()
        add_entries(split[0], split[1])

    loop = 0
    for x in read_strip_filter("/proc/swaps"):
        # To distinguish from actual mount points, name the entries SWAP-X,
        # this is in case there are multiple swap devices in use.
        add_entries(x.split()[0], f"SWAP-{loop}")
        loop += 1

    return mnts
