import distro
import json

from os import environ, uname
from os.path import exists
from platform import machine

from pyudev import Context

from planb.fs import get_mnts
from planb.luks import get_luks_devs
from planb.lvm import get_lvm_report
from planb.parted import get_part_layout
from planb.md import get_md_info
from planb.utils import get_modules, run_cmd


class Facts(object):
    def __init__(self):
        """
        The facts class is meant to determine different facts about the server being
        backed up, like what the storage layout is, what are the mount points, selinux,
        etc. The variables are used throughout the application for various stuff.
        """
        self.lvm = dict()

        # Some of these need to be called in order.
        self.recovery_mode = environ.get('RECOVERY_MODE', False)
        self.hostname = uname().nodename
        self.distro = distro.name()
        self.distro_pretty = distro.name(pretty=True)
        self.distro_version = distro.version_parts()[0]
        self.uname = uname().release
        self.udev_ctx = Context()
        self.mnts = get_mnts(self.udev_ctx)
        self.disks = get_part_layout(self.udev_ctx)
        self.lvm_installed = exists('/usr/sbin/lvm')

        if not self.recovery_mode:
            self.modules = get_modules()
            self.uefi = exists("/sys/firmware/efi")
            self.arch = machine()

            from selinux import is_selinux_enabled, security_getenforce
            if is_selinux_enabled():
                self.selinux_enabled = 1
                self.selinux_enforcing = security_getenforce()
            else:
                self.selinux_enabled = 0
                self.selinux_enforcing = 0

            if exists('/usr/bin/mokutil') and "enabled" in run_cmd(['mokutil', '--sb-state'], ret=True).stdout.decode():
                self.secure_boot = 1
            else:
                self.secure_boot = 0

        # Confirm the lvm2 pkg is installed before querying lvm.
        if self.lvm_installed:
            self.lvm = get_lvm_report(self.udev_ctx)

        self.md_info = get_md_info(self.udev_ctx)
        self.luks = get_luks_devs(self.udev_ctx)

    def print_facts(self):
        if not self.recovery_mode:
            print("General Facts")
            print(f"  Hostname: {self.hostname}")
            print(f"  Distro: {self.distro}")
            print(f"  UEFI: {self.uefi}")
            print(f"  SecureBoot: {self.secure_boot}")
            print(f"  Uname: {self.uname}")
            print(f"  Arch: {self.arch}")
            print(f"  Selinux Enabled: {self.selinux_enabled}\n")
        else:
            print("General Facts")
            print(f"  Hostname: {self.hostname}")
            print(f"  Distro: {self.distro}")
            print(f"  Uname: {self.uname}")

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
