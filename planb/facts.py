import distro
import json

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
                path = line.split("File(")[1].split(")")[0].split("\\")
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

    def is_debian_based(self):
        """
        Returns:
            (bool): Return True/False if it's a Debian based distro.
        """
        if "Debian" in self.distro or "debian" in self.distro_like:
            return True
        else:
            return False

    def is_fedora_based(self):
        """
        Returns:
            (bool): Return True/False if it's a Fedora based distro.
        """
        if "Fedora" in self.distro or "fedora" in self.distro_like and "mandriva" not in self.distro_like:
            return True
        else:
            return False

    def is_mageia_based(self):
        """
        Returns:
            (bool): Return True/False if it's a Mageia based distro.
        """
        if "Mageia" in self.distro or "mageia" in self.distro_like:
            return True
        else:
            return False

    def is_suse_based(self):
        """
        Returns:
            (bool): Return True/False if it's a SUSE based distro.
        """
        if "SUSE" in self.distro or "suse" in self.distro_like:
            return True
        else:
            return False

    def print_facts(self):
        print("General Facts")
        print(f"  Arch: {self.arch}")
        print(f"  Hostname: {self.hostname}")
        print(f"  Uname: {self.uname}")
        print(f"  Distro: {self.distro}")
        print(f"  Distro Codename: {self.distro_codename}")
        print(f"  Distro ID: {self.distro_id}")
        print(f"  Distro Like: {self.distro_like}")
        print(f"  Distro Version: {self.distro_version}")
        print(f"  PyVers: {self.pyvers}")
        print(f"  UEFI: {self.uefi}")

        if not self.recovery_mode:
            print(f"  SecureBoot: {self.secure_boot}")
            if self.uefi:
                print(f"  EFI Distro: {self.efi_distro}")
                print(f"  EFI File: {self.efi_file}")
            print(f"  Selinux Enabled: {self.selinux_enabled}")
            print(f"  Selinux Enforcing: {self.selinux_enforcing}")
        print("")

        if self.lvm:
            print("LVM Facts")
            print(json.dumps(self.lvm, indent=4))
            print("")

        print("Disk Facts")
        print(json.dumps(self.disks, indent=4))
        print("")
        print("Mount Facts")
        print(json.dumps(self.mnts, indent=4))
        print("")

        if self.md_info:
            print("MD Raid Facts")
            print(json.dumps(self.md_info, indent=4))
            print("")

        if self.luks:
            print("Luks Facts")
            print(json.dumps(self.luks, indent=4))
            print("")
