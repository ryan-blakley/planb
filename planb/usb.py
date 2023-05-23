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
from os import makedirs, rmdir, uname
from os.path import exists, join
from shutil import copy2

from jinja2 import Environment, FileSystemLoader

from planb.distros import LiveOS, prep_rootfs, rh_customize_rootfs, suse_customize_rootfs
from planb.exceptions import MountError, RunCMDError
from planb.fs import fmt_fs, grab_mnt_info
from planb.utils import dev_from_file,  is_block, mount, rand_str, run_cmd, udev_trigger, umount


def fmt_usb(device):
    """
    Format the usb to be bootable and have the proper label on the device for booting.
    :param device: USB device name.
    :return:
    """
    import pyudev
    from platform import machine
    from .parted import Parted

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
            ret = run_cmd(['/usr/sbin/grub2-install', '-v', '--target=powerpc-ieee1275', f"--boot-directory={tmp_dir}",
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
            ret = run_cmd(['/usr/sbin/grub2-install', '-v', f"--boot-directory={tmp_dir}", f"{device}"], ret=True)
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

    def prep_uefi(self, distro, efi_file, memtest):
        """
        Prep the usb to work for uefi.
        :return:
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

        env = Environment(loader=FileSystemLoader("/usr/share/planb/"))
        grub_cfg = env.get_template("grub.cfg")
        with open(join(self.tmp_efi_dir, "grub.cfg"), "w+") as f:
            # For aarch64 it doesn't use the normal efi commands in grub.cfg.
            if self.facts.arch == "aarch64":
                f.write(grub_cfg.render(
                    hostname=self.facts.hostname,
                    linux_cmd="linux",
                    initrd_cmd="initrd",
                    location="/boot/syslinux/",
                    label_name=self.label_name,
                    boot_args=self.cfg.rc_kernel_args,
                    arch=self.facts.arch,
                    distro=distro,
                    iso=0,
                    efi=1
                ))
            else:
                f.write(grub_cfg.render(
                    hostname=self.facts.hostname,
                    linux_cmd="linuxefi",
                    initrd_cmd="initrdefi",
                    location="/boot/syslinux/",
                    label_name=self.label_name,
                    boot_args=self.cfg.rc_kernel_args,
                    arch=self.facts.arch,
                    memtest=memtest,
                    distro=distro,
                    efi_file=efi_file,
                    secure_boot=self.facts.secure_boot,
                    iso=0,
                    efi=1
                ))

        self.log.info("Un-mounting EFI directory")
        umount(self.tmp_usbfs_boot_dir)

    def prep_usb(self):
        """
        Copy the needed files for syslinux in the tmp working directory.
        :return:
        """
        memtest = 0
        self.log.info("Mounting USB boot directory")
        makedirs(self.tmp_usbfs_dir)
        ret = mount("/dev/disk/by-label/PLANBRECOVER-USB", self.tmp_usbfs_dir)
        if ret.returncode:
            self.log.error(f"{ret.args} returned the following error: {ret.stderr.decode()}")
            raise MountError()

        # Make the needed temp directory.
        makedirs(self.tmp_syslinux_dir, exist_ok=True)

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

        # Grab the uuid of the fs that /boot is located on.
        if grab_mnt_info(self.facts, "/boot"):
            boot_uuid = grab_mnt_info(self.facts, "/boot")['fs_uuid']
        else:
            boot_uuid = grab_mnt_info(self.facts, "/")['fs_uuid']

        # Since syslinux is only available on x86_64, check the arch.
        # Then copy all of the needed syslinux files to the tmp dir.
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
                        hostname=self.facts.hostname,
                        linux_cmd="linux",
                        initrd_cmd="initrd",
                        location="/boot/syslinux/",
                        label_name=self.label_name,
                        boot_args=self.cfg.rc_kernel_args,
                        arch=self.facts.arch,
                        distro=distro,
                        memtest=memtest,
                        boot_uuid=boot_uuid,
                        iso=0,
                        efi=0
                    ))
        elif self.facts.arch == "ppc64le":
            # Generate a grub.cfg.
            env = Environment(loader=FileSystemLoader("/usr/share/planb/"))
            grub_cfg = env.get_template("grub.cfg")
            with open(join(self.tmp_dir, "usbfs/grub2/grub.cfg"), "w+") as f:
                f.write(grub_cfg.render(
                    hostname=self.facts.hostname,
                    linux_cmd="linux",
                    initrd_cmd="initrd",
                    location="/boot/syslinux/",
                    label_name=self.label_name,
                    boot_args=self.cfg.rc_kernel_args,
                    arch=self.facts.arch,
                    distro=distro,
                    iso=0,
                    efi=0
                ))

        # Copy the current running kernel's vmlinuz file to the tmp dir.
        if glob(f"/boot/Image-{uname().release}"):
            copy2(glob(f"/boot/Image-{uname().release}*")[0], join(self.tmp_syslinux_dir, "vmlinuz"))
        elif glob(f"/boot/vmlinu*-{uname().release}*"):
            copy2(glob(f"/boot/vmlinu*-{uname().release}*")[0], join(self.tmp_syslinux_dir, "vmlinuz"))

        if self.facts.uefi:
            self.prep_uefi(distro, efi_file, memtest)

    def mkusb(self):
        """
        Main function of the class.
        :return:
        """
        self.log.info("Prepping the USB")
        self.prep_usb()

        liveos = LiveOS(self.cfg, self.facts, self.tmp_dir)
        liveos.create()

        self.log.info("Customizing the copied files to work in the USB environment")
        prep_rootfs(self.cfg, self.tmp_dir, self.tmp_rootfs_dir)

        # Set OS specific customizations.
        if "openSUSE" in self.facts.distro:
            suse_customize_rootfs(self.tmp_rootfs_dir)
        else:
            rh_customize_rootfs(self.tmp_rootfs_dir)

        self.log.info("Creating the USB's LiveOS IMG")
        liveos.create_squashfs()

        self.log.info("Un-mounting USB directory")
        umount(self.tmp_usbfs_dir)

# vim:set ts=4 sw=4 et:
