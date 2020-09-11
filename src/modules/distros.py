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

import fileinput
import logging
import magic
from contextlib import suppress
from os import chdir, listdir, makedirs, remove, symlink, uname
from os.path import exists, dirname, isdir, isfile, islink, join
from re import search
from shutil import copy2, copyfile, copystat, copytree, SameFileError

from .exceptions import RunCMDError
from .logger import log
from .utils import rpmql, rpmqf, run_cmd

fedora_pkgs = ['python3', 'fedora-release', 'fedora-release-common', 'fedora-release-server']
rh_pkgs = ['dbus-daemon', 'platform-python', 'python36', 'redhat-release']


class RHLiveOS(object):
    def __init__(self, cfg, facts, tmp_dir):
        self.cfg = cfg
        self.facts = facts
        self.tmp_dir = tmp_dir
        self.tmp_rootfs_dir = join(tmp_dir, "rootfs")
        self.tmp_isolinux_dir = join(tmp_dir, "isofs/isolinux")
        self.tmp_syslinux_dir = join(tmp_dir, "backup/boot/syslinux")
        self.exclude_files = ['build-id', '/usr/share/man']
        self.libs = []
        self.lib_pkgs = []

        # List of base packages that need to be installed, WARNING the order of this array does matter.
        self.base_pkgs = ['filesystem', 'glibc', 'glibc-common', 'setup', 'systemd', 'systemd-udev', 'bash',
                          'bash-completion', 'initscripts', 'coreutils', 'coreutils-common', 'pam', 'util-linux',
                          'dbus', 'dbus-broker', 'dbus-common', 'polkit', 'python3-libs', 'alternatives',
                          'NetworkManager', 'binutils', 'crypto-policies', 'device-mapper-multipath',
                          'dosfstools', 'e2fsprogs', 'gawk', 'grep', 'iproute', 'iputils', 'kbd', 'kbd-misc', 'kmod',
                          'kpartx', 'less', 'libpwquality', 'lsof', 'mdadm', 'ncurses-base', 'openssh',
                          'openssh-clients', 'openssh-server', 'parted', 'passwd', 'procps-ng', 'rng-tools',
                          'rootfiles', 'rpm', 'sed', 'vim-minimal', 'xfsprogs']

        self.pkgs = self.set_pkgs()

    def copy_pkg_files(self, pkgs):
        """
        Loop through the array of pkgs, then list all the files
        in the pkg and copy the file or directory to the tmp rootfs.
        :param pkgs: Array of pkg names.
        :return:
        """
        for pkg in pkgs:
            # Suppress the following exceptions, normally they're caused by symlinks, or multiple
            # pkgs that state they own the same file/dir.
            with suppress(TypeError, FileExistsError, SameFileError):
                for f in rpmql(pkg):
                    fname = f"{f}"
                    for exclude in self.exclude_files:
                        if exclude in fname:
                            break
                    else:
                        if exists(fname) and not fname == "/":
                            dst = join(self.tmp_rootfs_dir, fname[1:])

                            if isfile(fname) or islink(fname):
                                try:
                                    copy2(fname, dst, follow_symlinks=False)
                                except FileNotFoundError:
                                    # If exception, try making the dir of the path, then copy, if still
                                    # the file isn't found there is probably a dead symlink in the path.
                                    with suppress(FileNotFoundError):
                                        makedirs(dirname(dst))
                                        copystat(dirname(fname), dirname(dst))
                                        copy2(fname, dst, follow_symlinks=False)

                            # copy2 can't copy dirs, so makedirs then copy
                            # the perms, owner, etc.
                            elif isdir(fname) and not exists(dst):
                                # If not found suppress it, there is probably a dead symlink in the path.
                                with suppress(FileNotFoundError):
                                    makedirs(dst)
                                    copystat(fname, dst)

    def create(self):
        """
        Create the needed files for the LiveOS.
        :return:
        """
        log("Creating initramfs for the LiveOS")
        self.create_initramfs()

        log("Copying pkg files for the LiveOS's rootfs")
        self.find_libs(self.pkgs)
        self.copy_pkg_files(self.pkgs)
        self.copy_pkg_files(self.lib_pkgs)

    def create_initramfs(self):
        """
        Create initramfs for booting the ISO.
        :return:
        """
        if self.cfg.boot_type == "iso":
            run_cmd(['/usr/bin/dracut', '-f', '-N', '-a', 'dmsquash-live', '-a', 'rescue', '--no-early-microcode',
                     '--tmpdir', self.tmp_dir, join(self.tmp_isolinux_dir, "initramfs.img")])
        elif self.cfg.boot_type == "usb":
            run_cmd(['/usr/bin/dracut', '-f', '-N', '-a', 'dmsquash-live', '-a', 'rescue', '--no-early-microcode',
                     '--tmpdir', self.tmp_dir, join(self.tmp_syslinux_dir, "initramfs.img")])

    def create_squashfs(self):
        """
        Create squashfs of the tmp rootfs for booting the ISO.
        :return:
        """
        # Create the output directory.
        if self.cfg.boot_type == "usb":
            liveos_dir = join(self.tmp_dir, "backup/LiveOS")
        else:
            liveos_dir = join(self.tmp_dir, "isofs/LiveOS")
        makedirs(liveos_dir, exist_ok=True)

        # Create the squashfs img file.
        run_cmd(['/usr/sbin/mksquashfs', self.tmp_rootfs_dir, join(liveos_dir, "squashfs.img")])

    def find_libs(self, pkgs):
        """
        For each pkg, run ldd on any compiled binary, and find any required dependency pkgs needed.
        :param pkgs: Array of pkg names.
        :return:
        """
        for pkg in pkgs:
            with suppress(TypeError):
                # Loop through all the files in the pkg.
                for f in rpmql(pkg):
                    fname = f"{f}"

                    # Check the magic of the file.
                    m = magic.open(magic.NONE)
                    m.load()
                    mg = m.file(fname)

                    # If the file type is ELF, then run ldd against it.
                    if search("ELF", mg):
                        ret = run_cmd(['/usr/bin/ldd', fname], ret=True)
                        if ret.returncode > 1:
                            logging.error(f" This command {ret.args} returned in error: {ret.stderr.decode()}")
                            raise RunCMDError()

                        for x in ret.stdout.decode().split():
                            if search("^/", x):
                                # For any lib file not already in libs append it to the list.
                                if x not in self.libs:
                                    self.libs.append(x)

        # Loop through the lib files, and find the pkgs they belong to,
        # then append those pkg names to the lib_pkgs list.
        for x in self.libs:
            pkg = rpmqf(x)
            if pkg not in self.lib_pkgs:
                self.lib_pkgs.append(pkg)

    def set_pkgs(self):
        """
        Append to the base pkgs array.
        :return:
        """
        # Set distro specific pkgs.
        pkgs = set_distro_pkgs(self.base_pkgs, self.facts)

        # Check if lvm is installed, if so add lvm pkgs.
        if self.facts.lvm_installed:
            lvm_pkgs = ['device-mapper', 'device-mapper-event', 'device-mapper-persistent-data', 'lvm2']
            pkgs.extend(lvm_pkgs)

        # Add the needed grub2 pkgs.
        grub_pkgs = ['grub2-common', 'grub2-pc', 'grub2-pc-modules', 'grub2-tools', 'grub2-tools-minimal',
                     'grub2-tools-extra']
        pkgs.extend(grub_pkgs)

        # Set any pkgs needed by pbr, and pbr itself.
        pbr_pkgs = ['pbr', 'python3-distro', 'python3-libselinux', 'python3-netifaces', 'python3-pyparted',
                    'python3-pyroute2', 'python3-pyudev', 'python3-rpm', 'python3-six', 'python3-tqdm']
        pkgs.extend(pbr_pkgs)

        # If there are additional pkgs set in the cfg, include them in the list.
        if self.cfg.bk_include_pkgs:
            for x in self.cfg.bk_include_pkgs:
                if x not in pkgs:
                    pkgs.append(x)

        # Add efibootmgr if it's an uefi install.
        if self.facts.uefi:
            pkgs.append('efibootmgr')

        # Include the specific pkgs for the bk_location_types.
        if self.cfg.bk_location_type == "nfs":
            pkgs.append('nfs-utils')
        elif self.cfg.bk_location_type == "cifs":
            pkgs.append('cifs-utils')
        elif self.cfg.bk_location_type == "rsync":
            pkgs.append('rsync')

        return pkgs


def rh_customize_rootfs(cfg, tmp_dir, tmp_rootfs_dir):
    """
    Copy the needed systemd files to the tmp rootfs,
    along with setting the root password to empty.
    :param cfg: App cfg file.
    :param tmp_dir: The generated tmp working directory.
    :param tmp_rootfs_dir: The tmp rootfs directory for the iso.
    :return:
    """
    # Create our custom login screen text.
    with open(join(tmp_rootfs_dir, "etc/issue"), "w") as f:
        f.writelines("Plan (B)ackup Recovery\n")
        f.writelines("Kernel \\r on an \\m (\\l)\n\n")
        f.writelines("Welcome to the Plan B Recovery rescue environment!\n\n")
        f.writelines("Please login as the root user to access the shell, "
                     "you can then run pbr -r to start the recovery process.\n\n")

    with suppress(FileExistsError):
        # Copy the kernel module dir, so modules can be loaded.
        copytree(f"/lib/modules/{uname().release}", join(tmp_rootfs_dir, f"lib/modules/{uname().release}"),
                 ignore_dangling_symlinks=True)
        # Copy the facts directory to the ISO for use in recovery mode.
        copytree(join(tmp_dir, "facts"), join(tmp_rootfs_dir, "facts"))

    # Remove any existing pam files, then copy basic pam files over to the iso environment.
    with suppress(FileNotFoundError):
        remove(join(tmp_rootfs_dir, "etc/pam.d/system-auth"))
        remove(join(tmp_rootfs_dir, "etc/pam.d/password-auth"))
        remove(join(tmp_rootfs_dir, "etc/pam.d/postlogin"))
    copyfile("/usr/share/planb/system-auth", join(tmp_rootfs_dir, "etc/pam.d/system-auth"))
    copyfile("/usr/share/planb/password-auth", join(tmp_rootfs_dir, "etc/pam.d/password-auth"))
    copyfile("/usr/share/planb/postlogin", join(tmp_rootfs_dir, "etc/pam.d/postlogin"))

    # Copy our custom pbr service and target file.
    copy2("/usr/share/planb/pbr.target", join(tmp_rootfs_dir, "usr/lib/systemd/system"))
    copy2("/usr/share/planb/pbr.service", join(tmp_rootfs_dir, "usr/lib/systemd/system"))

    # Link the default target to our custom target.
    chdir(join(tmp_rootfs_dir, "usr/lib/systemd/system/"))
    remove(join(tmp_rootfs_dir, "usr/lib/systemd/system/default.target"))
    symlink("pbr.target", "default.target")

    # Create the needed getty wants dir and lnk the service files.
    makedirs(join(tmp_rootfs_dir, "usr/lib/systemd/system/getty.target.wants"))
    chdir(join(tmp_rootfs_dir, "usr/lib/systemd/system/getty.target.wants"))
    symlink("../getty@.service", "getty@tty0.service")
    symlink("../serial-getty@.service", "serial-getty@ttyS0.service")

    # Create the custom target wants dir, and lnk the needed service and target files.
    makedirs(join(tmp_rootfs_dir, "usr/lib/systemd/system/pbr.target.wants"))
    chdir(join(tmp_rootfs_dir, "usr/lib/systemd/system/pbr.target.wants"))
    symlink("../getty.target", "getty.target")
    symlink("../NetworkManager.service", "NetworkManager.service")
    symlink("../rngd.service", "rngd.service")

    # Enable sshd to start by default or not, depening on cfg setting.
    if cfg.rc_enable_sshd:
        symlink("../sshd.service", "sshd.service")

    # Enable dbus and NetworkManager.
    chdir(join(tmp_rootfs_dir, "usr/lib/systemd/system/sockets.target.wants"))
    # In r8 the dbus-daemon pkg contains the symlink, so if it exists skip it.
    if not exists("dbus.socket"):
        symlink("../dbus.socket", "dbus.socket")
    symlink("../dm-event.socket", "dm-event.socket")

    chdir(join(tmp_rootfs_dir, "usr/lib/systemd/system/"))
    # Fedora renamed dbus to dbus-broker, and symlinks dbus and messsagebus from
    # the /etc/systemd/system directory for some reason. So only create the symlinks
    # if dbus-broker exist.
    if exists("dbus-broker.service"):
        symlink("dbus-broker.service", "dbus.service")
        symlink("dbus.service", "messagebus.service")

    symlink("NetworkManager-dispatcher.service", "dbus-org.freedesktop.nm-dispatcher.service")

    makedirs(join(tmp_rootfs_dir, "usr/lib/systemd/system/network-online.target.wants"))
    chdir(join(tmp_rootfs_dir, "usr/lib/systemd/system/network-online.target.wants"))
    symlink("../NetworkManager-wait-online.service", "NetworkManager-wait-online.service")

    # Remove the fstab so nothing tries to mount on boot.
    remove(join(tmp_rootfs_dir, "etc/fstab"))

    # Check if the mdadm.conf file exist if it does copy it.
    if exists("/etc/mdadm.conf"):
        copy2("/etc/mdadm.conf", join(tmp_rootfs_dir, "etc"))
        # Remove the monitor service, it seems to cause issues when restoring some times.
        remove(join(tmp_rootfs_dir, "lib/systemd/system/mdmonitor.service"))

    # Check if the multipath.conf file exist if it does copy it.
    if exists("/etc/multipath.conf"):
        copy2("/etc/multipath.conf", join(tmp_rootfs_dir, "etc"))
        if exists("/etc/multipath"):
            for f in listdir("/etc/multipath"):
                copy2(join("/etc/multipath", f), join(tmp_rootfs_dir, "etc/multipath"))

    # Set the root password to empty for the iso environment, unless set not to in the cfg.
    if not cfg.rc_keep_root_password:
        for line in fileinput.input(join(tmp_rootfs_dir, "etc/shadow"), inplace=True):
            if search("^root:", line):
                print("root:::0:99999:7:::")
            else:
                print(line, end='')

    # Replace the execstart of rngd so enough urandom is generated.
    for line in fileinput.input(join(tmp_rootfs_dir, "usr/lib/systemd/system/rngd.service"), inplace=True):
        if search("^ExecStart", line):
            print("ExecStart=/sbin/rngd -f -r /dev/urandom")
        else:
            print(line, end='')

    # Create a profile script that creates an env var,
    # in order to tell if we're booted into the ISO.
    with open(join(tmp_rootfs_dir, "etc/profile.d/pbr.sh"), "w+") as fd:
        fd.write("export RECOVERY_MODE='1'\n")

    # Append to the iso's sshd_config file the option to ssh as root,
    # and to ssh with empty an password.
    with open(join(tmp_rootfs_dir, "etc/ssh/sshd_config"), "a+") as fd:
        fd.write("PermitEmptyPasswords yes\n")
        fd.write("PermitRootLogin yes\n")

    # Create mnt directories on the ISO.
    makedirs(join(tmp_rootfs_dir, "mnt/backup"))
    makedirs(join(tmp_rootfs_dir, "mnt/rootfs"))


def set_distro_pkgs(pkgs, facts):
    """
    Append distro specific pkgs to the pkgs array.
    :param pkgs: Array of pkg names.
    :param facts: facts object to pull the distro name from.
    :return:
    """
    dis = facts.distro
    if "Fedora" in dis:
        return pkgs + fedora_pkgs
    elif "Red Hat" in dis:
        return pkgs + rh_pkgs

# vim:set ts=4 sw=4 et:
