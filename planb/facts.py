import distro
import json
import logging

from os import environ, uname
from os.path import exists
from platform import machine, python_version

from pyudev import Context

from planb.fs import get_mnts
from planb.luks import get_luks_devs
from planb.lvm import get_lvm_report
from planb.parted import get_part_layout
from planb.md import get_md_info
from planb.utils import get_modules, run_cmd

logger = logging.getLogger('pbr')


def distro_efi_vars(arch, dis):
    """
    Set the local distro and efi_file variable for the grub.cfg file.

    Args:
        arch (str): The cpu architecture.
        dis (str): Distro name.

    Returns:
        (tuple): Of the distro and efi file.
    """
    if exists("/usr/sbin/efibootmgr"):
        boot_current = ""
        ret = run_cmd(['efibootmgr', '-v'], ret=True).stdout.decode().split("\n")
        for line in ret:
            if line.startswith("BootCurrent:"):
                boot_current = f"Boot{line.split(':')[1].strip()}"
                continue

            if boot_current and line.startswith(boot_current):
                logger.debug(f"facts: distro_efi_vars: line: {line}")
                if "File" in line:
                    path = line.split("File(")[1].split(")")[0].split("\\")
                    logger.debug(f"facts: distro_efi_vars: path: {path}")
                    efi_file = path[-1]
                    efi_distro = path[-2].lower()
                    return efi_distro, efi_file
                else:
                    path = line.split("/")[1].split("\\")
                    logger.debug(f"facts: distro_efi_vars: path: {path}")
                    efi_file = path[-1]
                    efi_distro = path[-2].lower()
                    return efi_distro, efi_file
    else:
        if "aarch64" in arch:
            efi_file = "shimaa64.efi"
        else:
            efi_file = "shimx64.efi"

        if "Red Hat" in dis or "Oracle" in dis:
            efi_distro = "redhat"
        else:
            efi_distro = dis.split(" ", 1)[0].lower()

        return efi_distro, efi_file


def grub_prefix():
    """
    Return grub or grub2 depending on which available.
    """
    if exists("/usr/bin/grub-mkimage"):
        return "grub"
    return "grub2"


class Facts(object):
    def __init__(self):
        """
        The facts class is meant to determine different facts about the server being
        backed up, like what the storage layout is, what are the mount points, selinux,
        etc. The variables are used throughout the application for various stuff.
        """
        self.arch = machine()
        self.distro = distro.name()
        self.distro_codename = distro.codename()
        self.distro_id = distro.id()
        self.distro_like = distro.like()
        self.distro_pretty = distro.name(pretty=True)
        self.distro_version = distro.version_parts()[0]
        self.grub_prefix = grub_prefix()
        self.hostname = uname().nodename
        self.lvm = dict()
        self.lvm_installed = exists('/usr/sbin/lvm')
        self.pyvers = python_version().rsplit(".", 1)[0]
        self.recovery_mode = environ.get('RECOVERY_MODE', False)
        self.secure_boot = 0
        self.selinux_enabled = 0
        self.selinux_enforcing = 0
        self.udev_ctx = Context()
        self.uefi = exists("/sys/firmware/efi")
        self.uname = uname().release

        self.is_debian_based = self._debian_based()
        self.is_fedora_based = self._fedora_based()
        self.is_mageia_based = self._mageia_based()
        self.is_suse_based = self._suse_based()

        self.disks = get_part_layout(self.udev_ctx)
        self.luks = get_luks_devs(self.udev_ctx)
        self.lvm = get_lvm_report(self.udev_ctx) if self.lvm_installed else {}
        self.md_info = get_md_info(self.udev_ctx)
        self.mnts = get_mnts(self.udev_ctx)

        if not self.recovery_mode:
            self.modules = get_modules()

            from selinux import is_selinux_enabled, security_getenforce
            if is_selinux_enabled():
                self.selinux_enabled = 1
                self.selinux_enforcing = security_getenforce()

            if exists('/usr/bin/mokutil') and "enabled" in run_cmd(['mokutil', '--sb-state'], ret=True).stdout.decode():
                self.secure_boot = 1

            if self.uefi:
                self.efi_distro, self.efi_file = distro_efi_vars(self.arch, self.distro)

    def _debian_based(self):
        """
        Returns:
            (bool): Return True/False if it's a Debian based distro.
        """
        if "Debian" in self.distro or "debian" in self.distro_like:
            return True
        else:
            return False

    def _fedora_based(self):
        """
        Returns:
            (bool): Return True/False if it's a Fedora based distro.
        """
        if "Fedora" in self.distro or "fedora" in self.distro_like and "mandriva" not in self.distro_like:
            return True
        else:
            return False

    def _mageia_based(self):
        """
        Returns:
            (bool): Return True/False if it's a Mageia based distro.
        """
        if "Mageia" in self.distro or "mageia" in self.distro_like:
            return True
        else:
            return False

    def _suse_based(self):
        """
        Returns:
            (bool): Return True/False if it's a SUSE based distro.
        """
        if "SUSE" in self.distro or "suse" in self.distro_like:
            return True
        else:
            return False

    def print_facts(self):
        logger.info("General Facts")
        logger.info(f"  Arch: {self.arch}")
        logger.info(f"  Hostname: {self.hostname}")
        logger.info(f"  Uname: {self.uname}")
        logger.info(f"  Distro: {self.distro}")
        logger.info(f"  Distro Codename: {self.distro_codename}")
        logger.info(f"  Distro ID: {self.distro_id}")
        logger.info(f"  Distro Like: {self.distro_like}")
        logger.info(f"  Distro Version: {self.distro_version}")
        logger.info(f"  PyVers: {self.pyvers}")
        logger.info(f"  UEFI: {self.uefi}")

        if not self.recovery_mode:
            logger.info(f"  SecureBoot: {self.secure_boot}")
            if self.uefi:
                logger.info(f"  EFI Distro: {self.efi_distro}")
                logger.info(f"  EFI File: {self.efi_file}")
            logger.info(f"  Selinux Enabled: {self.selinux_enabled}")
            logger.info(f"  Selinux Enforcing: {self.selinux_enforcing}")
        logger.info("")

        if self.lvm:
            logger.info("LVM Facts")
            logger.info(json.dumps(self.lvm, indent=4))
            logger.info("")

        logger.info("Disk Facts")
        logger.info(json.dumps(self.disks, indent=4))
        logger.info("")
        logger.info("Mount Facts")
        logger.info(json.dumps(self.mnts, indent=4))
        logger.info("")

        if self.md_info:
            logger.info("MD Raid Facts")
            logger.info(json.dumps(self.md_info, indent=4))
            logger.info("")

        if self.luks:
            logger.info("Luks Facts")
            logger.info(json.dumps(self.luks, indent=4))
            logger.info("")
