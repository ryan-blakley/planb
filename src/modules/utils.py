# This file is part of the Plan (B)ackup Recovery project:
# https://gitlab.cee.redhat.com/rblakley/pbr

# Plan (B)ackup Recovery is free software; you can redistribute
# it and/or modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation; either
# version 3 of the License, or (at your option) any later version.

# Plan (B)ackup Recovery is distributed in the hope that it will
# be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details go to
# <http://www.gnu.org/licenses/>.

import logging
import random
import string
from os import stat
from os.path import exists
from pyudev.device import Devices
from rpm import RPMTAG_BASENAMES, RPMTAG_NAME, files, TransactionSet
from shutil import copy2
from stat import S_ISBLK
from subprocess import PIPE, run, TimeoutExpired

from .exceptions import RunCMDError


def dev_from_file(udev_ctx, dev):
    """
    Queries udev based on the device path, this is so I don't have to import pyudev everywhere,
    and it shortens the call.
    :param udev_ctx: Pass in the udev_ctx to use.
    :param dev: The device file path ex. /dev/sda.
    :return: Udev device object.
    """
    return Devices.from_device_file(udev_ctx, dev)


def dev_from_name(udev_ctx, name):
    """
    Queries udev based on the device name, this is so I don't have to import pyudev everywhere,
    and it shortens the call.
    :param udev_ctx: Pass in the udev_ctx to use.
    :param name: Device name ex. sda1
    :return: Udev device object
    """
    return Devices.from_name(udev_ctx, 'block', name)


def get_dev_type(udev_info):
    """
    Queries the udev object, and returns the device type.
    :param udev_info: Pass in the udev_ctx to use.
    :return: Device type in str format.
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
    Parse /proc/modules, and return all loaded modules.
    :return:
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
    :param dev: Device path to check.
    :return:
    """
    if exists(dev) and S_ISBLK(stat(dev).st_mode):
        return True
    else:
        return False


def mk_cdboot(kernel, initrd, parmfile, outfile):
    """
    Create the cdboot.img file needed for s390 to boot. I based this off of
    https://github.com/weldr/lorax/blob/master/src/bin/mk-s390-cdboot just
    slimmed it down a bit, instead of having it as an external script.
    :param kernel: The vmlinuz file.
    :param initrd: The initrd file.
    :param parmfile: The parmfile normally cdboot.prm
    :param outfile: The outputted file.
    :return:
    """
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
    :param dev: str
    :param array: array
    :return: nothing
    """
    if dev not in array:
        array.append(dev)


def rand_str(length, hexa):
    """
    Return a random string, used for uuid generation when needed.
    :param length: Length of string to return.
    :param hexa: Bool if hexa, return only hexadecimals.
    :return: String
    """
    if not hexa:
        letters = string.ascii_uppercase + string.digits
    else:
        letters = "abcdef" + string.digits
    return ''.join(random.choice(letters) for i in range(length))


def rpmq(pkg):
    """
    Check if a pkg is installed on the system.
    :param pkg: pkg name
    :return: True/False
    """
    ts = TransactionSet()

    if ts.dbMatch(RPMTAG_NAME, pkg):
        return True
    else:
        return False


def rpmql(pkg):
    """
    List all the files belonging to the passed in rpm.
    :param pkg: pkg name
    :return: List of files.
    """
    ts = TransactionSet()
    for h in ts.dbMatch(RPMTAG_NAME, pkg):
        return files(h)


def rpmqf(path):
    """
    Return the rpm that own the file/dir.
    :param path: File to check.
    :return: RPM that owns the file.
    """
    ts = TransactionSet()
    for h in ts.dbMatch(RPMTAG_BASENAMES, path):
        return h['name']


def rsync(cfg, opts, facts, bk_excludes=None):
    """
    Create the rsync command needed for backup or recovery, then execute that command.
    :param cfg: The cfg object, to pull cfg parameters.
    :param opts: The opts object, to check for verbosity.
    :param facts: The facts object, to query the hostname.
    :param bk_excludes: A list of paths to exclude from the backup.
    :return:
    """
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

    logging.debug(f"utils: rsync: cmd:{cmd}")

    ret = run_cmd(cmd, ret=True)
    if ret.returncode:
        logging.error(f" The command {ret.args} returned in error: {ret.stderr.decode()}")
        raise RunCMDError()
    else:
        logging.debug(f"utils: rsync: stdout:{ret.stdout}")


def run_cmd(cmd, ret=False, timeout=None, capture_output=True):
    """
    Wrapper function around subprocess.run.
    :param ret: Bool, on weather to return anything or not.
    :param cmd: Array that contains the command to run.
    :param timeout: Timeout time, useful for nfs mounts.
    :param capture_output: Bool, on weather to capture the output or not.
    :return: The output/return code.
    """
    try:
        if capture_output:
            if ret:
                return run(cmd, timeout=timeout, stdout=PIPE, stderr=PIPE)
            else:
                _ret = run(cmd, timeout=timeout, stdout=PIPE, stderr=PIPE)
        else:
            if ret:
                return run(cmd, timeout=timeout, stderr=PIPE)
            else:
                _ret = run(cmd, timeout=timeout, stderr=PIPE)

        if _ret.returncode:
            logging.error(f" The command {_ret.args} returned in error: {_ret.stderr.decode()}")
            raise RunCMDError()
    except TimeoutExpired:
        logging.error(f" The command ({cmd}) timed out, exiting.")
        raise RunCMDError()


def mount(src, dest, fstype=None, opts=None):
    """
    Wrapper that calls the mount command.
    :param src: The device/network share that's being mounted.
    :param dest: The location the src will be mounted.
    :param fstype: The filesystem type.
    :param opts: Mount options to use when mounting.
    :return: The output, and return code.
    """
    if opts is None:
        opts = "defaults"

    if fstype:
        cmd = ['/usr/bin/mount', '-o', opts, '-t', fstype, src, dest]
    else:
        cmd = ['/usr/bin/mount', '-o', opts, src, dest]

    return run_cmd(cmd, ret=True, timeout=10)


def umount(mnt, recursive=False, lazy=False):
    """
    Wrapper that calls the umount command.
    :param lazy: Perform a lazy umount.
    :param recursive: Bool, weather to un-mount recursively or not.
    :param mnt: Mount point to un-mount.
    :return: The output, and return code.
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

# vim:set ts=4 sw=4 et:
