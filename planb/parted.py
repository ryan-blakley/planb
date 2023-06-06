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
import parted

from _ped import DeviceException, DiskException, IOException, PartitionException

from planb.utils import dev_from_file, is_block


def get_part_layout(udev_ctx):
    """
    Loop through the disk and use parted and udev to capture the
    partition layout. Might need to add threading to the for loop in the
    future for servers with a ton of disk.
    
    Args:
        udev_ctx (obj): Udev ctx obj.

    Returns:
        disks_dict (dict): Dict of the disk partition layout.
    """
    from glob import glob
    from re import search

    # Define dict to store disk info.
    disks_dict = dict()

    def update(name, p_dev):
        if name:
            disks_dict.update({name: disk})
        else:
            disks_dict.update({d.device_node: disk})

        p_dev.removeFromCache()

    # Loop through disk pulled from udev.
    for d in udev_ctx.list_devices(subsystem='block', DEVTYPE='disk'):
        dm_name = None

        # Skip if the device is a /dev/loop, mdraid, cd, or usb.
        if not search("/dev/loop", d.device_node) and not d.get('MD_NAME', False) and not search(
                "cd", d.get('ID_TYPE', "")) and not search("usb", d.get('ID_BUS', "")) and not int(
                d.get('DM_MULTIPATH_DEVICE_PATH', False)):

            # If it's a dm device check if it's mpath if not skip it,
            # if it is set the dm_name.
            if search("dm-", d.device_node):
                if search("^mpath-", d.get('DM_UUID', "")):
                    dm_name = f"/dev/mapper/{d.get('DM_NAME')}"
                else:
                    continue

            # If the device is a mpath path, then skip it, would prefer
            # to query udev here, but apparently in the recovery
            # environment the DM_MULTIPATH_DEVICE_PATH variable is always
            # a zero for some reason. So I don't trust using it, so check
            # if the dev has any holders, and if they're a mpath device.
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
                    part_info = dev_from_file(udev_ctx, dev)

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


