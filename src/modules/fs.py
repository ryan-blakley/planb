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
from os.path import exists
from re import search

from .exceptions import ExistsError, RunCMDError
from .logger import log
from .utils import run_cmd


def fmt_fs(dev, fs_uuid, fs_label, fs_type):
    """
    Creates a filesystem on the device specified.
    :param dev: Device to format.
    :param fs_uuid: The uuid to set when formatting.
    :param fs_label: The label to set when formatting.
    :param fs_type: The type of filesystem to format the device.
    :return:
    """
    # Check to make sure the path is actually device before continuing.
    if not exists(dev):
        logging.error(f"ERROR: Can't format {dev}, because it isn't a valid device.")
        raise ExistsError()
    
    log(f"  Formatting {dev} as {fs_type}")

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
            cmd = ['/usr/sbin/mkfs.vfat', '-F 16', '-i', uuid, '-n', fs_label, dev]
        else:
            cmd = ['/usr/sbin/mkfs.vfat', '-F 16', '-i', uuid, dev]

    elif "ext" in fs_type:
        # Check to make sure fs_label isn't None.
        if fs_label:
            cmd = [f"/usr/sbin/mkfs.{fs_type}", '-U', fs_uuid, '-L', fs_label, dev]
        else:
            cmd = [f"/usr/sbin/mkfs.{fs_type}", '-U', fs_uuid, dev]

    ret = run_cmd(cmd, ret=True)

    if ret.returncode:
        stderr = ret.stderr.decode()
        if "is mounted" in stderr:
            logging.error(f" {ret.args} returned in error due to {dev} being mounted. "
                          "Please unmount everything and try again.")
        else:
            logging.error(f" The command {ret.args} returned in error: {ret.stderr.decode()}")

        raise RunCMDError()
