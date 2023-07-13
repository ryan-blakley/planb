import json
import logging

from os import chdir, listdir, makedirs, remove, rename
from os.path import exists, join
from shutil import copyfile, copytree, rmtree
from tempfile import mkdtemp
from time import strftime

from planb.exceptions import ExistsError, GeneralError, MountError, RunCMDError
from planb.facts import Facts
from planb.iso import ISO
from planb.tar import create_tar
from planb.usb import USB
from planb.utils import dev_from_file, dev_from_name, is_installed, not_in_append, rsync, run_cmd, mount, umount


class Backup(object):
    def __init__(self, opts, cfg):
        """
        The main backup class.

        Args:
            opts: Argparse object.
            cfg: Config file object.
        """
        self.opts = opts
        self.cfg = cfg
        self.facts = Facts()
        self.log = logging.getLogger('pbr')

        self.matched = False
        self.mounted = False
        self.tmp_dir = None
        self.tmp_facts_dir = None
        self.tmp_mount_dir = None
        self.tmp_bk_dir = None
        self.tmp_isofs_dir = None
        self.var_lib = "/var/lib/pbr"

        # Define the immutable excludes.
        self.bk_excludes = ['/dev', '/lost+found', '/proc', '/run', '/sys']
        self.skip_location_types = ['iso', 'rsync']

        # Add the cfg excludes.
        for ex in self.cfg.bk_exclude_paths:
            if ex not in self.bk_excludes:
                self.bk_excludes.append(ex)

        if self.facts.is_suse_based:
            self.nfs_pkg = "nfs-client"
        elif self.facts.is_debian_based:
            self.nfs_pkg = "nfs-common"
        else:
            self.nfs_pkg = "nfs-utils"

    def chk_bk_settings(self):
        t = self.cfg.bk_location_type
        # Need to add a section to check that the remote host is accessible, and
        # has rsync installed, probably can use paramiko and run rpm -q rsync on
        # the remote host to confirm.
        if t == "rsync":
            if not is_installed("rsync"):
                self.log.error(" Backup location type is set to rsync, but rsync isn't installed, please install.")
            else:
                self.tmp_bk_dir = None
        # If saving the backup to the iso, set the tmp_bk_dir under the isofs directory.
        elif t == "iso":
            if not self.opts.backup_only:
                self.log.info("Skipping mounting since the backup will be on the ISO")
                self.tmp_bk_dir = join(self.tmp_isofs_dir, self.facts.hostname.split('.')[0])
                # Create backup dir based on the hostname in the isofs directory.
                makedirs(self.tmp_bk_dir, exist_ok=True)
            else:
                self.log.error("Can't run with --backup-only if the backup_location_type is set to iso.")
                raise GeneralError()
        else:
            # Check if boot type is usb and mkrescue was passed, before mounting.
            if not ("usb" in self.cfg.boot_type.lower() and self.opts.mkrescue):
                if t == "cifs" and not is_installed(f"{t}-utils"):
                    self.log.error(f"Backup location type is set to {t}, but {t}-utils isn't installed, "
                                   "please install.")
                    raise ExistsError()
                    # Since the nfs pkg is named different across distros, just separate it out.
                elif t == "nfs" and not is_installed(self.nfs_pkg):
                    self.log.error(f"Backup location type is set to {t}, but {self.nfs_pkg} isn't installed, "
                                   "please install.")
                    raise ExistsError()

                # Mount bk_mount, which is where the backup archive
                # will be stored later on.
                if self.cfg.bk_mount_opts:
                    ret = mount(self.cfg.bk_mount, self.tmp_mount_dir, opts=self.cfg.bk_mount_opts)
                else:
                    ret = mount(self.cfg.bk_mount, self.tmp_mount_dir)

                if ret.returncode:
                    self.log.error(f"Failed running {ret.args} due to the following. "
                                   f"stderr:{ret.stderr.decode().strip()}")
                    raise MountError()
                else:
                    self.log.info(f"Successfully mounted {self.cfg.bk_mount} at {self.tmp_dir}/backup")
                    self.mounted = True

                    # Set the directory name of where the backup archive and iso will be copied to.
                    self.tmp_bk_dir = join(self.tmp_mount_dir, self.facts.hostname.split('.')[0])
                    # Create backup dir based on the hostname on the mounted fs.
                    makedirs(self.tmp_bk_dir, exist_ok=True)

        self.log.debug(f"backup: chk_bk_settings: tmp_bk_dir:{self.tmp_bk_dir}")

    def cleanup(self, error=0):
        """
        Cleanup by um-mounting the backup mount, so there isn't any hung mounts.

        Args:
            error (bool): Is this being called from a caught exception.
        """
        # Check if error is passed, so it's printed that the un-mount occurred
        # due to an error.
        if error:
            self.log.info("An error was caught, cleaning up before exiting.")

        # Copying the log file to the tmp_bk_dir here so that it gets written
        # potentially before the mount is un-mounted.
        if self.tmp_bk_dir and exists("/var/log/pbr.log"):
            copyfile("/var/log/pbr.log", join(self.tmp_bk_dir, "pbr.log"))

        if self.mounted:
            self.log.info(f"Un-mounting backup location {self.tmp_mount_dir}")
            umount(self.tmp_mount_dir, lazy=True)

        # If keep is passed, warn the user to remove the tmp dir.
        if self.opts.keep:
            self.log.info(f"You should remove the temp directory {self.tmp_dir}")

    def cleanup_bks(self):
        """
        Rotate the old backup archive files, and remove any if needed.
        """
        if exists(join(self.tmp_bk_dir, f"{self.cfg.bk_archive_prefix}.tar.gz")):
            num_bks = []
            times = []

            for b in listdir(self.tmp_bk_dir):
                if b.startswith(f"{self.cfg.bk_archive_prefix}-"):
                    num_bks.append(b)

            for b in num_bks:
                b_splits = b.split("-", 1)
                b_splits = b_splits[-1].split(".")
                times.append(b_splits[0])

            times.sort(reverse=True)
            if len(times) >= self.cfg.num_of_old_backups:
                f = join(self.tmp_bk_dir, f"{self.cfg.bk_archive_prefix}-{times.pop()}.tar.gz")
                self.log.debug(f"backup: cleanup_bks: remove_old_bak: {f}")
                remove(f)

            rename(join(self.tmp_bk_dir, f"{self.cfg.bk_archive_prefix}.tar.gz"),
                   join(self.tmp_bk_dir, f"{self.cfg.bk_archive_prefix}-{strftime('%Y%m%d-%H%M%S')}.tar.gz"))

    def cleanup_disks(self, bk_vgs):
        """
        Remove any disk from facts.disks not used by a mount point.

        Args:
            bk_vgs (list): An array of volume groups being backed up.
        """
        # Create a dict of disk used by mnts.
        bk_disks = []
        rm_disks = []

        # If lvm exist, loop the pvs, and determine which we're restoring.
        if self.facts.lvm.get('PVS', False):
            self.log.debug("backup: cleanup_disks: Checking for pvs to add to bk_disks.")
            for pv in self.facts.lvm['PVS']:
                # If the vg isn't in bk_vgs, skip the pv.
                if pv['vg_name'] not in bk_vgs:
                    self.log.debug(f"backup: cleanup_disks: Skipping {pv['vg_name']}, as it's not in bk_vgs.")
                    continue

                pv_name = pv['pv_name']
                d_type = pv['d_type']

                if pv['md_dev']:
                    for d in self.facts.md_info[pv_name.split('/')[-1]]['devs']:
                        not_in_append(dev_from_name(self.facts.udev_ctx, d).find_parent('block').device_node, bk_disks)
                        self.log.debug(f"backup: cleanup_disks: Appending the parent of {d} to bk_disks.")
                else:
                    if d_type == "disk" and pv_name not in bk_disks:
                        bk_disks.append(pv_name)
                        self.log.debug(f"backup: cleanup_disks: Appending {pv_name} to bk_disks.")
                    elif d_type == "mpath" and pv_name not in bk_disks:
                        bk_disks.append(pv_name)
                        self.log.debug(f"backup: cleanup_disks: Appending {pv_name} to bk_disks.")
                    elif d_type == "part":
                        not_in_append(dev_from_file(self.facts.udev_ctx, pv_name).find_parent('block').device_node,
                                      bk_disks)
                        self.log.debug(f"backup: cleanup_disks: Appending the parent of {pv_name} to bk_disks.")
                    elif d_type == "part-mpath":
                        not_in_append(f"/dev/mapper/{dev_from_file(self.facts.udev_ctx, pv_name)['DM_MPATH']}",
                                      bk_disks)
                        self.log.debug(f"backup: cleanup_disks: Appending the parent of {pv_name} to bk_disks.")

        # Loop through each mp, for any non lvm mp and determine which we're restoring.
        self.log.debug("backup: cleanup_disks: Looping through the mount points to check for non lvm mounts.")
        mnts = self.facts.mnts.copy()
        for mp, info in mnts.items():
            self.log.debug(f"backup: cleanup_disks: Checking mp:{mp} info:{info}")
            # We handle all lvm stuff above, so skip lvm mount points.
            if str(info['type']) == "lvm":
                self.log.debug("backup: cleanup_disks: Skipping due to being type lvm.")
                continue

            # If using usb or local backup type, skip the mount point so the disk aren't captured.
            if mp.startswith(self.tmp_dir):
                self.log.debug("backup: cleanup_disks: Skipping due to being mounted in the tmp dir.")
                continue

            # Check if it has a parent set, if it does check if it exists in bk_exclude_disks, if it doesn't
            # then add it to the bk_disks list. If it does then skip it, and it will be removed below.
            if info['parent'] and info['parent'] not in self.cfg.bk_exclude_disks:
                # Capture the parent for each mp.
                m_p = str(info['parent'])

                if info['md_devname']:
                    self.log.debug("backup: cleanup_disks: Found md_devname, looping through md_info for the devs.")
                    for d in self.facts.md_info[info['md_devname'].split('/')[-1]]['devs']:
                        self.log.debug(f"backup: cleanup_disks: Found d:{d}")
                        not_in_append(dev_from_name(self.facts.udev_ctx, d).find_parent('block').device_node, bk_disks)
                else:
                    self.log.debug(f"backup: cleanup_disks: Appending m_p:{m_p} if not in bk_disk:{bk_disks}")
                    not_in_append(m_p, bk_disks)
            else:
                self.log.debug(f"backup: cleanup_disks: skipping mp:{mp} due to it being "
                               f"in {self.cfg.bk_exclude_disks}")

        # Capture a list of disk not used in mnts, or were skipped due to being excluded.
        for d in self.facts.disks.keys():
            if d not in bk_disks:
                self.log.debug(f"backup: cleanup_disks: {d} is not in bk_disks, adding to rm_disks.")
                rm_disks.append(d)

        # Remove the unused disks from the facts disks.
        for d in rm_disks:
            self.facts.disks.pop(d)

    def cmp_mnts_fstab(self):
        """
        Compare the current mount points and fstab for any differences, this will
        hopefully help prevent any can't boots after restoration due to fstab entries.
        """
        mp = []
        with open("/etc/fstab", "r") as f:
            lines = f.readlines()

        lines = [line.strip() for line in lines]

        # Loop over the lines and grab the mount points set in the fstab.
        for line in lines:
            if line and not line.startswith("#") and not line.startswith("none") and not line.startswith("tmpfs")\
                    and not line.startswith("/dev/sr"):
                if line.split()[1].startswith("/"):
                    mp.append(line.split()[1])

        # Now compare and remove any mount points that match.
        for mnt in self.facts.mnts:
            if mnt in mp:
                mp.remove(mnt)

        # If there is anymore entries in mp, throw an error.
        if len(mp) > 0:
            self.log.debug(f"backup: cmp_mnt_fstab: mp: {mp}")
            self.log.error("""There is a discrepancy between the mount points and the fstab, please correct the """
                           """fstab and try again. This is here to help prevent a can't boot after restoration.""")
            raise GeneralError()

    def create_tmp_dirs(self):
        """
        Create subdirectories in the tmp dir that are needed.
        """
        # Set the tmp dir vars for use by other functions.
        self.tmp_facts_dir = join(self.tmp_dir, "facts")
        self.tmp_mount_dir = join(self.tmp_dir, "backup")
        self.tmp_isofs_dir = join(self.tmp_dir, "isofs")

        # Create the required subdirectories.
        makedirs(self.tmp_facts_dir)
        makedirs(self.tmp_mount_dir)

        if not self.facts.is_debian_based:
            makedirs(join(self.tmp_dir, "rootfs"))

        if self.cfg.bk_location_type not in self.skip_location_types:
            makedirs(self.tmp_isofs_dir)

    def dump_facts(self):
        """
        Dump all the server facts to json files, for use when recovering
        the system. These will be included in the iso later on.
        """
        self.log.info("Dumping facts")

        # Determine which volume groups need to be restored.
        bk_vgs = self.get_bk_vgs()

        # Cleanup the disk list before dumping.
        self.cleanup_disks(bk_vgs)

        # Dump all the individual vars to their own json file.
        misc = {
            "uefi": self.facts.uefi,
            "distro": self.facts.distro,
            "distro_pretty": self.facts.distro_pretty,
            "arch": self.facts.arch,
            "hostname": self.facts.hostname,
            "selinux_enabled": self.facts.selinux_enabled,
            "selinux_enforcing": self.facts.selinux_enforcing,
            "bk_vgs": bk_vgs,
            "md_info": self.facts.md_info,
            "luks": self.facts.luks,
            "grub_prefix": self.facts.grub_prefix
        }
        if self.facts.uefi:
            misc.update({"efi_distro": self.facts.efi_distro, "efi_file": self.facts.efi_file})

        # Write out the facts to the tmp iso dir.
        with open(join(self.tmp_facts_dir, "disks.json"), 'w') as f:
            json.dump(self.facts.disks, f, indent=4)
            self.log.debug(f" backup: dump_facts: disks:\n{json.dumps(self.facts.disks, indent=4)}")
        with open(join(self.tmp_facts_dir, "lvm.json"), 'w') as f:
            json.dump(self.facts.lvm, f, indent=4)
            self.log.debug(f" backup: dump_facts: lvm:\n{json.dumps(self.facts.lvm, indent=4)}")
        with open(join(self.tmp_facts_dir, "mnts.json"), 'w') as f:
            json.dump(self.facts.mnts, f, indent=4)
            self.log.debug(f" backup: dump_facts: mnts:\n{json.dumps(self.facts.mnts, indent=4)}")
        with open(join(self.tmp_facts_dir, "misc.json"), 'w') as f:
            json.dump(misc, f, indent=4)
            self.log.debug(f" backup: dump_facts: misc:\n{json.dumps(misc, indent=4)}")

        # If rootfs is on lvm, then dump the lvm metadata to /facts/vgcfg/."
        if self.facts.lvm_installed:
            makedirs(join(self.tmp_facts_dir, "vgcfg"))
            run_cmd(['/usr/sbin/vgcfgbackup', '-v', '-f', f"{join(self.tmp_facts_dir, 'vgcfg')}/%s"])

        if not self.opts.check_facts:
            # Copy the facts to /var/lib/pbr/facts/ used for checking for layout changes.
            # Do this before dumping the luks header, so that it's not copied on disk.
            if exists(join(self.var_lib, "facts")):
                rmtree(join(self.var_lib, "facts"))

            copytree(self.tmp_facts_dir, join(self.var_lib, "facts"))

        # If luks detected, then dump the headers to files to be included in the iso.
        if self.facts.luks:
            makedirs(join(self.tmp_facts_dir, "luks"))
            for dev in self.facts.luks:
                run_cmd(['/usr/sbin/cryptsetup', '-v', 'luksHeaderBackup', dev, '--header-backup-file',
                         f"{join(join(self.tmp_facts_dir, 'luks'), dev.split('/')[-1])}.backup"])

    def get_bk_vgs(self):
        """
        Gather a list of volume groups needing to be checked/restored during recovery. Also remove
        any mount points that were part of a vg/disk that was excluded.
        """
        # Copy the facts mnts, so entries can be removed if need be.
        mnts = self.facts.mnts.copy()
        bk_vgs = []

        # Loop through each mp, to capture list of vgs.
        for mnt, info in mnts.items():
            # If the mp isn't a lv or luks skip it.
            if (info['type'] == "lvm" or info['type'] == "crypt") and not info['parent']:
                vg = info['vg']

                # If the vg is in the excludes list, remove the mp and continue.
                if vg in self.cfg.bk_exclude_vgs:
                    self.facts.mnts.pop(mnt)
                    # If the vg has two pvs, check and remove
                    # the vg if it's in bk_vgs already.
                    if vg in bk_vgs:
                        bk_vgs.remove(vg)
                    continue

                # Check if there are any bk_exclude_disks set, before running the below.
                if self.cfg.bk_exclude_disks:
                    for pv in self.facts.lvm['PVS']:
                        self.log.debug(f"backup: get_bk_vgs: Checking if {pv} is in the excludes.")
                        # Check for the mp's vg, and that the parent isn't null.
                        if pv['vg_name'] == vg and pv['parent']:
                            # Check if the parent is in the exclude list, if so remove the mp and continue.
                            # Also append the vg to the bk_exclude_vgs list, in case the vg has multiple pvs.
                            if pv['parent'] in self.cfg.bk_exclude_disks:
                                self.log.debug(f"backup: get_bk_vgs: Excluding {vg} it's parent is in the excludes.")
                                self.cfg.bk_exclude_vgs.append(vg)
                                self.facts.mnts.pop(mnt)
                                continue
                        # Next if the parent is null just use the pv_name, this is for pvs that aren't partitioned.
                        elif pv['vg_name'] == vg and not pv['parent']:
                            # Check if the pv_name is in the exclude list, if so remove the mp and continue.
                            # Also append the vg to the bk_exclude_vgs list, in case the vg has multiple pvs.
                            if pv['pv_name'] in self.cfg.bk_exclude_disks:
                                self.log.debug(f"backup: get_bk_vgs: Excluding {vg} it's pv_name is in the excludes.")
                                self.cfg.bk_exclude_vgs.append(vg)
                                self.facts.mnts.pop(mnt)
                                continue

                not_in_append(vg, bk_vgs)

        return bk_vgs

    def start(self):
        """
        Run the backup tasks from here so there isn't duplicate
        code in the main function above.
        """
        # Create the needed dirs in the tmp dir.
        self.create_tmp_dirs()
        iso = None

        if not self.opts.backup_only:
            # Before dumping facts, compare the mnts and fstab.
            self.cmp_mnts_fstab()

            # Dump all the facts gathered to json files in the tmp dir.
            self.dump_facts()

            if self.opts.check_facts:
                self.log.info("Checking if the facts have changed")
                import filecmp

                # Compare the 4 facts files to see if they're different.
                match, mismatch, errors = filecmp.cmpfiles(self.tmp_facts_dir, join(self.var_lib, "facts"),
                                                           ['disks.json', 'lvm.json', 'mnts.json', 'misc.json'])

                # If no mismatch or errors, set matched to true, if there is any
                # log the mismatch and errors to the log file.
                if not mismatch and not errors:
                    self.matched = True
                else:
                    self.log.debug(f"backup: start: check_facts: mismatched: {mismatch} errors: {errors}")

                self.cleanup()
                return

        # Check if any addition pkgs need to be installed,
        # and mount the bk_mount if needed.
        self.chk_bk_settings()

        if not self.opts.backup_only:
            if self.cfg.boot_type == "iso":
                iso = ISO(self.cfg, self.facts, self.tmp_dir)
                iso.mkiso()
            elif self.cfg.boot_type == "usb":
                usb = USB(self.cfg, self.facts, self.tmp_dir)
                usb.prep_usb()
                usb.mkusb()
            else:
                self.log.error("Please set a valid boot_type in the cfg file.")
                raise ExistsError()

        if not self.opts.mkrescue:
            if self.cfg.bk_location_type == "rsync":
                self.log.info("Creating backup using rsync, this could take a while, please be patient")
                rsync(self.cfg, self.opts, self.facts, bk_excludes=self.bk_excludes)
            else:
                if exists(join(self.tmp_bk_dir, f"{self.cfg.bk_archive_prefix}.tar.gz")):
                    self.cleanup_bks()

                self.log.info("Creating backup archive, this could take a while, please be patient")
                create_tar(self.cfg, self.bk_excludes, self.tmp_bk_dir)

        # Create the iso after the backup archive is created
        # if the backup location is set to iso.
        if self.cfg.bk_location_type == "iso":
            self.log.info("Creating the ISO file")
            iso.create_iso()

        self.cleanup()

    def main(self):
        """
        Main function, it creates the tmp directory and then hands off
        to the start function to prevent duplicate code.
        """
        # Catch any exception and so umount can be run, otherwise, the tmp dir function
        # will wipe all the files on the nfs mount, also the nfs mount would be left hanging.
        try:
            # Create a temporary working directory.
            self.tmp_dir = mkdtemp(prefix="pbr.")
            self.log.info(f"Created temporary directory {self.tmp_dir}")

            # Now add the temporary directory to the excludes.
            self.bk_excludes.append(self.tmp_dir)

            # Let the games begin.
            self.start()

            # By default, remove the tmp dir after running, to prevent filling up /tmp.
            # Otherwise, if -k is passed don't remove the directory, this is used for debugging.
            if not self.opts.keep:
                rmtree(self.tmp_dir)
        except (Exception, KeyboardInterrupt, RunCMDError):
            # Change the cwd to /tmp to avoid any umount errors.
            chdir("/tmp")

            # Call cleanup before exiting.
            self.cleanup(error=1)

            # Log the full exception, then exit.
            self.log.exception("Caught an exception in the main handler.")
            exit(1)

        # For check facts, we need to set the proper exit code.
        if self.opts.check_facts:
            if not self.matched:
                self.log.info("Facts have changed.")
                exit(1)
            else:
                self.log.info("Facts matched.")
                exit(0)
        else:
            self.log.info("Finished backing everything up")