class Parted(object):
    def __init__(self):
        self.log = logging.getLogger('pbr')
        self.device = None
        self.pdisk = None

    def add_partition(self, start, end, fstype, flags, ptype):
        """
        Create a specified partition by start and end sectors.

        Args:
            start (int): The sector the partition will start at.
            end (int): The sector the partition will end at.
            fstype (str): The fstype of the partition if it's valid.
            flags (str): The flags to set on the partition.
            ptype (str): The type of partition it should be.
        """
        # An array of a few fs types that aren't actually valid parted fs types.
        bad_fs = ['LVM2_member', 'swap', 'linux_raid_member', 'vfat', 'crypto_LUKS']

        try:
            # Set the partition type.
            if ptype == 0:
                p_type = parted.PARTITION_NORMAL
            elif ptype == 1:
                p_type = parted.PARTITION_LOGICAL
            elif ptype == 2:
                p_type = parted.PARTITION_EXTENDED
            else:
                p_type = parted.PARTITION_NORMAL

            geometry = parted.Geometry(start=start, end=end, device=self.device)

            if fstype and fstype not in bad_fs:
                filesystem = parted.FileSystem(type=fstype, geometry=geometry)
                partition = parted.Partition(disk=self.pdisk, type=p_type, fs=filesystem, geometry=geometry)
            else:
                partition = parted.Partition(disk=self.pdisk, type=p_type, geometry=geometry)

            # Set any flags needed.
            for flags in flags.split(','):
                if "boot" in flags:
                    partition.setFlag(parted.PARTITION_BOOT)
                elif "lvm" in flags:
                    partition.setFlag(parted.PARTITION_LVM)
                elif "swap" in flags:
                    partition.setFlag(parted.PARTITION_SWAP)
                elif "raid" in flags:
                    partition.setFlag(parted.PARTITION_RAID)
                elif "bios_grub" in flags:
                    partition.setFlag(parted.PARTITION_BIOS_GRUB)
                elif "esp" in flags:
                    partition.setFlag(parted.PARTITION_ESP)
                elif "prep" in flags:
                    partition.setFlag(parted.PARTITION_PREP)

            self.pdisk.addPartition(partition, constraint=parted.Constraint(exactGeom=geometry))
            self.pdisk.commit()

        # Catch any IOException then print a warning and skip it, normally it's
        # due to the device being active in some way lvm, md, etc.
        except IOException:
            self.log.exception("Caught an IOException, when running parted.")
            pass

    def create_legacy_usb(self, disk):
        """
        Create the partition table on an usb, to make it bootable.

        Args:
            disk (str): USB device name.
        """
        self.log.debug(f"parted: create_legacy_usb: disk:{disk}")
        self.init_disk(disk, "msdos")

        geometry = parted.Geometry(device=self.device, start=2048, length=self.device.getLength() - 2049)
        partition = parted.Partition(disk=self.pdisk, type=parted.PARTITION_NORMAL, geometry=geometry)

        self.pdisk.addPartition(partition=partition, constraint=self.device.optimalAlignedConstraint)
        partition.setFlag(parted.PARTITION_BOOT)

        self.pdisk.commit()

        self.device.removeFromCache()

    def create_prep_usb(self, disk):
        """
        Create the partition table on an usb, to make it bootable.

        Args:
            disk (str): USB device name.
        """
        self.log.debug(f"parted: create_prep_usb: disk:{disk}")
        self.init_disk(disk, "msdos")

        geometry = parted.Geometry(device=self.device, start=2048, end=10239)
        partition = parted.Partition(disk=self.pdisk, type=parted.PARTITION_NORMAL, geometry=geometry)

        self.pdisk.addPartition(partition=partition, constraint=self.device.optimalAlignedConstraint)
        partition.setFlag(parted.PARTITION_BOOT)
        partition.setFlag(parted.PARTITION_PREP)

        geometry = parted.Geometry(device=self.device, start=10240, length=self.device.getLength() - 10240)
        partition = parted.Partition(disk=self.pdisk, type=parted.PARTITION_NORMAL, geometry=geometry)

        self.pdisk.addPartition(partition=partition, constraint=self.device.optimalAlignedConstraint)

        self.pdisk.commit()

        self.device.removeFromCache()

    def create_uefi_usb(self, disk):
        """
        Create the partition table on an usb, to make it bootable.

        Args:
            disk (str): USB device name.
        """
        self.log.debug(f"parted: create_legacy_usb: disk:{disk}")
        self.init_disk(disk, "msdos")

        geometry = parted.Geometry(device=self.device, start=2048, end=206849)
        partition = parted.Partition(disk=self.pdisk, type=parted.PARTITION_NORMAL, geometry=geometry)

        self.pdisk.addPartition(partition=partition, constraint=self.device.optimalAlignedConstraint)
        partition.setFlag(parted.PARTITION_BOOT)
        partition.setFlag(parted.PARTITION_ESP)

        geometry = parted.Geometry(device=self.device, start=206850, length=self.device.getLength() - 206850)
        partition = parted.Partition(disk=self.pdisk, type=parted.PARTITION_NORMAL, geometry=geometry)

        self.pdisk.addPartition(partition=partition, constraint=self.device.optimalAlignedConstraint)

        self.pdisk.commit()

        self.device.removeFromCache()

    def init_disk(self, disk, ptable):
        """
        Initial and wipe the disk, and set the new partition table to ptable.

        Args:
            disk (str): Device to initialize.
            ptable (str): Partition table to use msdos/gpt.
        """
        self.log.debug(f"parted: init_disk: disk:{disk} ptable:{ptable}")
        # Set the device.
        self.device = parted.getDevice(disk)

        # Wipe the device.
        self.device.clobber()

        # Create label on the disk.
        self.pdisk = parted.freshDisk(self.device, ptable)

    def recreate_disk(self, bdisk, rdisk):
        """
        Loop through the bdisk dictionary and recreate the partitions.

        Args:
            bdisk (dict): Dictionary that has the partition information in it.
            rdisk (str): The disk to recovery the partition onto.
        """
        self.log.debug(f"parted: recreate_disk: bdisk:{bdisk}")
        # Initialize the disk and create a label on it.
        if bdisk.get('type', False):
            self.init_disk(rdisk, bdisk['type'])
        else:
            self.log.debug("parted: recreate_disk: skipping disk due to no partitions")
            return

        # Go through the backup disk dict, and recreate the
        # partitions from it on the disk.
        for key, vals in bdisk.items():
            if key.isnumeric():
                self.add_partition(bdisk[key]['start'], bdisk[key]['end'], bdisk[key]['fs_type'],
                                   bdisk[key]['flags'], bdisk[key]['type'])

        self.device.removeFromCache()
