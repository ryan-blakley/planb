def dev_from_file(udev_ctx, dev):
    """
    Queries udev based on the device path, this is, so I don't have to import pyudev everywhere,
    and it shortens the call.

    Args:
        udev_ctx (obj): Pass in the udev_ctx to use.
        dev (str): The device file path ex. /dev/sda.

    Returns:
        (obj): Udev device object.
    """
    from pyudev.device import Devices
    return Devices.from_device_file(udev_ctx, dev)


def dev_from_name(udev_ctx, name):
    """
    Queries udev based on the device name, this is, so I don't have to import pyudev everywhere,
    and it shortens the call.

    Args:
        udev_ctx (obj): Pass in the udev_ctx to use.
        name (str): Device name ex. sda1

    Returns:
        (obj): Udev device object
    """
    from pyudev.device import Devices
    return Devices.from_name(udev_ctx, 'block', name)


def get_dev_type(udev_info):
    """
    Queries the udev object, and returns the device type.

    Args:
        udev_info (obj): Pass in the udev_ctx to use.

    Returns:
        (obj): Device type in str format.
    """
    d_type = None
    if udev_info.get('DM_UUID', False):
        dm_uuid = udev_info['DM_UUID']
        if dm_uuid.startswith("LVM"):
            d_type = "lvm"
        elif dm_uuid.startswith("mpath"):
            d_type = "mpath"
        elif dm_uuid.startswith("part"):
            if "mpath" in dm_uuid:
                d_type = "part-mpath"
        elif dm_uuid.startswith("CRYPT-LUKS"):
            d_type = "crypt"
    elif udev_info.get('MD_LEVEL', False):
        if udev_info.get('PARTN', False):
            d_type = "part-raid"
        else:
            d_type = "raid"
    elif udev_info['DEVTYPE'] == "partition":
        d_type = "part"
    elif udev_info['DEVTYPE'] == "disk":
        d_type = "disk"

    return d_type


def get_modules():
    """
    Parse /proc/modules.

    Returns:
        modules (list): All loaded modules.
    """
    with open("/proc/modules", "r") as f:
        lines = f.readlines()
        # Strip new lines.
        lines = [x.strip() for x in lines]
        # Split on spaces, return first column.
        modules = [x.split()[0] for x in lines]
    return modules


def is_block(dev):
    """
    Check if the device path exist and is a block device.

    Args:
        dev (str): Device path to check.

    Returns:
        (bool): Whether the device is a block device or not.
    """
    from os import stat
    from os.path import exists
    from stat import S_ISBLK

    if exists(dev) and S_ISBLK(stat(dev).st_mode):
        return True
    else:
        return False


def is_installed(pkg):
    """
    Checks if the pkg is installed or not.

    Args:
        pkg (str): Pkg name

    Returns:
        (bool): Whether the pkg is installed or not.
    """
    from os.path import exists

    if exists("/usr/bin/rpm"):
        from rpm import RPMTAG_NAME, TransactionSet

        ts = TransactionSet()

        if ts.dbMatch(RPMTAG_NAME, pkg):
            return True
        else:
            return False


def pkg_files(pkg):
    """
    Query all files in a given pkg.

    Args:
        pkg (str): Pkg name.

    Returns:
        (list): The files in the pkg.
    """
    from os.path import exists

    if exists("/usr/bin/rpm"):
        from rpm import RPMTAG_NAME, files, TransactionSet

        ts = TransactionSet()
        for h in ts.dbMatch(RPMTAG_NAME, pkg):
            return files(h)


def pkg_query_file(file_name):
    """
    Query which pkg a file belongs to.

    Args:
        file_name (str): The file name.

    Returns:
        (str): Pkg name.
    """
    from os.path import exists

    if exists("/usr/bin/rpm"):
        from rpm import RPMTAG_BASENAMES, TransactionSet

        ts = TransactionSet()
        for h in ts.dbMatch(RPMTAG_BASENAMES, file_name):
            return h['name']


def mk_cdboot(kernel, initrd, parmfile, outfile):
    """
    Create the cdboot.img file needed for s390 to boot. I based this off of
    https://github.com/weldr/lorax/blob/master/src/bin/mk-s390-cdboot just
    slimmed it down a bit, instead of having it as an external script.

    Args:
        kernel (str): The vmlinuz file.
        initrd (str): The initrd file.
        parmfile (str): The parmfile normally cdboot.prm
        outfile (str): The outputted file.
    """
    from os import stat
    from shutil import copy2
    from struct import pack

    copy2(kernel, outfile)

    with open(initrd, "rb") as initrd_fd:
        with open(outfile, "r+b") as out_fd:
            out_fd.seek(0x0000000000800000)
            out_fd.write(initrd_fd.read())

    size = stat(initrd).st_size

    with open(outfile, "r+b") as out_fd:
        out_fd.seek(0x04)
        out_fd.write(pack(">L", 0x80010000))

        # Write the initrd start and size
        out_fd.seek(0x10408)
        out_fd.write(pack(">Q", 0x0000000000800000))
        out_fd.seek(0x10410)
        out_fd.write(pack(">Q", size))

        # Erase the previous COMMAND_LINE, write zeros
        out_fd.seek(0x10480)
        out_fd.write(bytes(896))

        # Write the first line of the parmfile
        cmdline = open(parmfile, "r").readline().strip()
        out_fd.seek(0x10480)
        out_fd.write(bytes(cmdline, "utf-8"))


def not_in_append(dev, array):
    """
    Check if dev is in the array, if not append to the array.

    Args:
        dev (str): String to check if it's in the array.
        array (list): List to check against.
    """
    if dev not in array:
        array.append(dev)


def rand_str(length, hexa):
    """
    Return a random string, used for uuid generation when needed.

    Args:
        length (int): Length of string to return.
        hexa (bool): Bool if hexa, return only hexadecimals.

    Returns:
        (str): Random generated string.
    """
    import random
    import string

    if not hexa:
        letters = string.ascii_uppercase + string.digits
    else:
        letters = "abcdef" + string.digits
    return ''.join(random.choices(letters, k=length))


def rsync(cfg, opts, facts, bk_excludes=None):
    """
    Create the rsync command needed for backup or recovery, then execute that command.

    Args:
        cfg (obj): The cfg object, to pull cfg parameters.
        opts (obj): The argparse object.
        facts (obj): The facts object.
        bk_excludes (list): A list of paths to exclude from the backup.
    """
    import logging
    from planb.exceptions import RunCMDError

    logger = logging.getLogger('pbr')

    if opts.verbose:
        cmd = ['/usr/bin/rsync', '-av']
    else:
        cmd = ['/usr/bin/rsync', '-a']

    # Excludes aren't needed when recovering, so skip if None.
    if bk_excludes:
        excludes = []
        for ex in bk_excludes:
            split = ex.split('/')
            lst = '/'.join(list(filter(None, split)))
            excludes.append(f"--exclude=/{lst}/*")

        cmd.extend(excludes)

    # For recovering swap the order, and set the restore path to /mnt/rootfs.
    if facts.recovery_mode:
        cmd.append(f"{cfg.bk_mount}/{facts.hostname.split('.')[0]}/")
        cmd.append('/mnt/rootfs/')
    else:
        cmd.append('/')
        cmd.append(f"{cfg.bk_mount}/{facts.hostname.split('.')[0]}/")

    ret = run_cmd(cmd, ret=True)
    if ret.returncode:
        logger.error(f" The command {ret.args} returned in error: {ret.stderr.decode()}")
        raise RunCMDError()
    else:
        logger.debug(f"utils: rsync: stdout:{ret.stdout}")


def run_cmd(cmd, ret=False, timeout=None, capture_output=True):
    """
    Wrapper function around subprocess.run.

    Args:
        ret (bool): Bool, on weather to return anything or not.
        cmd (list): Array that contains the command to run.
        timeout (float): Timeout time, useful for nfs mounts.
        capture_output (bool): Bool, on weather to capture the output or not.

    Returns:
        (obj): The run command object, that includes the output and return code.
    """
    import logging
    from subprocess import PIPE, run, TimeoutExpired
    from planb.exceptions import RunCMDError

    logger = logging.getLogger('pbr')
    logger.debug(f"utils: run_cmd: cmd: {cmd}")

    try:
        if capture_output:
            if ret:
                return run(cmd, timeout=timeout, stdout=PIPE, stderr=PIPE)
            else:
                _ret = run(cmd, timeout=timeout, stdout=PIPE, stderr=PIPE)
                logger.debug(f"utils: run_cmd: stdout: {_ret.stdout.decode()}")
        else:
            if ret:
                return run(cmd, timeout=timeout, stderr=PIPE)
            else:
                _ret = run(cmd, timeout=timeout, stderr=PIPE)

        if _ret.returncode:
            logger.error(f" The command {_ret.args} returned in error: {_ret.stderr.decode()}")
            raise RunCMDError()
    except TimeoutExpired:
        logger.error(f" The command ({cmd}) timed out, exiting.")
        raise RunCMDError()


def udev_trigger():
    """
    Run udevadm trigger, to force udev reload.
    """
    from time import sleep

    run_cmd(['udevadm', 'trigger'])
    sleep(2)


def mount(src, dest, fstype=None, opts=None):
    """
    Wrapper that calls the mount command.

    Args:
        src (str): The device/network share that's being mounted.
        dest (str): The location the src will be mounted.
        fstype (str): The filesystem type.
        opts (str): Mount options to use when mounting.

    Returns:
        (obj): Returns the run command obj.
    """
    if opts is None:
        opts = "defaults"

    if fstype:
        cmd = ['/usr/bin/mount', '-v', '-o', opts, '-t', fstype, src, dest]
    else:
        cmd = ['/usr/bin/mount', '-v', '-o', opts, src, dest]

    return run_cmd(cmd, ret=True, timeout=10)


def umount(mnt, recursive=False, lazy=False):
    """
    Wrapper that calls the umount command.

    Args:
        mnt (str): Mount point to un-mount.
        recursive (bool): Bool, weather to un-mount recursively or not.
        lazy (bool): Perform a lazy umount.

    Returns:
        (obj): Returns the run command obj.
    """
    if recursive:
        if lazy:
            cmd = ['/usr/bin/umount', '-l', '-R', mnt]
        else:
            cmd = ['/usr/bin/umount', '-R', mnt]
    else:
        if lazy:
            cmd = ['/usr/bin/umount', '-l', mnt]
        else:
            cmd = ['/usr/bin/umount', mnt]

    return run_cmd(cmd, ret=True)
