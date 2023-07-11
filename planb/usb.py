import logging

from glob import glob
from os import makedirs, rmdir, uname
from os.path import exists, join
from shutil import copy2

from jinja2 import Environment, FileSystemLoader

from planb.distros import LiveOS, prep_rootfs, customize_rootfs_debian, customize_rootfs_rh, customize_rootfs_suse
from planb.exceptions import MountError, RunCMDError
from planb.fs import fmt_fs
from planb.utils import dev_from_file, is_block, mount, rand_str, run_cmd, udev_trigger, umount


def fmt_usb(device):
    """
    Format the usb to be bootable and have the proper label on the device for booting.

    Args:
        device (str): USB device name.
    """
    import pyudev

    from platform import machine

    from planb.facts import grub_prefix
    from planb.parted import Parted

    # Query the arch and set the udev context.
    arch = machine()
    udev_ctx = pyudev.Context()
    logger = logging.getLogger('pbr')

    # Prompt to make sure the correct device is chosen to format.
    confirmation = input(f"Are you sure you want to format {device} this will wipe it it, type YES if so: ")

    if dev_from_file(udev_ctx, device).get('ID_BUS', '') == "usb" and confirmation == "YES":
        p = Parted()
        if exists("/sys/firmware/efi"):
            p.create_uefi_usb(device)
        elif "ppc64le" in arch:
            logger.info("Wiping the device")
            # Wipe the disk, otherwise the grub install will complain about it not being empty.
            run_cmd(['/usr/bin/dd', 'bs=5M', 'count=1', 'if=/dev/zero', f"of={device}"])

            logger.info("Starting to partition the device")
            p.create_prep_usb(device)
        else:
            logger.info("Starting to partition the device")
            p.create_legacy_usb(device)
        logger.info("Partitioning complete")

        # Apparently the system take a second to recognize the new partition,
        # so if it doesn't exist query udev on the device again.
        if not is_block(f"{device}1"):
            logger.debug("usb: fmt_usb: Partition not found yet, so query udev on the device again.")
            dev_from_file(udev_ctx, device)

        uuid = f"{rand_str(8, 1)}-{rand_str(4, 1)}-{rand_str(4, 1)}-{rand_str(4, 1)}-{rand_str(12, 1)}"
        if exists("/sys/firmware/efi"):
            fmt_fs(f"{device}1", rand_str(8, True), "PBR-EFI", "vfat")
            fmt_fs(f"{device}2", uuid.lower(), "PLANBRECOVER-USB", "ext4")
            logger.info("Formatting complete")
        elif "ppc64le" in arch:
            from tempfile import mkdtemp

            fmt_fs(f"{device}2", uuid.lower(), "PLANBRECOVER-USB", "ext4")
            logger.info("Formatting complete")

            # Create a tmp dir to mount the usb on, so grub2 can be installed.
            tmp_dir = mkdtemp(prefix="usb.")
            ret = mount(f"{device}2", tmp_dir)
            if ret.returncode:
                stderr = ret.stderr.decode()
                if "already mounted" not in stderr:
                    logger.error(f" Failed running {ret.args} due to {stderr}")
                    raise MountError()

            # Go ahead and install grub2 on the usb device, I don't think grub needs
            # to be installed every time a backup is created, so it makes sense to
            # just do it here once.
            ret = run_cmd([f'{grub_prefix()}-install', '-v', '--target=powerpc-ieee1275', f"--boot-directory={tmp_dir}",
                           f"{device}1"], ret=True)
            if ret.returncode:
                logger.error(f" The command {ret.args} returned in error: {ret.stderr.decode()}")

                # Clean up if there is an error running grub install.
                ret2 = umount(tmp_dir)
                rmdir(tmp_dir)
                if ret2.returncode:
                    logger.error(f" The command {ret2.args} returned in error: {ret2.stderr.decode()}")

                raise RunCMDError()

            # Clean everything up.
            umount(tmp_dir)
            rmdir(tmp_dir)
            logger.info("Grub2 install complete")
        else:
            from tempfile import mkdtemp

            fmt_fs(f"{device}1", uuid.lower(), "PLANBRECOVER-USB", "ext4")
            logger.info("Formatting complete")

            # Create a tmp dir to mount the usb on, so grub2 can be installed.
            tmp_dir = mkdtemp(prefix="usb.")
            ret = mount(f"{device}1", tmp_dir)
            if ret.returncode:
                stderr = ret.stderr.decode()
                if "already mounted" not in stderr:
                    logger.error(f" Failed running {ret.args} due to {stderr}")
                    raise MountError()

            # Go ahead and install grub2 on the usb device, I don't think grub needs
            # to be installed every time a backup is created, so it makes sense to
            # just do it here once.
            ret = run_cmd([f'{grub_prefix()}-install', '-v', f"--boot-directory={tmp_dir}", f"{device}"], ret=True)
            if ret.returncode:
                logger.error(f" The command {ret.args} returned in error: {ret.stderr.decode()}")

                # Clean up if there is an error running grub install.
                ret2 = umount(tmp_dir)
                rmdir(tmp_dir)
                if ret2.returncode:
                    logger.error(f" The command {ret2.args} returned in error: {ret2.stderr.decode()}")

                raise RunCMDError()

            # Clean everything up.
            umount(tmp_dir)
            rmdir(tmp_dir)
            logger.info("Grub2 install complete")
    else:
        logger.error("Either device isn't a usb or you didn't type YES in all caps.")
        exit(1)


class USB(object):
    def __init__(self, cfg, facts, tmp_dir):
        self.log = logging.getLogger('pbr')
        self.cfg = cfg
        self.facts = facts

        self.label_name = "PLANBRECOVER-USB"
        self.tmp_dir = tmp_dir
        self.tmp_rootfs_dir = join(tmp_dir, "rootfs")
        self.tmp_usbfs_dir = join(tmp_dir, "usbfs")
        self.tmp_usbfs_boot_dir = join(tmp_dir, "usbfs/boot")
        self.tmp_efi_dir = join(tmp_dir, "usbfs/boot/EFI/BOOT")
        self.tmp_syslinux_dir = join(tmp_dir, "usbfs/boot/syslinux")
        self.tmp_share_dir = join(tmp_dir, "/usr/share/planb")

        udev_trigger()

    def prep_uefi(self, efi_distro, efi_file, memtest):
        """
        Prep the usb to work for uefi.

        Args:
            efi_distro (str): EFI distro path name.
            efi_file (str): The efi file location.
            memtest (bool): Whether to include memtest or not.
        """
        self.log.info("Mounting EFI directory")
        ret = mount("/dev/disk/by-label/PBR-EFI", self.tmp_usbfs_boot_dir)
        if ret.returncode:
            self.log.error(f"{ret.args} returned the following error: {ret.stderr.decode()}")
            raise MountError()

        makedirs(self.tmp_efi_dir, exist_ok=True)

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
        with open(join(self.tmp_efi_dir, "grub.cfg"), "w+") as f:
            # For aarch64 it doesn't use the normal efi commands in grub.cfg.
            if self.facts.arch == "aarch64":
                f.write(grub_cfg.render(
                    facts=self.facts,
                    linux_cmd="linux",
                    initrd_cmd="initrd",
                    location="/boot/syslinux/",
                    label_name=self.label_name,
                    boot_args=self.cfg.rc_kernel_args,
                    efi_distro=efi_distro,
                    efi=1
                ))
            else:
                f.write(grub_cfg.render(
                    facts=self.facts,
                    linux_cmd="linuxefi",
                    initrd_cmd="initrdefi",
                    location="/boot/syslinux/",
                    label_name=self.label_name,
                    boot_args=self.cfg.rc_kernel_args,
                    memtest=memtest,
                    efi_distro=efi_distro,
                    efi_file=efi_file,
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

        self.log.info("Un-mounting EFI directory")
        umount(self.tmp_usbfs_boot_dir)

    def prep_usb(self):
        """
        Copy the needed files for syslinux in the tmp working directory.
        """
        self.log.info("Mounting USB boot directory")
        makedirs(self.tmp_usbfs_dir)
        ret = mount("/dev/disk/by-label/PLANBRECOVER-USB", self.tmp_usbfs_dir)
        if ret.returncode:
            self.log.error(f"{ret.args} returned the following error: {ret.stderr.decode()}")
            raise MountError()

        memtest = 0
        makedirs(self.tmp_syslinux_dir, exist_ok=True)

        # Grab the uuid of the fs that /boot is located on, if
        # /boot isn't a partition then it returns the uuid of /.
        boot_uuid = self.facts.mnts.get("/boot", self.facts.mnts.get("/", {})).get("fs_uuid")

        # Since syslinux is only available on x86_64, check the arch.
        # Then copy all the needed syslinux files to the tmp dir.
        if self.facts.arch == "x86_64":
            # If the memtest86+ pkg isn't installed, skip adding that boot option.
            if glob("/boot/memtest*"):
                copy2(glob("/boot/memtest*")[0], join(self.tmp_syslinux_dir, "memtest.bin"))
                memtest = 1

            if not self.facts.uefi:
                # Generate a grub.cfg.
                env = Environment(loader=FileSystemLoader("/usr/share/planb/"))
                grub_cfg = env.get_template("grub.cfg")
                with open(join(self.tmp_dir, "usbfs/grub2/grub.cfg"), "w+") as f:
                    f.write(grub_cfg.render(
                        facts=self.facts,
                        linux_cmd="linux",
                        initrd_cmd="initrd",
                        location="/boot/syslinux/",
                        label_name=self.label_name,
                        boot_args=self.cfg.rc_kernel_args,
                        memtest=memtest,
                        boot_uuid=boot_uuid,
                        efi=0
                    ))
        elif self.facts.arch == "ppc64le":
            # Generate a grub.cfg.
            env = Environment(loader=FileSystemLoader("/usr/share/planb/"))
            grub_cfg = env.get_template("grub.cfg")
            with open(join(self.tmp_dir, "usbfs/grub2/grub.cfg"), "w+") as f:
                f.write(grub_cfg.render(
                    facts=self.facts,
                    linux_cmd="linux",
                    initrd_cmd="initrd",
                    location="/boot/syslinux/",
                    label_name=self.label_name,
                    boot_args=self.cfg.rc_kernel_args,
                    boot_uuid=boot_uuid,
                    efi=0
                ))

        # Copy the current running kernel's vmlinuz file to the tmp dir.
        if glob(f"/boot/Image-{uname().release}"):
            copy2(glob(f"/boot/Image-{uname().release}")[0], join(self.tmp_syslinux_dir, "vmlinuz"))
        elif glob(f"/boot/vmlinu*-{uname().release}"):
            copy2(glob(f"/boot/vmlinu*-{uname().release}")[0], join(self.tmp_syslinux_dir, "vmlinuz"))

        if self.facts.uefi:
            self.prep_uefi(self.facts.efi_distro, self.facts.efi_file, memtest)

    def mkusb(self):
        """
        Main function of the class.
        """
        self.log.info("Prepping the USB")
        self.prep_usb()

        liveos = LiveOS(self.cfg, self.facts, self.tmp_dir)
        liveos.create()

        self.log.info("Customizing the copied files to work in the USB environment")
        prep_rootfs(self.cfg, self.tmp_dir, self.tmp_rootfs_dir)

        # Set OS specific customizations.
        if self.facts.is_suse_based():
            customize_rootfs_suse(self.tmp_rootfs_dir)
        elif self.facts.is_debian_based():
            customize_rootfs_debian(self.tmp_rootfs_dir)
        else:
            customize_rootfs_rh(self.tmp_rootfs_dir)

        self.log.info("Creating the USB's LiveOS IMG")
        liveos.create_squashfs()

        self.log.info("Un-mounting USB directory")
        umount(self.tmp_usbfs_dir)
