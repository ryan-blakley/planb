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
from glob import glob
from jinja2 import Environment, FileSystemLoader
from os import chdir, makedirs, stat, uname
from os.path import exists, join
from shutil import copy2

from .distros import LiveOS, prep_rootfs, rh_customize_rootfs, suse_customize_rootfs
from .exceptions import MountError
from .fs import fmt_fs
from .utils import mk_cdboot, mount, rand_str, run_cmd, umount


class ISO(object):
    def __init__(self, cfg, facts, tmp_dir):
        """
        A class for creating a bootable ISO, for recovering from a backup.
        :param cfg: Object with cfg values.
        :param facts: The facts object.
        :param tmp_dir: The tmp working directory.
        """
        self.log = logging.getLogger('pbr')
        self.cfg = cfg
        self.facts = facts

        self.label_name = "PLANBRECOVER-ISO"
        self.tmp_dir = tmp_dir
        self.tmp_rootfs_dir = join(tmp_dir, "rootfs")
        self.tmp_boot_dir = join(tmp_dir, "isofs/boot/grub")
        self.tmp_efi_dir = join(tmp_dir, "isofs/EFI/BOOT")
        self.tmp_images_dir = join(tmp_dir, "isofs/images")
        self.tmp_isolinux_dir = join(tmp_dir, "isofs/isolinux")
        self.tmp_ppc_dir = join(tmp_dir, "isofs/ppc")
        self.tmp_share_dir = join(tmp_dir, "/usr/share/planb")

    def create_iso(self):
        """
        Generate a bootable live ISO.
        :return:
        """
        chdir(join(self.tmp_dir, "isofs"))

        # Set the bk_dir and create it if it's doesn't exist, it should only need to
        # be created when the backup is being included on the iso itself.
        bk_dir = join(join(self.tmp_dir, "backup"), uname().nodename.split('.')[0])
        makedirs(bk_dir, exist_ok=True)

        if exists('/usr/bin/genisoimage'):
            cmd = "/usr/bin/genisoimage"
        else:
            cmd = "/usr/bin/mkisofs"

        # isohybrid is only available on x86_64, so set to none to begin with.
        cmd_isohybrid = None

        if self.facts.uefi and self.facts.arch == "x86_64":
            if "SUSE" in self.facts.distro:
                cmd_mkisofs = [cmd, '-vv', '-o', join(bk_dir, f"{self.cfg.rc_iso_prefix}.iso"), '-b',
                               'isolinux/isolinux.bin', '-J', '-R', '-l', '-c', 'isolinux/boot.cat', '-no-emul-boot',
                               '-boot-load-size', '4', '-boot-info-table', '-eltorito-alt-boot', '-eltorito-platform',
                               'efi', '-eltorito-boot', 'images/efiboot.img', '-no-emul-boot', '-graft-points', '-V',
                               self.label_name, '.']
            else:
                cmd_mkisofs = [cmd, '-vv', '-o', join(bk_dir, f"{self.cfg.rc_iso_prefix}.iso"), '-b',
                               'isolinux/isolinux.bin', '-J', '-R', '-l', '-c', 'isolinux/boot.cat', '-no-emul-boot',
                               '-boot-load-size', '4', '-boot-info-table', '-eltorito-alt-boot', '-e',
                               'images/efiboot.img', '-no-emul-boot', '-graft-points', '-V', self.label_name, '.']

            cmd_isohybrid = ['/usr/bin/isohybrid', '-v', '-u', join(bk_dir, f"{self.cfg.rc_iso_prefix}.iso")]
        elif self.facts.arch == "aarch64":
            if "SUSE" in self.facts.distro:
                cmd_mkisofs = [cmd, '-vv', '-o', join(bk_dir, f"{self.cfg.rc_iso_prefix}.iso"), '-J', '-r', '-l',
                               '-eltorito-alt-boot', '-eltorito-platform', 'efi', '-eltorito-boot',
                               'images/efiboot.img', '-no-emul-boot', '-graft-points', '-V', self.label_name, '.']
            else:
                cmd_mkisofs = [cmd, '-vv', '-o', join(bk_dir, f"{self.cfg.rc_iso_prefix}.iso"), '-J', '-r', '-l',
                               '-eltorito-alt-boot', '-e', 'images/efiboot.img', '-no-emul-boot', '-graft-points',
                               '-V', self.label_name, '.']
        elif self.facts.arch == "ppc64le":
            cmd_mkisofs = [cmd, '-vv', '-o', join(bk_dir, f"{self.cfg.rc_iso_prefix}.iso"), '-U', '-chrp-boot', '-J',
                           '-R', '-iso-level', '3', '-graft-points', '-V', self.label_name, '.']
        elif self.facts.arch == "s390x":
            with open(join(self.tmp_images_dir, "initrd.addrsize"), "wb") as f:
                from struct import pack

                data = pack(">iiii", 0, int("0x02000000", 16), 0,
                            stat(join(self.tmp_isolinux_dir, "initramfs.img")).st_size)
                f.write(data)

            mk_cdboot("isolinux/vmlinuz", "isolinux/initramfs.img", "images/cdboot.prm", "images/cdboot.img")

            cmd_mkisofs = [cmd, '-vv', '-o', join(bk_dir, f"{self.cfg.rc_iso_prefix}.iso"), '-b', 'images/cdboot.img',
                           '-J', '-R', '-l', '-c', 'isolinux/boot.cat', '-no-emul-boot', '-boot-load-size', '4', '-V',
                           self.label_name, '-graft-points', '.']
        else:
            cmd_mkisofs = [cmd, '-vv', '-o', join(bk_dir, f"{self.cfg.rc_iso_prefix}.iso"), '-b',
                           'isolinux/isolinux.bin', '-J', '-R', '-l', '-c', 'isolinux/boot.cat', '-no-emul-boot',
                           '-boot-load-size', '4', '-boot-info-table', '-V', self.label_name, '-graft-points', '.']

            cmd_isohybrid = ['/usr/bin/isohybrid', '-v', join(bk_dir, f"{self.cfg.rc_iso_prefix}.iso")]

        # Execute the mkisofs/genisoimage, and isohybrid command if set.
        run_cmd(cmd_mkisofs)
        if cmd_isohybrid:
            run_cmd(cmd_isohybrid)

        # Copy the iso locally under /var/lib/pbr.
        makedirs(join("/var/lib/pbr", "output"), exist_ok=True)
        copy2(join(bk_dir, f"{self.cfg.rc_iso_prefix}.iso"), f"/var/lib/pbr/output/{self.cfg.rc_iso_prefix}.iso")

    def prep_uefi(self, memtest):
        """
        Prep the isofs working directory to work for uefi.
        :return:
        """
        def cp_files():
            """
            Copy the efi files onto the efiboot.img and to the tmp working directory.
            :return:
            """
            if glob("/boot/efi/EFI/BOOT/BOOT*.EFI"):
                copy2(glob("/boot/efi/EFI/BOOT/BOOT*.EFI")[0], self.tmp_efi_dir)
            elif glob("/boot/efi/EFI/boot/boot*.efi"):
                copy2(glob("/boot/efi/EFI/boot/boot*.efi")[0], self.tmp_efi_dir)

            if glob("/boot/efi/EFI/[a-z]*/BOOT*.CSV"):
                copy2(glob("/boot/efi/EFI/[a-z]*/BOOT*.CSV")[0], self.tmp_efi_dir)
            elif glob("/boot/efi/EFI/[a-z]*/boot*.csv"):
                copy2(glob("/boot/efi/EFI/[a-z]*/boot*.csv")[0], self.tmp_efi_dir)

            # Loop through any efi file under /boot/efi/EFI/<distro>/, and copy.
            for efi in glob("/boot/efi/EFI/[a-z]*/*.efi"):
                # Don't copy the fallback efi files, because it will cause it not to boot.
                if "fbx64" not in efi and "fallback" not in efi:
                    copy2(efi, self.tmp_efi_dir)

            # Set the local distro and efi_file variable for the grub.cfg file.
            if "Fedora" in self.facts.distro:
                distro = "fedora"

                if "aarch64" in self.facts.arch:
                    efi_file = "shimaa64.efi"
                else:
                    efi_file = "shimx64.efi"
            elif "Red Hat" in self.facts.distro or "Oracle" in self.facts.distro:
                distro = "redhat"

                if "aarch64" in self.facts.arch:
                    efi_file = "shimaa64.efi"
                else:
                    efi_file = "shimx64.efi"
            elif "CentOS" in self.facts.distro:
                distro = "centos"

                if "aarch64" in self.facts.arch:
                    efi_file = "shimaa64.efi"
                else:
                    efi_file = "shimx64.efi"
            elif "SUSE" in self.facts.distro:
                distro = "opensuse"
                efi_file = "shim.efi"
            else:
                distro = "redhat"

                if "aarch64" in self.facts.arch:
                    efi_file = "shimaa64.efi"
                else:
                    efi_file = "shimx64.efi"

            env = Environment(loader=FileSystemLoader("/usr/share/planb/"))
            grub_cfg = env.get_template("grub.cfg")
            with open(join(self.tmp_efi_dir, "grub.cfg"), "w+") as cfg:
                # For aarch64 it doesn't use the normal efi commands in grub.cfg.
                if self.facts.arch == "aarch64":
                    cfg.write(grub_cfg.render(
                        hostname=self.facts.hostname,
                        linux_cmd="linux",
                        initrd_cmd="initrd",
                        location="/isolinux/",
                        label_name=self.label_name,
                        boot_args=self.cfg.rc_kernel_args,
                        arch=self.facts.arch,
                        distro=distro,
                        iso=1,
                        efi=1
                    ))
                else:
                    cfg.write(grub_cfg.render(
                        hostname=self.facts.hostname,
                        linux_cmd="linuxefi",
                        initrd_cmd="initrdefi",
                        location="/isolinux/",
                        label_name=self.label_name,
                        boot_args=self.cfg.rc_kernel_args,
                        arch=self.facts.arch,
                        distro=distro,
                        efi_file=efi_file,
                        secure_boot=self.facts.secure_boot,
                        memtest=memtest,
                        iso=1,
                        efi=1
                    ))

        makedirs(self.tmp_efi_dir)
        makedirs(self.tmp_images_dir)

        # Create blank img file.
        with open(join(self.tmp_images_dir, "efiboot.img"), "wb") as f:
            f.seek(15728640 - 1)
            f.write(b"\0")

        # Format and mount the img file.
        fmt_fs(join(self.tmp_images_dir, "efiboot.img"), rand_str(8, True), "PBR-EFI", "vfat")
        ret = mount(join(self.tmp_images_dir, "efiboot.img"), join(self.tmp_dir, "isofs"))
        if ret.returncode:
            self.log.error(f"{ret.args} returned the following error: {ret.stderr.decode()}")
            raise MountError()

        # Create the efi directories, and copy the efi files.
        makedirs(self.tmp_efi_dir)
        try:
            cp_files()
        except Exception:
            umount(join(self.tmp_dir, "isofs"))

        # Unmount the img file, and copy the efi files for the iso file itself.
        umount(join(self.tmp_dir, "isofs"))
        cp_files()

    def prep_iso(self):
        """
        Copy the needed files to create the iso in the tmp working directory.
        :return:
        """
        memtest = 0
        # Make the needed temp directory.
        makedirs(self.tmp_isolinux_dir)

        # Since syslinux is only available on x86_64, check the arch.
        # Then copy all of the needed isolinux files to the tmp dir.
        if self.facts.arch == "x86_64":
            chdir("/usr/share/syslinux/")
            copy2("chain.c32", self.tmp_isolinux_dir)
            copy2("isolinux.bin", self.tmp_isolinux_dir)
            copy2("menu.c32", self.tmp_isolinux_dir)
            copy2("vesamenu.c32", self.tmp_isolinux_dir)

            # The below files are only needed for syslinux v5+ so if the
            # files don't exist don't attempt to copy them.
            if exists("ldlinux.c32"):
                copy2("ldlinux.c32", self.tmp_isolinux_dir)
            if exists("libcom32.c32"):
                copy2("libcom32.c32", self.tmp_isolinux_dir)
            if exists("libmenu.c32"):
                copy2("libmenu.c32", self.tmp_isolinux_dir)
            if exists("libutil.c32"):
                copy2("libutil.c32", self.tmp_isolinux_dir)

            # If the memtest86+ pkg isn't installed, skip adding that boot option.
            if glob("/boot/memtest*"):
                copy2(glob("/boot/memtest*")[0], join(self.tmp_isolinux_dir, "memtest.bin"))
                memtest = 1

            # Write out the isolinux.cfg based on the template file.
            env = Environment(loader=FileSystemLoader("/usr/share/planb/"))
            isolinux_cfg = env.get_template("isolinux.cfg")
            with open(join(join(self.tmp_dir, "isofs"), "isolinux.cfg"), "w+") as f:
                f.write(isolinux_cfg.render(
                    hostname=self.facts.hostname,
                    location="/isolinux/",
                    label_name=self.label_name,
                    boot_args=self.cfg.rc_kernel_args,
                    memtest=memtest
                ))

            # Copy the splash image over.
            copy2(join(self.tmp_share_dir, "splash.png"), self.tmp_isolinux_dir)
        elif self.facts.arch == "ppc64le":
            makedirs(self.tmp_boot_dir)
            makedirs(self.tmp_ppc_dir)

            # Create the bootinfo.txt file.
            with open(join(self.tmp_ppc_dir, "bootinfo.txt"), "w") as f:
                f.writelines("<chrp-boot>\n")
                f.writelines("<description>grub 2.00</description>\n")
                f.writelines("<os-name>grub 2.00</os-name>\n")
                f.writelines("<boot-script>boot &device;:\\boot\\grub\\core.elf</boot-script>\n")
                f.writelines("</chrp-boot>\n")

            # Generate a custom grub image file for booting iso's.
            run_cmd(['/usr/bin/grub2-mkimage', '--verbose', '-O', 'powerpc-ieee1275', '-p', '()/boot/grub', '-o',
                     join(self.tmp_boot_dir, "core.elf"), 'linux', 'normal', 'iso9660'])

            # Generate a grub.cfg.
            env = Environment(loader=FileSystemLoader("/usr/share/planb/"))
            grub_cfg = env.get_template("grub.cfg")
            with open(join(self.tmp_boot_dir, "grub.cfg"), "w+") as f:
                f.write(grub_cfg.render(
                    hostname=self.facts.hostname,
                    linux_cmd="linux",
                    initrd_cmd="initrd",
                    location="/isolinux/",
                    label_name=self.label_name,
                    boot_args=self.cfg.rc_kernel_args,
                    arch=self.facts.arch,
                    iso=1,
                    efi=0
                ))
        elif self.facts.arch == "s390x":
            makedirs(self.tmp_images_dir)
            
            # Set the cmdline arguments for the iso.
            with open(join(self.tmp_images_dir, "cdboot.prm"), "w") as f:
                f.writelines(f"ro root=live:LABEL={self.label_name} rd.live.image selinux=0 "
                             f"{' '.join(self.cfg.rc_kernel_args)}\n")
            with open(join(self.tmp_images_dir, "genericdvd.prm"), "w") as f:
                f.writelines(f"ro root=live:LABEL={self.label_name} rd.live.image selinux=0 "
                             f"{' '.join(self.cfg.rc_kernel_args)}\n")
            with open(join(self.tmp_images_dir, "generic.prm"), "w") as f:
                f.writelines(f"ro root=live:LABEL={self.label_name} rd.live.image selinux=0 "
                             f"{' '.join(self.cfg.rc_kernel_args)}\n")

            # Create the punch file.
            with open(join(self.tmp_images_dir, "redhat.exec"), "w") as f:
                f.writelines("/* */\n")
                f.writelines("'CL RDR'\n")
                f.writelines("'PURGE RDR ALL'\n")
                f.writelines("'SPOOL PUNCH * RDR'\n")
                f.writelines("'PUNCH KERNEL IMG A (NOH'\n")
                f.writelines("'PUNCH GENERIC PRM A (NOH'\n")
                f.writelines("'PUNCH INITRD IMG A (NOH'\n")
                f.writelines("'CH RDR ALL KEEP NOHOLD'\n")
                f.writelines("'I 00C'\n")

            # Create the mapping file.
            with open(join(join(self.tmp_dir, "isofs"), "generic.ins"), "w") as f:
                f.writelines("isolinux/vmlinuz 0x00000000\n")
                f.writelines("isolinux/initramfs.img 0x02000000\n")
                f.writelines("images/genericdvd.prm 0x00010480\n")
                f.writelines("images/initrd.addrsize 0x00010408\n")

        # Copy the current running kernel's vmlinuz file to the tmp dir.
        if glob(f"/boot/Image-{uname().release}"):
            copy2(glob(f"/boot/Image-{uname().release}*")[0], join(self.tmp_isolinux_dir, "vmlinuz"))
        elif glob(f"/boot/vmlinu*-{uname().release}*"):
            copy2(glob(f"/boot/vmlinu*-{uname().release}*")[0], join(self.tmp_isolinux_dir, "vmlinuz"))

        if self.facts.uefi:
            self.prep_uefi(memtest)

    def mkiso(self):
        """
        Main function of the class.
        :return:
        """
        self.log.info("Prepping isolinux")
        self.prep_iso()

        liveos = LiveOS(self.cfg, self.facts, self.tmp_dir)
        liveos.create()

        self.log.info("Customizing the copied files to work in the ISO environment")
        prep_rootfs(self.cfg, self.tmp_dir, self.tmp_rootfs_dir)

        # Set OS specific customizations.
        if "openSUSE" in self.facts.distro:
            suse_customize_rootfs(self.tmp_rootfs_dir)
        else:
            rh_customize_rootfs(self.tmp_rootfs_dir)

        self.log.info("Creating the ISO's LiveOS IMG")
        liveos.create_squashfs()

        # If the bk location isn't set to iso, then create the iso. Otherwise
        # skip this step since the iso needs to be created after the backup
        # archive is done.
        if not self.cfg.bk_location_type == "iso":
            self.log.info("Creating the ISO file")
            self.create_iso()

    """
    def old_create_iso(self):
        # The below pycdlib code works fine for booting without isohybrid and efiboot.img, I tried to get isohybrid
        # to work but even running the isohybrid command on the iso makes it not bootable. So I'm not sure why it's
        # not working, I will occasionally come back and try to get it working, but for now I will just use mkisofs
        # and isohybrid commands as they work perfectly each time.
        # Create ISO object.
        import pycdlib
        iso = pycdlib.PyCdlib()

        # Create a new ISO, and set the label.
        iso.new(interchange_level=3, rock_ridge='1.09', joliet=3, vol_ident='PLANBRECOVER', set_size=1)

        # Add the isolinux dir to the iso.
        iso.add_directory("/ISOLINUX", joliet_path="/isolinux", rr_name="isolinux", file_mode=0o040755)

        chdir(self.tmp_isolinux_dir)
        # Loop through the files, set the path, and add each file to the iso.
        for f in listdir("."):
            path = f"/isolinux/{f}"

            # The kernel file requires 755 perms, so set it correctly.
            if f == "vmlinuz":
                file_mode = 0o100755
            else:
                file_mode = 0o100644

            iso.add_file(join(self.tmp_isolinux_dir, f), iso_path=path.upper(), joliet_path=path, rr_name=f, 
                              file_mode=file_mode)

        # Add the liveos dir, and the squashfs img file.
        iso.add_directory("/LIVEOS", joliet_path="/LiveOS", rr_name="LiveOS", file_mode=0o040755)
        iso.add_file(join(self.tmp_dir, "isofs/LiveOS/squashfs.img"), iso_path="/LIVEOS/SQUASHFS.IMG", 
                     joliet_path="/LiveOS/squashfs.img", rr_name="squashfs.img", file_mode=0o100644)

        if self.facts.uefi:
            iso.add_directory("/IMAGES", joliet_path="/images", rr_name="images", file_mode=0o040755)
            iso.add_file(join(self.tmp_dir, "isofs/images/efiboot.img"), iso_path="/IMAGES/EFIBOOT.IMG", 
                         joliet_path="/images/efiboot.img", rr_name="efiboot.img", file_mode=0o100644)

            iso.add_directory("/EFI", joliet_path="/EFI", rr_name="EFI", file_mode=0o040755)
            iso.add_directory("/EFI/BOOT", joliet_path="/EFI/BOOT", rr_name="BOOT", file_mode=0o040755)

            chdir(join(self.tmp_dir, "isofs/EFI/BOOT"))
            for f in listdir("."):
                path = f"/EFI/BOOT/{f}"
                full_path = join(self.tmp_dir, "isofs/EFI/BOOT")
                iso.add_file(join(full_path, f), iso_path=path.upper(), joliet_path=path, rr_name=f, file_mode=0o100700)

            iso.add_eltorito('/ISOLINUX/ISOLINUX.BIN', bootcatfile='/ISOLINUX/BOOT.CAT', efi=True, boot_info_table=True, 
                             platform_id=0, media_name='noemul', bootable=True)
            iso.add_eltorito('/IMAGES/EFIBOOT.IMG', bootcatfile='/ISOLINUX/BOOT.CAT', efi=True, boot_info_table=True, 
                            platform_id=0, media_name='noemul', bootable=True)
        else:
            # Make the ISO bootable by adding eltorito, then write the iso out.
            iso.add_eltorito('/ISOLINUX/ISOLINUX.BIN', bootcatfile='/ISOLINUX/BOOT.CAT', boot_load_size=4, 
                             boot_load_seg=0, efi=False, boot_info_table=True, platform_id=0, media_name='noemul', 
                             bootable=True)

        #iso.add_isohybrid()
        iso.write(join(join(join(self.tmp_dir, "backup"), uname().nodename.split('.')[0]), "recover.iso"))
        iso.close()
    """

# vim:set ts=4 sw=4 et:
