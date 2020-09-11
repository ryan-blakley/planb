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
from _ped import IOException


class Parted(object):
    def __init__(self):
        self.device = None
        self.pdisk = None

    def add_partition(self, start, end, fstype, flags, ptype):
        """
        Create a specified partition by start and end sectors.
        :param start: The sector the partition will start at.
        :param end: The sector the partition will end at.
        :param fstype: The fstype of the partition if it's valid.
        :param flags: The flags to set on the partition.
        :param ptype: The type of partition it should be.
        :return:
        """
        # An array of a few fs that aren't actually valid parted fs's.
        bad_fs = ['LVM2_member', 'swap', 'linux_raid_member', 'vfat']

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

            self.pdisk.addPartition(partition, constraint=parted.Constraint(exactGeom=geometry))
            self.pdisk.commit()

        # Catch any IOException then print a warning and skip it, normally it's
        # due to the device being active in some way lvm, md, etc.
        except IOException as e:
            logging.exception("Caught an IOException, when running parted.")
            pass

    def create_legacy_usb(self, disk):
        """
        Create the partition table on a usb, to make it bootable.
        :param disk: USB device name.
        :return:
        """
        logging.debug(f"parted: create_legacy_usb: disk:{disk}")
        self.init_disk(disk, "msdos")

        geometry = parted.Geometry(device=self.device, start=2048, length=self.device.getLength() - 2049)
        partition = parted.Partition(disk=self.pdisk, type=parted.PARTITION_NORMAL, geometry=geometry)

        self.pdisk.addPartition(partition=partition, constraint=self.device.optimalAlignedConstraint)
        partition.setFlag(parted.PARTITION_BOOT)
        partition.setFlag(parted.PARTITION_ESP)

        self.pdisk.commit()

        self.device.removeFromCache()

    def create_uefi_usb(self, disk):
        """
        Create the partition table on a usb, to make it bootable.
        :param disk: USB device name.
        :return:
        """
        logging.debug(f"parted: create_legacy_usb: disk:{disk}")
        self.init_disk(disk, "msdos")

        geometry = parted.Geometry(device=self.device, start=2048, end=206849)
        partition = parted.Partition(disk=self.pdisk, type=parted.PARTITION_NORMAL, geometry=geometry)

        self.pdisk.addPartition(partition=partition, constraint=self.device.optimalAlignedConstraint)
        partition.setFlag(parted.PARTITION_BOOT)
        partition.setFlag(parted.PARTITION_ESP)

        geometry = parted.Geometry(device=self.device, start=206850, length=self.device.getLength() - 207874)
        partition = parted.Partition(disk=self.pdisk, type=parted.PARTITION_NORMAL, geometry=geometry)

        self.pdisk.addPartition(partition=partition, constraint=self.device.optimalAlignedConstraint)

        self.pdisk.commit()

        self.device.removeFromCache()

    def init_disk(self, disk, ptable):
        """
        Initial and wipe the disk, and set the new partition table to ptable.
        :param disk: Device to initialize.
        :param ptable: Partition table to use msdos/gpt.
        :return:
        """
        logging.debug(f"parted: init_disk: disk:{disk} ptable:{ptable}")
        # Set the device.
        self.device = parted.getDevice(disk)

        # Wipe the device.
        self.device.clobber()

        # Create label on the disk.
        self.pdisk = parted.freshDisk(self.device, ptable)

    def recreate_disk(self, bdisk, rdisk):
        """
        Loop through the bdisk dictionary and recreate the partitions.
        :param bdisk: Dictionary that has the partition information in it.
        :param rdisk: The disk to recovery the partition onto.
        :return:
        """
        logging.debug(f"parted: recreate_disk: bdisk:{bdisk}")
        # Initialize the disk and create a label on it.
        if bdisk.get('type', False):
            self.init_disk(rdisk, bdisk['type'])
        else:
            logging.debug("parted: recreate_disk: skipping disk due to no partitions")
            return

        # Go through the backup disk dict, and recreate the
        # partitions from it on the disk.
        for key, vals in bdisk.items():
            if key.isnumeric():
                self.add_partition(bdisk[key]['start'], bdisk[key]['end'], bdisk[key]['fs_type'],
                                   bdisk[key]['flags'], bdisk[key]['type'])

        self.device.removeFromCache()