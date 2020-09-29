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

import json
import parted
from glob import glob
from os import environ, uname
from os.path import exists
from re import search
from _ped import DeviceException, DiskException, PartitionException
from platform import machine
from pyudev import Context

from .lvm import get_lvm_report
from .md import get_md_info
from .utils import dev_from_file, get_dev_type, is_block, rpmq


class Facts(object):
    def __init__(self):
        """
        The facts class is meant to determine different facts about the server being
        backed up, like what the storage layout is, what are the mount points, selinux,
        etc. The variables are used through out the application for various stuff.
        """
        self.lvm = dict()

        # Some of these need to be called in order.
        self.recovery_mode = environ.get('RECOVERY_MODE', False)
        self.hostname = uname().nodename
        self.udev_ctx = Context()
        self.mnts = self.get_mnts()
        self.disks = self.get_part_layout()
        self.lvm_installed = rpmq("lvm2")

        if not self.recovery_mode:
            import distro
            self.distro = distro.name()
            self.distro_pretty = distro.name(pretty=True)
            self.modules = self.get_modules()
            self.uefi = exists("/sys/firmware/efi")
            self.uname = uname().release
            self.arch = machine()

            from selinux import is_selinux_enabled, security_getenforce
            if is_selinux_enabled():
                self.selinux_enabled = 1
                self.selinux_enforcing = security_getenforce()
            else:
                self.selinux_enabled = 0
                self.selinux_enforcing = 0

        # Confirm the lvm2 pkg is installed before querying lvm.
        if self.lvm_installed:
            self.lvm = get_lvm_report(self.udev_ctx)

        self.md_info = get_md_info(self.udev_ctx)

    def get_mnts(self):
        """
        Query and store information about anything that's mounted.
        :return:
        """
        mnts = dict()

        def add_entries(dev, mp):
            info = dict()
            vg = None
            parent = None
            md_devname = None

            udev_info = dev_from_file(self.udev_ctx, dev)
            
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

        for x in read_strip_filter("/proc/swaps"):
            add_entries(x.split()[0], "[SWAP]")

        return mnts

    def get_modules(self):
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

    def get_part_layout(self):
        """
        Loop through the disk and use parted and udev to capture the
        partition layout. Might need to add threading to the for loop in the
        future for servers with a ton of disk.
        :return:
        """
        # Define dict to store disk info.
        disks_dict = dict()

        def update(name, p_dev):
            if name:
                disks_dict.update({name: disk})
            else:
                disks_dict.update({d.device_node: disk})

            p_dev.removeFromCache()

        # Loop through disk pulled from udev.
        for d in self.udev_ctx.list_devices(subsystem='block', DEVTYPE='disk'):
            dm_name = None

            # Skip if the device is a /dev/loop, mdraid, cd, or usb.
            if (not search("/dev/loop", d.device_node) 
                    and not d.get('MD_NAME', False) 
                    and not search("cd", d.get('ID_TYPE', "")) 
                    and not search("usb", d.get('ID_BUS', "")) 
                    and not int(d.get('DM_MULTIPATH_DEVICE_PATH', False))):

                # If it's a dm device check if it's mpath if not skip it,
                # if it is set the dm_name.
                if search("dm-", d.device_node):
                    if search("^mpath-", d.get('DM_UUID', "")):
                        dm_name = f"/dev/mapper/{d.get('DM_NAME')}"
                    else:
                        continue

                # If the device is an mpath path, then skip it, would prefer 
                # to query udev here, but apparently in the recovery 
                # environment the DM_MULTIPATH_DEVICE_PATH variable is always
                # a zero for some reason. So I don't trust using it, so check 
                # if the dev has any holders, and if they're an mpath device.
                holders = glob(f"/sys/block/{d.device_node.split('/')[-1]}/holders/*/dm/uuid")
                if holders:
                    with open(holders[0]) as f:
                        if f.readline().split()[0].startswith("mpath-"):
                            continue

                # Define a dict to store each disk info.
                disk = dict()

                # Fetch the parted device.
                p_device = parted.getDevice(d.device_node)

                # Add parted info, and udev info to the dict.
                disk.update({"id_serial": d.get('ID_SERIAL_SHORT'),
                             "id_wwn": d.get('ID_WWN'),
                             "id_path": d.get('ID_PATH'),
                             "size": p_device.length})

                # Add a catch for disk that don't have a label and skip them.
                try:
                    # Fetch the parted disk object.
                    p_disk = parted.newDisk(p_device)
                except (DeviceException, DiskException):
                    disk.update({"fs_type": d.get('ID_FS_TYPE'),
                                 "fs_uuid": d.get('ID_FS_UUID', '')})
                    update(dm_name, p_device)
                    continue

                # Add parted info, and udev info to the dict.
                disk.update({"type": p_disk.type})

                if p_disk.type == "loop":
                    disk.update({"fs_type": d.get('ID_FS_TYPE'),
                                 "fs_uuid": d.get('ID_FS_UUID', '')})
                    update(dm_name, p_device)
                    continue

                # Loop through the partitions, and grab info.
                for p in p_disk.partitions:
                    # Define dict to store partition info.
                    part = dict()

                    # Grab any part flags, and the part type.
                    part.update({"flags": p.getFlagsAsString(), 
                                 "type": p.type})

                    # If the disk label isn't msdos, check for part names.
                    if "msdos" not in p_disk.type:
                        try:
                            if p.name:
                                part.update({"name": p.name})
                            else:
                                part.update({"name": None})
                        except PartitionException:
                            part.update({"name": None})
                            pass
                    else:
                        part.update({"name": None})
                   
                    # Pull the fs type from udev instead of parted.
                    if dm_name and dm_name[-1].isnumeric():
                        dev = f"{dm_name}p{p.number}"
                    elif dm_name:
                        dev = f"{dm_name}{p.number}"
                    elif d.device_node[-1].isnumeric():
                        dev = f"{d.device_node}p{p.number}"
                    else:
                        dev = f"{d.device_node}{p.number}"

                    if is_block(dev):
                        part_info = dev_from_file(self.udev_ctx, dev)

                        # Add the fs info, and the geometry info.
                        part.update({"fs_type": part_info.get('ID_FS_TYPE', ''),
                                     "fs_uuid": part_info.get('ID_FS_UUID', ''),
                                     "fs_label": part_info.get('ID_FS_LABEL', ''),
                                     "start": p.geometry.start,
                                     "end": p.geometry.end})

                    # Add the part dict as an entry to the disk dict.
                    # Might change this to the full path later, for 
                    # now just the part number.
                    disk.update({p.number: part})

                # Add the disk dict as an entry to the master dict.
                update(dm_name, p_device)

        return disks_dict

    def test(self):
        print(json.dumps(self.lvm, indent=4))
        print(json.dumps(self.disks, indent=4))
        print(json.dumps(self.mnts, indent=4))
        print("")
        print(json.dumps(self.md_info, indent=4))
        print("")

# vim:set ts=4 sw=4 et:
