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
import logging

from glob import glob
from os import environ, chdir, chmod, chroot, makedirs, sync, O_RDONLY
from os import open as o_open
from os.path import exists, isdir, isfile, join
from re import search
from shutil import move

from selinux import chcon

from planb.exceptions import ExistsError, GeneralError, MountError, RunCMDError
from planb.facts import Facts
from planb.fs import fmt_fs, get_mnts
from planb.luks import luks_check
from planb.lvm import deactivate_vgs, RecoveryLVM
from planb.md import get_md_info, md_check
from planb.parted import Parted
from planb.tar import restore_tar
from planb.utils import dev_from_file, dev_from_name, rsync, run_cmd, mount, umount


class Recover(object):
    def __init__(self, opts, cfg):
        """
        A class to run all the recovery task out of.

        Args:
            opts (obj): The argparse object.
            cfg (obj): The cfg file object.
        """
        self.log = logging.getLogger('pbr')

        # Check to make sure we're booted into the iso.
        if not environ.get('RECOVERY_MODE'):
            self.log.error(" Recover should be ran from recovery mode only.")
            raise ExistsError()

        # Set opts, cfg, and facts.
        self.opts = opts
        self.cfg = cfg
        self.facts = Facts()

        with open('/facts/disks.json') as json_file:
            self.bk_disks = json.load(json_file)
        with open('/facts/lvm.json') as json_file:
            self.bk_lvm = json.load(json_file)
        with open('/facts/misc.json') as json_file:
            self.bk_misc = json.load(json_file)
        with open('/facts/mnts.json') as json_file:
            self.bk_mnts = json.load(json_file)

        # Set str vars.
        self.tmp_bk_mnt = "/mnt/backup"
        self.tmp_rootfs_dir = "/mnt/rootfs"

        # Tmp variables for mapping.
        self.tmp_mapped_disks = dict()
        self.lst_mapped_mps = []
        self.bk_mounted = False

    def cleanup(self):
        """
        Un-mount the backup mount, and sync everything.
        """
        # When finished un-mount the bk_mount if there was a mount
        # for rsync there isn't a mount, so no need to un-mount anything.
        if self.bk_mounted:
            umount(self.tmp_bk_mnt)

        sync()

    def cmp_disks(self):
        """
        This function compares the disk set in the backup, to the disk
        presented to the recovery environment. It possible that disk enumeration
        changes disk names, there is also going to be people that use this to
        migrate to different servers all together. So the disk need to be compared
        and mapped if needed to the proper disk in the recovery environment.
        """
        # Make a copy, so entries can be removed, and added to the originals.
        facts_disks = self.facts.disks.copy()
        bk_disks = self.bk_disks.copy()
        matching_size_disks = dict()
        possible_larger_disks = dict()

        # Loop through the disk needed for mount points, from the backup.
        for disk1, info1 in bk_disks.items():
            self.log.debug(f"disk1: {disk1}")
            sn1 = info1.get('id_serial', '')
            size1 = int(info1.get('size', 0))
            if search("/dev/mapper", disk1):
                d1_mapper = 1
            else:
                d1_mapper = 0

            # First test by device name, if everything matches loop to the next.
            if facts_disks.get(disk1, ''):
                # Check if sn exist and if they match.
                if sn1 and sn1 == facts_disks[disk1]['id_serial']:
                    # If the sn matches confirm the size is still the same.
                    if size1 == int(facts_disks[disk1]['size']):
                        self.log.debug("name, sn, and size matches")
                        # Delete disk from facts_disks.
                        del facts_disks[disk1]
                        continue

                # If the serial number doesn't exist, or doesn't match, chk the size.
                elif size1 == int(facts_disks[disk1]['size']):
                    self.log.debug("name, and size matches")
                    # If the size matches, delete from facts_disks.
                    del facts_disks[disk1]
                    continue

            self.log.debug(f"Disk {disk1} with the size of {size1} doesn't exist in the recovery environment, "
                           "checking if there is a suitable disk.")
            possible_size_matching_disks = []
            larger_disks = []

            # If checking by dev name doesn't match, loop through facts_disks.
            for disk2, info2 in list(facts_disks.items()):
                # If disk1 is an mpath device, skip all regular disk/paths.
                if not search("/dev/mapper", disk2) and d1_mapper:
                    continue

                sn2 = info2.get('id_serial', '')
                size2 = int(info2.get('size', 0))
                self.log.debug(f"disk1:{disk1} size1:{size1} disk2:{disk2} size2:{size2}")

                if sn1 and sn2 and sn1 == sn2:
                    if size1 == size2:
                        self.log.debug("serial number and size matches")
                        self.map_disk(disk1, disk2)
                        del facts_disks[disk2]
                        break

                # If the size matches, add to list, and del the entry, we'll handle the list later.
                elif size1 == size2:
                    self.log.debug("sizes only match")
                    possible_size_matching_disks.append(disk2)
                    del facts_disks[disk2]
                    break

                # Come back to, for disk that don't match exact size, we could grab a
                # list of possible disk that are larger, then the user manually map.
                elif size1 < size2:
                    self.log.debug("Disk is larger append to the list of possible disk if needed.")
                    larger_disks.append(disk2)

                elif size1 > size2:
                    self.log.error(f" There isn't a disk large enough to recovery the backup disk {disk1}, "
                                   f"please add a disk equal or larger than {size1}.")
                    raise ExistsError()

            if possible_size_matching_disks:
                matching_size_disks.update({disk1: possible_size_matching_disks})

            if larger_disks:
                possible_larger_disks.update({disk1: larger_disks})

        if matching_size_disks:
            for key, vals in matching_size_disks.items():
                l_vals = len(vals)
                if l_vals > 1:
                    self.log.info(f"\n  So it appears the disk enumeration changed or you're running this recover on "
                                  f"another server.\n  The backup disk {key} doesn't match the recovery environments "
                                  f"disk of the same name.\n It appears there are {l_vals} disk that match the size, "
                                  f"they are {' '.join(vals)}.\n")
                    m_disk = input("  Please enter the disk that should be used to restore on from the above list: ")
                    if exists(m_disk) and m_disk in vals:
                        self.log.debug(f"  test1 key:{key} m_disk:{m_disk}")
                        self.map_disk(key, m_disk)
                    else:
                        self.log.error(f" The disk {m_disk} doesn't exist or wasn't in the list, "
                                       "please enter one of the disk in the output.")
                        raise ExistsError()
                else:
                    self.log.debug(f"recover: cmp_disk: matching_size_disk: key:{key} vals:{vals[0]}")
                    self.map_disk(key, vals[0])

        if possible_larger_disks:
            for key, vals in possible_larger_disks.items():
                l_vals = len(vals)
                if l_vals:
                    self.log.info(f"\n  So it appears a new bigger disk was added to replace the old one, "
                                  f"or you're running this recover on another server.\n The backup disk {key} doesn't "
                                  "match the recovery environments disk of the same name, serial number, or size.")
                    if l_vals == 1:
                        self.log.info(f"  It appears there is {l_vals} disk that is larger in size, "
                                      f"it is {' '.join(vals)}.\n")
                    else:
                        self.log.info(f"  It appears there are {len(vals)} disk that are larger in size, "
                                      f"they are {' '.join(vals)}.\n")

                    m_disk = input("  Please enter the disk that should be used to restore on from the above list: ")
                    if exists(m_disk) and m_disk in vals:
                        self.log.debug(f"recover: cmp_disk: possible_larger_disks: key:{key} m_disk:{m_disk}")
                        self.map_disk(key, m_disk)
                    else:
                        self.log.error(f" The disk {m_disk} doesn't exist or wasn't in the list, "
                                       "please enter one of the disk in the output.")
                        raise ExistsError()
                else:
                    self.log.debug(f"  test2 key:{key} vals:{vals[0]}")
                    self.map_disk(key, vals[0])

        # Add any tmp_mapped_disks back to self.bk_disks.
        self.bk_disks.update(self.tmp_mapped_disks)

        # For debugging log the values after in case mapping failed.
        self.log.debug(f"recover: cmp_disk: bk_disks:{self.bk_disks}")
        self.log.debug(f"recover: cmp_disk: bk_mnts:{self.bk_mnts}")
        if self.bk_lvm.get('PVS', False):
            self.log.debug(f"recover: cmp_disk: bk_lvm:{self.bk_lvm['PVS']}")

    def cmp_disk_layout(self, d1, d2, facts):
        """
        Compare specified disk to see if they contain the same partition
        table, or the same filesystem if no partition table. The purpose is to check if
        the disk needs to be repartitioned or not, there is no point in wiping and
        repartitioning a disk, if the partitions match the backup disk.

        Args:
            d1 (str): First disk to compare.
            d2 (str): Second disk to compare.
            facts (obj): Facts object.

        Returns:
            (bool): Whether the disk match or not.
        """
        match = 0
        partitioned = 0

        # Loop through disks d1 entry to look for partitions.
        for key, val in self.bk_disks[d1].items():
            self.log.debug(f"recover: cmp_disk_layout: key:{key} val:{val}")
            # If there are partitions the key will be the partition number,
            # so we can ignore non number keys.
            if key.isnumeric():
                partitioned += 1
                # If the restore disk is missing a partition,
                # it will throw a key error, so catch and return false.
                try:
                    # Check if the partitions start sectors match, if not return false. Wrap key in int(),
                    # since when the backup facts are written to disk, they're converted to str.
                    if not self.bk_disks[d1][key]['start'] == facts.disks[d2][int(key)]['start']:
                        return False
                    else:
                        match += 1
                except KeyError:
                    return False

        # This is a check for non-partitioned disk with a fs, basically if we've made it this far,
        # the size has already been checked. So check for a fs key, if it exists return true, if
        # it doesn't return false.
        if partitioned == 0:
            return self.bk_disks[d1].get('fs', '')

        # If we haven't returned false yet, make sure match was incremented,
        # if it was return true, if not false.
        if match > 0:
            return True
        else:
            return False

    def grab_bootloader_disk(self, mp):
        """
        Figure out what disk /boot is mounted on in the tmp dir,
        and return tha disk's path.

        Args:
            mp (str): Mount point to check.

        Returns:
            (str): The device name.
        """
        for mnt, info in get_mnts(self.facts.udev_ctx).items():
            self.log.debug(f"recover: grab_bootloader_disk: cmp_mp: {self.tmp_rootfs_dir}{mp} mnt: {mnt}")
            if mnt == f"{self.tmp_rootfs_dir}{mp}":
                dev_info = dev_from_file(self.facts.udev_ctx, info['path'])
                if info['type'] == "part":
                    return dev_info.find_parent('block').device_node
                elif info['type'] == "part-mpath":
                    return f"/dev/mapper/{dev_info['DM_MPATH']}"
                elif info['type'] == "disk" or info['type'] == "mpath":
                    return info['path']
                elif info['type'] == "lvm":
                    d = glob(f"/sys/block/{info['kname'].split('/')[-1]}/slaves/*")[0].split("/")[-1]
                    return dev_from_name(self.facts.udev_ctx, d).find_parent('block').device_node
                else:
                    p = None

                    # Just grab the first disk in the list of devs, they should be sorted to have the top device.
                    # Probably need to print something to warn that the devices might enumerate different on reboot.
                    if info['type'] == "part-raid":
                        return dev_info.find_parent('block').device_node
                    elif info['md_devname']:
                        p = info['md_devname'].split('/')[-1]

                    # Since this is in an else statement, make sure p isn't None.
                    if p:
                        self.log.debug(f"recover: grab_bootloader_disk: p: {p}")
                        md_info_dev = get_md_info(self.facts.udev_ctx)[p]['devs'][0]
                        d_info = dev_from_name(self.facts.udev_ctx, md_info_dev)
                        if d_info['DEVTYPE'] == "partition":
                            return d_info.find_parent('block').device_node
                        else:
                            return d_info.device_node

    def handle_disk_excludes(self):
        """
        Process any recovery_exclude_disks entries,
        and remove disk from bk_disks, and bk_mnts.
        """
        if self.cfg.rc_exclude_disks:
            # Loop through each mp, and remove any mp that it's parent is in the disk excludes.
            self.log.debug("recover: handle_disk_excludes: looping trough bk_mnts to remove any.")
            mnts = self.bk_mnts.copy()
            for mp, info in mnts.items():
                self.log.debug(f"backup: cleanup_disks: Checking mp:{mp} info:{info}")
                # For recovery disk excludes I'm not going to handle lvm stuff,
                # exclude vg should be set for that.
                if str(info['type']) == "lvm":
                    self.log.debug("backup: handle_disk_excludes: Skipping due to being type lvm.")
                    continue

                # Check if it has a parent set, if it does check if it exists in rc_exclude_disks,
                # if it does then remove it from bk_mnts.
                if info['parent'] and info['parent'] in self.cfg.rc_exclude_disks:
                    self.log.debug(f"backup: handle_disk_excludes: Removing {mp} from bk_mnts.")
                    self.bk_mnts.pop(mp)

            # Loop through each disk and removing any entry from bk_disks that are in the excludes.
            self.log.debug("recover: handle_disk_excludes: looping trough bk_disks to remove any.")
            disks = self.bk_disks.copy()
            for d in disks.keys():
                if d in self.cfg.rc_exclude_disks:
                    self.log.debug(f"backup: handle_disk_excludes: Removing {d} from bk_disks.")
                    self.bk_disks.pop(d)

    def handle_vg_excludes(self):
        """
        Process any recovery_exclude_vgs that are set,
        and remove entries from bk_vgs, and bk_mnts.
        """
        if self.cfg.rc_exclude_vgs:
            for vg in self.cfg.rc_exclude_vgs:
                if vg in self.bk_misc['bk_vgs']:
                    self.log.debug(f"recover: handle_vg_excludes: Removing {vg} from bk_vgs.")
                    self.bk_misc['bk_vgs'].remove(vg)

                    mnts = self.bk_mnts.copy()
                    for mp, info in mnts.items():
                        if info['vg'] == vg:
                            self.log.debug(f"recover: handle_vg_excludes: Removing {mp} from bk_mnts.")
                            self.bk_mnts.pop(mp)

    def map_disk(self, o_disk, n_disk):
        """
        This function changes the disk stored in bk_mnts and bk_disks, so that the
        recovery is done on the proper disk in the recovery environment.

        Args:
            o_disk (str): Original disk name from the backup.
            n_disk (str): New disk name from the recovery environment.
        """
        # If the disk exist in bk_disks, then copy to tmp dict with the n_disk as the key.
        if self.bk_disks.get(o_disk, False):
            self.tmp_mapped_disks.update({n_disk: self.bk_disks.pop(o_disk)})

        # For the mnts, we need to loop through each entry, to replace the various info entries.
        for mnt, info in self.bk_mnts.items():
            # Loop through the mapped mps list, if the mnt matches, skip it. This is in case for ex.
            # you have /dev/vda being mapped to /dev/vdb, and then later /dev/vdb needs to be mapped
            # to /dev/vda, which would cause the previous map to be overwritten again.
            if [True for x in self.lst_mapped_mps if mnt == x]:
                continue

            if info['type'] == "lvm" or info['type'] == "raid":
                continue

            if info['type'] == "part":
                d = info['parent']
            elif info['type'] == "part-mpath":
                d = info['parent']
            elif info['type'] == "mpath" or info['type'] == "disk":
                d = info['path']
            else:
                d = None

            if o_disk == d:
                if n_disk[-1].isnumeric() and "part" in info['type']:
                    self.bk_mnts[mnt]['path'] = info['path'].replace(o_disk, f"{n_disk}p")
                    self.bk_mnts[mnt]['parent'] = info['parent'].replace(o_disk, n_disk)
                else:
                    self.bk_mnts[mnt]['path'] = info['path'].replace(o_disk, n_disk)
                    self.bk_mnts[mnt]['parent'] = info['parent'].replace(o_disk, n_disk)

                # Append the mp to the mapped list, so it can be skipped.
                self.lst_mapped_mps.append(mnt)

                self.log.debug(f"recover: map_disk: mnts: od:{o_disk} nd:{n_disk} d:{d}")
                self.log.debug(f"recover: map_disk: mnts: bk_mnts[mnt]:{self.bk_mnts[mnt]}")

        # If md_info exist in bk_misc, update the devs entries if they need to be.
        if self.bk_misc.get('md_info', ''):
            od_split = o_disk.split('/')[-1]
            nd_split = n_disk.split('/')[-1]

            for devname, info in self.bk_misc['md_info'].items():
                for d in info['devs']:
                    if od_split == search("([a-z]+)", d).group():
                        self.bk_misc['md_info'][devname]['devs'] = [i.replace(od_split, nd_split) for i in info['devs']]

        # If there is a pvs entry, update the pvs if needed.
        if self.bk_lvm.get('PVS', False):
            i = 0
            for pv in self.bk_lvm['PVS']:
                if pv['d_type'] == "disk" or pv['d_type'] == "mpath":
                    self.bk_lvm['PVS'][i]['pv_name'] = pv['pv_name'].replace(o_disk, n_disk)
                    if pv['parent']:
                        self.bk_lvm['PVS'][i]['parent'] = pv['parent'].replace(o_disk, n_disk)
                elif pv['d_type'].startswith("part"):
                    if o_disk == str(pv['parent']):
                        if n_disk[-1].isnumeric():
                            self.bk_lvm['PVS'][i]['pv_name'] = pv['pv_name'].replace(o_disk, f"{n_disk}p")
                        else:
                            self.bk_lvm['PVS'][i]['pv_name'] = pv['pv_name'].replace(o_disk, n_disk)

                        self.bk_lvm['PVS'][i]['parent'] = pv['parent'].replace(o_disk, n_disk)
                i += 1

        # If there are luks devices, map any disk that needs it.
        if self.bk_misc.get('luks', ''):
            p = None
            for dev in self.bk_misc['luks']:
                if o_disk.split('/')[-1] == search("([a-z]+)", dev.split('/')[-1]).group():
                    p = search("([0-9]+)", dev.split('/')[-1]).group()
                    if p:
                        self.bk_misc['luks'][f"{n_disk}{p}"] = self.bk_misc['luks'].pop(dev)
                        self.log.debug(f"recover: map_disk: luks: od:{o_disk} nd:{n_disk} p:{p}")
                        break

            # If the header file exist, rename it to match n_disk.
            luks_header = f"/facts/luks/{o_disk.split('/')[-1]}{p}.backup"
            if exists(luks_header) and p:
                move(luks_header, f"/facts/luks/{n_disk.split('/')[-1]}{p}.backup")
                self.log.debug(f"recover: map_disk: luks: luks_header:{luks_header}")

    def mnt_bk_mount(self):
        """
        If the backup location type isn't rsync, then mount bk_mount in the tmp directory.
        """
        if not self.opts.backup_archive:
            if self.cfg.boot_type == "usb" and self.cfg.bk_location_type == "usb":
                # Since we use LiveOS it mounts the partition up,
                # so just use that instead of another mount point.
                self.tmp_bk_mnt = "/run/initramfs/live"
            elif self.cfg.boot_type == "iso" and self.cfg.bk_location_type == "iso":
                # Since we use LiveOS it mounts the partition up,
                # so just use that instead of another mount point.
                self.tmp_bk_mnt = "/run/initramfs/live"
            elif self.cfg.bk_location_type == "rsync":
                self.tmp_bk_mnt = None
            else:
                # Mount bk_mount, which is where the backup archive
                # will be stored later on.
                if self.cfg.bk_mount_opts:
                    ret = mount(self.cfg.bk_mount, self.tmp_bk_mnt, opts=self.cfg.bk_mount_opts)
                else:
                    ret = mount(self.cfg.bk_mount, self.tmp_bk_mnt)

                # If the mount fails exit, and print the mount error.
                if ret.returncode:
                    self.log.error(f" Failed mounting {self.cfg.bk_mount} due to {ret.stderr.decode().strip()}")
                    raise MountError()
                else:
                    self.log.info(f"Successfully mounted {self.cfg.bk_mount} at {self.tmp_bk_mnt}")
                    self.bk_mounted = True

            self.log.debug(f"recover: mnt_bk_mount: boot_type:{self.cfg.boot_type} "
                           f"bk_location_type:{self.cfg.bk_location_type} tmp_bk_mnt:{self.tmp_bk_mnt}")
        else:
            self.log.debug("recover: mnt_bk_mount: Skipping mounting, since backup archive arg was passed.")

    def mnt_restored_rootfs(self):
        """
        Loop through the bk_mnts, and mount up the restored mounts
        to /mnt/rootfs, so that the backup archive can be restored.
        """
        # Loop through the backed up mp's, and mount them up.
        for mnt in self.bk_mnts:
            # We can skip swaps for the restore.
            if "SWAP" not in mnt:
                m = self.bk_mnts[mnt]
                mp = f"{self.tmp_rootfs_dir}{mnt}"

                # If the mp is a subdirectory create it before trying to mnt.
                if not isdir(mp):
                    self.log.debug(f"recover: mnt_restored_rootfs: Creating {mp} directory since it doesn't exist.")
                    makedirs(mp)

                    # Set the context on the directory before mounting, on a test box I hit an issue being
                    # able to log in. After bind mounting / and relabeling the directories that were unlabeled_t,
                    # the issue disappeared. So any time a directory is created set the proper context.
                    if mnt == "/boot":
                        chcon(mp, "system_u:object_r:boot_t:s0")
                    elif mnt == "/home":
                        chcon(mp, "system_u:object_r:home_root_t:s0")
                    elif mnt == "/mnt":
                        chcon(mp, "system_u:object_r:mnt_t:s0")
                    elif mnt == "/opt":
                        chcon(mp, "system_u:object_r:usr_t:s0")
                    elif mnt == "/tmp":
                        chcon(mp, "system_u:object_r:tmp_t:s0")
                    elif mnt == "/usr":
                        chcon(mp, "system_u:object_r:usr_t:s0")
                    elif mnt == "/var":
                        chcon(mp, "system_u:object_r:var_t:s0")

                self.log.info(f"  Mounting {mp}")

                # First check if md raid device, if so mount via the /dev/md/x in case the /dev/mdX changed.
                if m['type'].startswith("raid") and m['md_devname']:
                    ret = mount(m['md_devname'], mp)
                else:
                    ret = mount(m['path'], mp)

                # If the mount fails exit, and print the mount error.
                if ret.returncode:
                    stderr = ret.stderr.decode()
                    if "already mounted" not in stderr:
                        self.log.error(f" Failed running {ret.args} due to {stderr}")
                        raise MountError()

    def restore_bootloader(self, bootloader_disk):
        """
        Perform either a grub2-install or set the boot order via efibootmgr.

        Args:
            bootloader_disk (str): Disk that will be booted from.
        """
        # Store the iso's root fd, so it can exit the chroot.
        rroot = o_open("/", O_RDONLY)

        tmpfs_mnts = ['dev', 'sys', 'proc', 'sys/firmware/efi/efivars']
        # Mount self.tmpfs mount points needed by grub2-install inside the chroot directory.
        for m in tmpfs_mnts:
            if "efi" in m and not self.bk_misc['uefi']:
                continue

            ret = mount(f"/{m}", f"{self.tmp_rootfs_dir}/{m}", opts="bind")
            if ret.returncode:
                self.log.error(f" Failed running {ret.args}, stderr: {ret.stderr.decode()}")
                raise MountError()

        # Chroot into the restored rootfs to reinstall grub2.
        chroot(self.tmp_rootfs_dir)

        if self.bk_misc['uefi']:
            if "Fedora" in self.bk_misc['distro']:
                distro = "fedora"
            elif "Red Hat" in self.bk_misc['distro'] or "Oracle" in self.bk_misc['distro']:
                distro = "redhat"
            elif "CentOS" in self.bk_misc['distro']:
                distro = "centos"
            elif "AlmaLinux" in self.bk_misc['distro']:
                distro = "almalinux"
            elif "Rocky Linux" in self.bk_misc['distro']:
                distro = "rocky"
            elif "openSUSE" in self.bk_misc['distro']:
                distro = "opensuse"
            else:
                distro = self.bk_misc['distro'].lower()

            if "suse" in distro:
                shim = "shim.efi"
            else:
                if "aarch64" in self.bk_misc['arch']:
                    shim = "shimaa64.efi"
                else:
                    shim = "shimx64.efi"

            run_cmd(['/usr/sbin/efibootmgr', '-v', '-c', '-d', bootloader_disk, '-p', '1', '-l',
                     f"\\EFI\\{distro}\\{shim}", '-L', self.bk_misc['distro_pretty']])

        else:
            # Reinstall the bootloader on the recovered disk.
            if "ppc64le" in self.bk_misc['arch']:
                run_cmd(['/usr/sbin/grub2-install', '-v', f"{bootloader_disk}1"])
            elif "s390x" in self.bk_misc['arch']:
                run_cmd(['/usr/sbin/zipl', '-V'])
            else:
                run_cmd(['/usr/sbin/grub2-install', '-v', bootloader_disk])

        # Cd back to the rroot fd, then chroot back out.
        chdir(rroot)
        chroot('.')

        # Clean up tmpfs mounts from earlier.
        for m in tmpfs_mnts:
            if "efi" in m and not self.bk_misc['uefi']:
                continue

            umount(f"{self.tmp_rootfs_dir}/{m}")

    def selinux_check(self):
        """
        Check if selinux was enabled on the server when backed up,
        if so create the /.autorelabel file to trigger a relabel on boot.
        """
        if self.bk_misc.get('selinux_enabled', ''):
            self.log.info("Setting selinux to relabel on first boot")

            # Create the /.autorelabel file.
            open(f"{self.tmp_rootfs_dir}/.autorelabel", 'a').close()

            # Set the proper context on tmp mounts. This is because they will not get labeled before the tmpfs is
            # mounted over them, so a relabel will not fix the issue. This can cause issues with anything that
            # bind mounts / somewhere. I hit this issue with dbus failing to start due to an avc denial that
            # occurred on /run/systemd/unit-root/dev.
            chcon(join(self.tmp_rootfs_dir, "dev"), "system_u:object_r:device_t:s0")
            chcon(join(self.tmp_rootfs_dir, "proc"), "system_u:object_r:proc_t:s0")
            chcon(join(self.tmp_rootfs_dir, "run"), "system_u:object_r:var_run_t:s0")
            chcon(join(self.tmp_rootfs_dir, "sys"), "system_u:object_r:sysfs_t:s0")

    def umount_active_mnts(self):
        """
        Un-mount anything mounted under /mnt/rootfs, this is in case we're running
        after a failed execution, so we don't hit any errors about formatting/re-mounting.
        """
        ret = umount(self.tmp_rootfs_dir, recursive=True)
        if ret.returncode and "not mounted" not in ret.stderr.decode():
            self.log.error(f" The command {ret.args} returned in error: {ret.stderr.decode()}")
            raise MountError()

    def main(self):
        """
        The main function of the class that calls everything.
        """
        # Check for active mnts.
        self.umount_active_mnts()

        # Mount bk_mount if needed.
        self.mnt_bk_mount()

        # Handle any added excludes from the cfg file.
        self.handle_disk_excludes()
        self.handle_vg_excludes()

        try:
            if not self.opts.restore_only:
                rc_part_disks = []

                # Grab any bk_vgs.
                bk_vgs = self.bk_misc.get('bk_vgs', '')

                # Compare the disks, and map if necessary.
                self.cmp_disks()

                # Deactivate any vgs before doing anything.
                if bk_vgs:
                    deactivate_vgs()

                # Loop through the disks keys, and check if the disk match, if not add
                # to the rc_parts_disks to be re-partitioned.
                for d in self.bk_disks.keys():
                    if not self.cmp_disk_layout(d, d, self.facts):
                        rc_part_disks.append(d)

                # Check if any disk need partition scheme recovered, if they do, then
                # recover the disk's partition table from the backup info.
                if rc_part_disks:
                    self.log.info("Starting disk partition recreation")
                    parted = Parted()

                    # Loop through the dict, and restore the partitions on all the disk.
                    for d in rc_part_disks:
                        self.log.info(f"  Re-partitioning {d}")
                        parted.recreate_disk(self.bk_disks[d], d)

                # If md_info in bk_misc, then check the md arrays.
                if self.bk_misc.get('md_info', False):
                    self.log.info("Starting MD raid check")
                    md_check(self.facts.udev_ctx, self.bk_misc['md_info'])

                # If luks in bk_misc, then check if it was on a partition.
                if self.bk_misc.get('luks', False):
                    self.log.info("Starting Luks check for encrypted partitions")
                    for dev in self.bk_misc['luks']:
                        if "part" in self.bk_misc['luks'][dev]['type']:
                            luks_check(self.facts.udev_ctx, self.bk_misc['luks'], dev)

                # Check if the bk_vgs match or if they need recovering.
                if bk_vgs:
                    self.log.info("Starting LVM check")
                    rc_lvm = RecoveryLVM(self.facts, self.bk_mnts, self.bk_lvm)
                    rc_lvm.lvm_check(bk_vgs)

                # If luks in bk_misc, then check if it was on a lvm device.
                if self.bk_misc.get('luks', False):
                    self.log.info("Starting Luks check for encrypted lvms")
                    for dev in self.bk_misc['luks']:
                        if "lvm" in self.bk_misc['luks'][dev]['type']:
                            luks_check(self.facts.udev_ctx, self.bk_misc['luks'], dev)

                # Now format all the fs.
                self.log.info("Starting filesystem restoring")
                for mnt in self.bk_mnts:
                    m = self.bk_mnts[mnt]
                    if m['type'].startswith("raid") and m['md_devname']:
                        dev = m['md_devname']
                    else:
                        dev = m['path']

                    fmt_fs(dev, m['fs_uuid'], m['fs_label'], m['fs_type'])

                self.log.info("Starting to mount the restored filesystems")
            else:
                self.cmp_disks()
                self.log.info("Starting to mount the filesystems")

            # Mount the restored rootfs to /mnt/rootfs, to restore backup on.
            self.mnt_restored_rootfs()

            if self.cfg.bk_location_type == "rsync":
                self.log.info("Restoring backup using rsync, this could take a while, please be patient")
                rsync(self.cfg, self.opts, self.facts)
            else:
                # Set the backup archive depending on if it's specified via an arg or not.
                if self.opts.backup_archive:
                    if isfile(self.opts.backup_archive):
                        backup_archive = self.opts.backup_archive
                    else:
                        self.log.error("The specified backup archive isn't a valid file.")
                        raise GeneralError()
                else:
                    backup_archive = join(self.tmp_bk_mnt,
                                          f"{self.bk_misc['hostname'].split('.')[0]}/"
                                          f"{self.cfg.bk_archive_prefix}.tar.gz")

                self.log.info("Restoring backup using tar, this could take a while, please be patient")
                restore_tar(self.tmp_rootfs_dir, backup_archive)

            self.log.info("Restoring the bootloader")
            if self.bk_misc['uefi']:
                bl_disk = self.grab_bootloader_disk("/boot/efi")
            else:
                bl_disk = self.grab_bootloader_disk("/boot")

            # If there isn't a /boot or /boot/efi, then search for /.
            if not bl_disk:
                bl_disk = self.grab_bootloader_disk("")

            self.log.debug(f"recover: main: bl_disk: {bl_disk}")
            self.restore_bootloader(bl_disk)

            self.selinux_check()

            # Set the permission on the restored / depending
            # on the distro after everything is done.
            if "openSUSE" in self.bk_misc['distro']:
                chmod(self.tmp_rootfs_dir, 0o755)
            else:
                chmod(self.tmp_rootfs_dir, 0o555)

        except (Exception, KeyboardInterrupt, RunCMDError):
            # Call cleanup before exiting.
            self.cleanup()

            # Log the full exception, then exit.
            self.log.exception("Caught exception while running main handler.")
            exit(1)

        self.cleanup()

        # If post scripts are configured, execute them now.
        if self.cfg.rc_post_script:
            self.log.info("Executing configured post script(s)")
            for script in self.cfg.rc_post_script:
                run_cmd(script)

        self.log.info("Restoration Finished, the restored system is mounted under /mnt/rootfs!")

        exit(0)

# vim:set ts=4 sw=4 et:
