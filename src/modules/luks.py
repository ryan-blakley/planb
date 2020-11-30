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

from .logger import log
from .utils import run_cmd


def get_luks_devs(udev_ctx):
    """
    Loop through and find any luks devices.
    :param udev_ctx: udev info ctx object.
    :return:
    """
    luks = dict()
    for d in udev_ctx.list_devices(subsystem='block'):
        if "crypto_LUKS" in d.get('ID_FS_TYPE', ""):
            info = dict()

            if d.get('DM_NAME', None):
                info.update({"uuid": d['ID_FS_UUID'], "version": d['ID_FS_VERSION'], "type": "lvm"})
                luks.update({f"/dev/mapper/{d['DM_NAME']}": info})
            else:
                info.update({"uuid": d['ID_FS_UUID'], "version": d['ID_FS_VERSION'], "type": "part"})
                luks.update({d['DEVNAME']: info})

    return luks


def luks_check(udev_ctx, luks, dev):
    """
    Loop through current devices, if any luks devices open them, and return. Otherwise restore the
    luks header, and open the luks device.
    :param udev_ctx:
    :param luks:
    :param dev:
    :return:
    """
    uuid = luks[dev]['uuid']

    for d in udev_ctx.list_devices(subsystem='block'):
        if "crypto_LUKS" in d.get('ID_FS_TYPE', ""):
            if uuid == d['ID_FS_UUID']:
                run_cmd(['/usr/sbin/cryptsetup', 'luksOpen', dev, f"luks-{uuid}"])
                log(f"  Opening {dev} at /dev/mapper/luks-{uuid}")
                return

    run_cmd(['/usr/sbin/cryptsetup', '-q', 'luksHeaderRestore', dev, '--header-backup-file',
             f"/facts/luks/{dev.split('/')[-1]}.backup"])
    log(f"  Restoring luks header on {dev}")

    run_cmd(['/usr/sbin/cryptsetup', 'luksOpen', dev, f"luks-{uuid}"])
    log(f"  Opening {dev} at /dev/mapper/luks-{uuid}")
    return

# vim:set ts=4 sw=4 et:
