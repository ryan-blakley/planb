import logging

from glob import glob
from os import chdir, makedirs, stat, uname
from os.path import exists, join
from shutil import copy2

from jinja2 import Environment, FileSystemLoader

from planb.distros import LiveOS, customize_rootfs_debian, customize_rootfs_rh, customize_rootfs_suse, prep_rootfs
from planb.exceptions import MountError
from planb.fs import fmt_fs
from planb.utils import mount, rand_str, run_cmd, umount


class ISO(object):
    def __init__(self, cfg, facts, tmp_dir):
        """
        A class for creating a bootable ISO, for recovering from a backup.

        Args:
            cfg (obj): Object with cfg values.
            facts (obj): The facts object.
            tmp_dir (str): The tmp working directory.
        """
        self.log = logging.getLogger('pbr')
        self.cfg = cfg
        self.facts = facts

        self.label_name = "PLANBRECOVER-ISO"
        self.tmp_dir = tmp_dir
        self.tmp_rootfs_dir = join(tmp_dir, "rootfs")
        self.tmp_boot_grub_dir = join(tmp_dir, "isofs/boot/grub")
        self.tmp_boot_grub2_dir = join(tmp_dir, "isofs/boot/grub2")
        self.tmp_efi_dir = join(tmp_dir, "isofs/EFI/BOOT")
        self.tmp_images_dir = join(tmp_dir, "isofs/images")
        self.tmp_isofs_dir = join(tmp_dir, "isofs")
        self.tmp_isolinux_dir = join(tmp_dir, "isofs/isolinux")
        self.tmp_ppc_dir = join(tmp_dir, "isofs/ppc")
        self.tmp_share_dir = join(tmp_dir, "/usr/share/planb")

    def create_iso(self):
        """
        Generate a bootable live ISO.
        """
        # Change the isofs directory, and create the output directory.
        chdir(self.tmp_isofs_dir)
        makedirs(join("/var/lib/pbr", "output"), exist_ok=True)

        # Set the bk_dir and create it if it doesn't exist, it should only need to
        # be created when the backup is being included on the iso itself.
        bk_dir = join(join(self.tmp_dir, "backup"), uname().nodename.split('.')[0])
        makedirs(bk_dir, exist_ok=True)

        # Set the outputted iso filename.
        iso_file = f"/var/lib/pbr/output/{self.cfg.rc_iso_prefix}.iso"

        if exists('/usr/bin/genisoimage'):
            cmd = "/usr/bin/genisoimage"
        else:
            cmd = "/usr/bin/mkisofs"

        # isohybrid is only available on x86_64, so set too none to begin with.
        cmd_isohybrid = None

        if self.facts.uefi and self.facts.arch == "x86_64":
            if "SUSE" in self.facts.distro:
                cmd_mkisofs = [cmd, '-vv', '-o', iso_file, '-b', 'isolinux/isolinux.bin', '-J', '-R', '-l', '-c',
                               'isolinux/boot.cat', '-no-emul-boot', '-boot-load-size', '4', '-boot-info-table',
                               '-eltorito-alt-boot', '-eltorito-platform', 'efi', '-eltorito-boot',
                               'images/efiboot.img', '-no-emul-boot', '-graft-points', '-V', self.label_name, '.']
            else:
                cmd_mkisofs = [cmd, '-vv', '-o', iso_file, '-b', 'isolinux/isolinux.bin', '-J', '-R', '-l', '-c',
                               'isolinux/boot.cat', '-no-emul-boot', '-boot-load-size', '4', '-boot-info-table',
                               '-eltorito-alt-boot', '-e', 'images/efiboot.img', '-no-emul-boot', '-graft-points',
                               '-V', self.label_name, '.']

            cmd_isohybrid = ['/usr/bin/isohybrid', '-v', '-u', iso_file]
        elif self.facts.arch == "aarch64":
            if "SUSE" in self.facts.distro:
                cmd_mkisofs = [cmd, '-vv', '-o', iso_file, '-J', '-r', '-l', '-eltorito-alt-boot', '-eltorito-platform',
                               'efi', '-eltorito-boot', 'images/efiboot.img', '-no-emul-boot', '-graft-points', '-V',
                               self.label_name, '.']
            else:
                cmd_mkisofs = [cmd, '-vv', '-o', iso_file, '-J', '-r', '-l', '-eltorito-alt-boot', '-e',
                               'images/efiboot.img', '-no-emul-boot', '-graft-points', '-V', self.label_name, '.']
        elif self.facts.arch == "ppc64le":
            cmd_mkisofs = [cmd, '-vv', '-o', iso_file, '-U', '-chrp-boot', '-J', '-R', '-iso-level', '3',
                           '-graft-points', '-V', self.label_name, '.']
        elif self.facts.arch == "s390x":
            with open(join(self.tmp_images_dir, "initrd.addrsize"), "wb") as f:
                from struct import pack

                data = pack(">iiii", 0, int("0x02000000", 16), 0,
                            stat(join(self.tmp_isolinux_dir, "initramfs.img")).st_size)
                f.write(data)

            run_cmd(['/usr/bin/mk-s390image', 'isolinux/vmlinuz', 'images/cdboot.img', '-r', 'isolinux/initramfs.img',
                     '-p', 'images/cdboot.prm'])

            cmd_mkisofs = [cmd, '-vv', '-o', iso_file, '-b', 'images/cdboot.img', '-J', '-R', '-l', '-c',
                           'isolinux/boot.cat', '-no-emul-boot', '-boot-load-size', '4', '-V', self.label_name,
                           '-graft-points', '.']
        else:
            cmd_mkisofs = [cmd, '-vv', '-o', iso_file, '-b', 'isolinux/isolinux.bin', '-J', '-R', '-l', '-c',
                           'isolinux/boot.cat', '-no-emul-boot', '-boot-load-size', '4', '-boot-info-table', '-V',
                           self.label_name, '-graft-points', '.']

            cmd_isohybrid = ['/usr/bin/isohybrid', '-v', iso_file]

        # Execute the mkisofs/genisoimage, and isohybrid command if set.
        run_cmd(cmd_mkisofs)
        if cmd_isohybrid:
            run_cmd(cmd_isohybrid)

        # Copy the iso locally under /var/lib/pbr.
        copy2(f"/var/lib/pbr/output/{self.cfg.rc_iso_prefix}.iso", bk_dir)

    def prep_uefi(self, memtest, efi_distro, efi_file):
        """
        Prep the isofs working directory to work for uefi.

        Args:
            memtest (bool): Whether to include memtest or not.
            efi_distro (str): EFI distro path name.
            efi_file (str): The efi file location.
        """
        def cp_files():
            """
            Copy the efi files onto the efiboot.img and to the tmp working directory.
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

            # If a bootx86.efi or bootaa64.efi file doesn't exist
            # create one by copying the shim or grub efi files.
            if not glob(join(self.tmp_efi_dir, "boot*.efi")) and not glob(join(self.tmp_efi_dir, "BOOT*.EFI")):
                for shim in ['shimx64.efi', 'shim.efi', 'grubx64.efi', 'shimaa64.efi', 'grubaa64.efi']:
                    if exists(join(self.tmp_efi_dir, shim)):
                        boot_efi = "bootx64.efi"
                        if "aarch64" in self.facts.arch:
                            boot_efi = "bootaa64.efi"

                        copy2(join(self.tmp_efi_dir, shim), join(self.tmp_efi_dir, boot_efi))
                        break

            env = Environment(loader=FileSystemLoader("/usr/share/planb/"))
            grub_cfg = env.get_template("grub.cfg")
            with open(join(self.tmp_efi_dir, "grub.cfg"), "w+") as cfg:
                # For aarch64 it doesn't use the normal efi commands in grub.cfg.
                if self.facts.arch == "aarch64":
                    cfg.write(grub_cfg.render(
                        facts=self.facts,
                        linux_cmd="linux",
                        initrd_cmd="initrd",
                        location="/isolinux/",
                        label_name=self.label_name,
                        boot_args=self.cfg.rc_kernel_args,
                        efi_distro=efi_distro,
                        efi=1
                    ))
                else:
                    cfg.write(grub_cfg.render(
                        facts=self.facts,
                        linux_cmd="linuxefi",
                        initrd_cmd="initrdefi",
                        location="/isolinux/",
                        label_name=self.label_name,
                        boot_args=self.cfg.rc_kernel_args,
                        efi_distro=efi_distro,
                        efi_file=efi_file,
                        memtest=memtest,
                        efi=1
                    ))

            if "mageia" in efi_distro and self.facts.arch == "x86_64":
                run_cmd([f'{self.facts.grub_prefix}-mkimage', '--verbose', '-O', 'x86_64-efi', '-p', '/EFI/BOOT', '-o',
                         join(self.tmp_efi_dir, "bootx64.efi"), 'iso9660', 'ext2', 'fat', 'f2fs', 'jfs', 'reiserfs',
                         'xfs', 'part_apple', 'part_bsd', 'part_gpt', 'part_msdos', 'all_video', 'font', 'gfxterm',
                         'gfxmenu', 'png', 'boot', 'chain', 'configfile', 'echo', 'gettext', 'linux', 'linux32', 'ls',
                         'search', 'test', 'videoinfo', 'reboot', 'gzio', 'gfxmenu', 'gfxterm', 'serial'])

            if self.facts.is_debian_based() and self.facts.arch == "aarch64":
                run_cmd([f'{self.facts.grub_prefix}-mkimage', '--verbose', '-O', 'arm64-efi', '-p', '/EFI/BOOT', '-o',
                         join(self.tmp_efi_dir, "bootaa64.efi"), 'search', 'iso9660', 'configfile', 'normal', 'tar',
                         'part_msdos', 'part_gpt', 'ext2', 'fat', 'xfs', 'linux', 'boot', 'chain', 'ls', 'reboot',
                         'all_video', 'gzio', 'gfxmenu', 'gfxterm', 'serial'])

        makedirs(self.tmp_efi_dir)
        makedirs(self.tmp_images_dir)

        # Create blank img file.
        with open(join(self.tmp_images_dir, "efiboot.img"), "wb") as f:
            f.seek(15728640 - 1)
            f.write(b"\0")

        # Format and mount the img file.
        fmt_fs(join(self.tmp_images_dir, "efiboot.img"), rand_str(8, True), "PBR-EFI", "vfat")
        ret = mount(join(self.tmp_images_dir, "efiboot.img"), self.tmp_isofs_dir)
        if ret.returncode:
            self.log.error(f"{ret.args} returned the following error: {ret.stderr.decode()}")
            raise MountError()

        # Create the efi directories, and copy the efi files.
        makedirs(self.tmp_efi_dir)
        try:
            cp_files()
        except Exception:
            umount(self.tmp_isofs_dir)

        # Unmount the img file, and copy the efi files for the iso file itself.
        umount(self.tmp_isofs_dir)
        cp_files()

    def prep_iso(self):
        """
        Copy the needed files to create the iso in the tmp working directory.
        """
        memtest = 0
        makedirs(self.tmp_isolinux_dir)

        # Since syslinux is only available on x86_64, check the arch.
        # Then copy all the needed isolinux files to the tmp dir.
        if self.facts.arch == "x86_64":
            if exists("/usr/lib/syslinux/isolinux.bin"):
                # Magia location
                chdir("/usr/lib/syslinux/")
                copy2("isolinux.bin", self.tmp_isolinux_dir)
            elif exists("/usr/lib/ISOLINUX/"):
                # Debian location
                chdir("/usr/lib/ISOLINUX/")
                copy2("isolinux.bin", self.tmp_isolinux_dir)
                chdir("/usr/lib/syslinux/modules/bios/")
            else:
                # RH based location
                chdir("/usr/share/syslinux/")
                copy2("isolinux.bin", self.tmp_isolinux_dir)

            copy2("chain.c32", self.tmp_isolinux_dir)
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
            with open(join(self.tmp_isofs_dir, "isolinux.cfg"), "w+") as f:
                f.write(isolinux_cfg.render(
                    facts=self.facts,
                    location="/isolinux/",
                    label_name=self.label_name,
                    boot_args=self.cfg.rc_kernel_args,
                    memtest=memtest
                ))

            # Copy the splash image over.
            copy2(join(self.tmp_share_dir, "splash.png"), self.tmp_isolinux_dir)
        elif self.facts.arch == "ppc64le":
            makedirs(self.tmp_boot_grub_dir)
            makedirs(self.tmp_ppc_dir)

            # Grab the uuid of the fs that /boot is located on, if
            # /boot isn't a partition then it returns the uuid of /.
            boot_uuid = self.facts.mnts.get("/boot", self.facts.mnts.get("/", {})).get("fs_uuid")

            # Create the bootinfo.txt file.
            with open(join(self.tmp_ppc_dir, "bootinfo.txt"), "w") as f:
                f.writelines("<chrp-boot>\n")
                f.writelines("<description>grub 2.00</description>\n")
                f.writelines("<os-name>grub 2.00</os-name>\n")
                f.writelines("<boot-script>boot &device;:\\boot\\grub\\core.elf</boot-script>\n")
                f.writelines("</chrp-boot>\n")

            # Generate a custom grub image file for booting iso's.
            run_cmd([f'{self.facts.grub_prefix}-mkimage', '--verbose', '-O', 'powerpc-ieee1275', '-p', '()/boot/grub',
                     '-o', join(self.tmp_boot_grub_dir, "core.elf"), 'search', 'iso9660', 'configfile', 'normal', 'tar',
                     'part_msdos', 'part_gpt', 'ext2', 'xfs', 'linux', 'boot', 'ls', 'reboot', 'all_video', 'gzio',
                     'gfxmenu', 'gfxterm', 'serial'])

            # Generate a grub.cfg.
            env = Environment(loader=FileSystemLoader("/usr/share/planb/"))
            grub_cfg = env.get_template("grub.cfg")
            with open(join(self.tmp_boot_grub_dir, "grub.cfg"), "w+") as f:
                f.write(grub_cfg.render(
                    facts=self.facts,
                    linux_cmd="linux",
                    initrd_cmd="initrd",
                    location="/isolinux/",
                    label_name=self.label_name,
                    boot_args=self.cfg.rc_kernel_args,
                    boot_uuid=boot_uuid,
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
            with open(join(self.tmp_isofs_dir, "generic.ins"), "w") as f:
                f.writelines("isolinux/vmlinuz 0x00000000\n")
                f.writelines("isolinux/initramfs.img 0x02000000\n")
                f.writelines("images/genericdvd.prm 0x00010480\n")
                f.writelines("images/initrd.addrsize 0x00010408\n")

        # Copy the current running kernel's vmlinuz file to the tmp dir.
        if glob(f"/boot/Image-{uname().release}"):
            copy2(glob(f"/boot/Image-{uname().release}")[0], join(self.tmp_isolinux_dir, "vmlinuz"))
        elif glob(f"/boot/vmlinu*-{uname().release}"):
            copy2(glob(f"/boot/vmlinu*-{uname().release}")[0], join(self.tmp_isolinux_dir, "vmlinuz"))

        if self.facts.uefi:
            self.prep_uefi(memtest, self.facts.efi_distro, self.facts.efi_file)

    def mkiso(self):
        """
        Main function of the class.
        """
        self.log.info("Prepping isolinux")
        self.prep_iso()

        liveos = LiveOS(self.cfg, self.facts, self.tmp_dir)
        liveos.create()

        self.log.info("Customizing the copied files to work in the ISO environment")
        prep_rootfs(self.cfg, self.tmp_dir, self.tmp_rootfs_dir)

        # Set OS specific customizations.
        if self.facts.is_suse_based():
            customize_rootfs_suse(self.tmp_rootfs_dir)
        elif self.facts.is_debian_based():
            customize_rootfs_debian(self.tmp_rootfs_dir)
        else:
            customize_rootfs_rh(self.tmp_rootfs_dir)

        self.log.info("Creating the ISO's LiveOS IMG")
        liveos.create_squashfs()

        # If the bk location isn't set to iso, then create the iso. Otherwise,
        # skip this step since the iso needs to be created after the backup
        # archive is done.
        if not self.cfg.bk_location_type == "iso":
            self.log.info("Creating the ISO file")
            self.create_iso()
