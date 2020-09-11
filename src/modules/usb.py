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
from os import chdir, makedirs, uname
from os.path import exists, isfile, join
from shutil import copy2

from .distros import rh_customize_rootfs, RHLiveOS
from .exceptions import MountError
from .fs import fmt_fs
from .logger import log
from .utils import dev_from_file, is_block, mount, rand_str, run_cmd, umount


def fmt_usb(device):
    """
    Format the usb to be bootable and have the proper label on the device for booting.
    :param device: USB device name.
    :return:
    """
    import pyudev
    from .parted import Parted

    udev_ctx = pyudev.Context()
    confirmation = input(f"Are you sure you want to format {device} this will wipe it it, type YES if so: ")
    if dev_from_file(udev_ctx, device).get('ID_BUS', '') == "usb" and confirmation == "YES":
        p = Parted()
        if exists("/sys/firmware/efi"):
            p.create_uefi_usb(device)
        else:
            p.create_legacy_usb(device)
        log("Partitioning complete")

        # Apparently the system take a second to recognize the new partition,
        # so if it doesn't exist query udev on the device again.
        if not is_block(f"{device}1"):
            logging.debug("usb: fmt_usb: Partition not found yet, so query udev on the device again.")
            dev_from_file(device)

        uuid = f"{rand_str(8, 1)}-{rand_str(4, 1)}-{rand_str(4, 1)}-{rand_str(4, 1)}-{rand_str(12, 1)}"
        if exists("/sys/firmware/efi"):
            fmt_fs(f"{device}1", rand_str(8, True), "PBR-EFI", "vfat")
            fmt_fs(f"{device}2", uuid.lower(), "PLANBRECOVER-USB", "ext4")
            log("Formatting complete")
        else:
            fmt_fs(f"{device}1", uuid.lower(), "PLANBRECOVER-USB", "ext4")
            log("Formatting complete")

            # Write the mbr.bin to the beginning of the device.
            with open(device, 'wb') as dev:
                with open("/usr/share/syslinux/mbr.bin", 'rb', buffering=0) as f:
                    dev.writelines(f.readlines())
            log("Writing mbr.bin complete")
    else:
        logging.error("Either device isn't a usb or you didn't type YES in all caps.")
        exit(1)


class USB(object):
    def __init__(self, cfg, facts, tmp_dir):
        self.cfg = cfg
        self.facts = facts

        self.label_name = "PLANBRECOVER-USB"
        self.tmp_dir = tmp_dir
        self.tmp_rootfs_dir = join(tmp_dir, "rootfs")
        self.tmp_usbfs_dir = join(tmp_dir, "usbfs")
        self.tmp_efi_dir = join(tmp_dir, "usbfs/EFI/BOOT")
        self.tmp_syslinux_dir = join(tmp_dir, "backup/boot/syslinux")

    def prep_uefi(self):
        """
        Prep the usb to work for uefi.
        :return:
        """
        log("Mounting EFI directory")
        makedirs(self.tmp_usbfs_dir)
        ret = mount("/dev/disk/by-label/PBR-EFI", self.tmp_usbfs_dir)
        if ret.returncode:
            logging.error(f"{ret.args} returned the following error: {ret.stderr.decode()}")
            raise MountError()

        makedirs(self.tmp_efi_dir, exist_ok=True)

        copy2(glob("/boot/efi/EFI/BOOT/BOOT*.EFI")[0], self.tmp_efi_dir)
        copy2(glob("/boot/efi/EFI/fedora/BOOT*.CSV")[0], self.tmp_efi_dir)

        # Loop through any efi file under /boot/efi/EFI/<distro>/, and copy.
        for efi in glob("/boot/efi/EFI/[a-z]*/*.efi"):
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
                    location="boot/syslinux",
                    label_name=self.label_name,
                    boot_args=self.cfg.rc_kernel_args,
                    aarch64=1
                ))
            else:
                f.write(grub_cfg.render(
                    hostname=self.facts.hostname,
                    linux_cmd="linuxefi",
                    initrd_cmd="initrdefi",
                    location="boot/syslinux",
                    label_name=self.label_name,
                    boot_args=self.cfg.rc_kernel_args,
                    aarch64=0
                ))

        log("Un-mounting EFI directory")
        umount(self.tmp_usbfs_dir)

    def prep_usb(self):
        """
        Copy the needed files for syslinux in the tmp working directory.
        :return:
        """
        # Copy all of the needed syslinux files to the tmp dir.
        makedirs(self.tmp_syslinux_dir, exist_ok=True)
        if self.facts.arch == "x86_64":
            chdir("/usr/share/syslinux/")
            copy2("chain.c32", self.tmp_syslinux_dir)
            copy2("isolinux.bin", self.tmp_syslinux_dir)
            copy2("ldlinux.c32", self.tmp_syslinux_dir)
            copy2("libcom32.c32", self.tmp_syslinux_dir)
            copy2("libmenu.c32", self.tmp_syslinux_dir)
            copy2("libutil.c32", self.tmp_syslinux_dir)
            copy2("menu.c32", self.tmp_syslinux_dir)
            copy2("vesamenu.c32", self.tmp_syslinux_dir)

            # If the memtest86+ pkg isn't installed, skip adding that boot option.
            memtest = 0
            if glob("/boot/memtest86+-*"):
                copy2(glob("/boot/memtest86*")[0], join(self.tmp_syslinux_dir, "memtest"))
                memtest = 1

            # Write out the extlinux.conf based on the isolinux.cfg template file.
            env = Environment(loader=FileSystemLoader("/usr/share/planb/"))
            isolinux_cfg = env.get_template("isolinux.cfg")
            with open(join(self.tmp_syslinux_dir, "extlinux.conf"), "w+") as f:
                f.write(isolinux_cfg.render(
                    hostname=self.facts.hostname,
                    label_name=self.label_name,
                    boot_args=self.cfg.rc_kernel_args,
                    memtest=memtest
                ))

        # Copy the current running kernel's vmlinuz file to the tmp dir.
        copy2(f"/boot/vmlinuz-{uname().release}", join(self.tmp_syslinux_dir, "vmlinuz"))

        # If fedora logos pkg is installed, copy the splash image over.
        if isfile('/usr/share/planb/splash.png'):
            copy2("/usr/share/planb/splash.png", self.tmp_syslinux_dir)

        if self.facts.uefi:
            self.prep_uefi()
        else:
            run_cmd(['extlinux', '-i', self.tmp_syslinux_dir], capture_output=False)

    def mkusb(self):
        """
        Main function of the class.
        :return:
        """
        log("Prepping the USB")
        self.prep_usb()

        liveos = RHLiveOS(self.cfg, self.facts, self.tmp_dir)
        liveos.create()

        log("Customizing the copied files to work in the USB environment")
        rh_customize_rootfs(self.cfg, self.tmp_dir, self.tmp_rootfs_dir)

        log("Creating the USB's LiveOS IMG")
        liveos.create_squashfs()

# vim:set ts=4 sw=4 et:
