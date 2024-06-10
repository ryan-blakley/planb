import fileinput
import logging
import magic

from contextlib import suppress
from glob import glob
from os import chdir, chroot, listdir, makedirs, open as o_open, remove, rename, symlink, uname, O_RDONLY
from os.path import exists, dirname, isdir, isfile, islink, join
from re import search
from shutil import copy2, copystat, copytree, SameFileError

from planb.exceptions import RunCMDError
from planb.utils import is_installed, pkg_files, pkg_query_file, run_cmd

logger = logging.getLogger('pbr')


class LiveOS(object):
    def __init__(self, cfg, facts, opts, tmp_dir):
        self.log = logging.getLogger('pbr')
        self.cfg = cfg
        self.facts = facts
        self.opts = opts
        self.tmp_dir = tmp_dir
        self.tmp_rootfs_dir = join(tmp_dir, "rootfs")
        self.tmp_isolinux_dir = join(tmp_dir, "isofs/isolinux")
        self.tmp_syslinux_dir = join(tmp_dir, "usbfs/boot/syslinux")
        self.exclude_files = ['build-id', '/usr/share/man']
        self.libs = []
        self.lib_pkgs = []

        self.pkgs = self.set_pkgs()

    def copy_include_files(self):
        """
        If include files is configured copy them to the recovery environment.
        """
        for src in self.cfg.rc_include_files:
            if exists(src):
                dest = join(self.tmp_rootfs_dir, src[1:])
                self.log.debug(f"distros: liveos: copy_include_files: rc_include_files: src: {src} dst: {dest}")
                makedirs(dirname(dest), exist_ok=True)
                copy2(src, dest)

    def copy_pkg_files(self, pkgs):
        """
        Loop through the array of pkgs, then list all the files
        in the pkg and copy the file or directory to the tmp rootfs.

        Args:
            pkgs (list): List of pkg names.
        """
        for pkg in pkgs:
            # Suppress the following exceptions, normally they're caused by symlinks, or multiple
            # pkgs that state they own the same file/dir.
            with suppress(TypeError, FileExistsError, SameFileError):
                for f in pkg_files(pkg):
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
                                        makedirs(dirname(dst), exist_ok=True)
                                        copystat(dirname(fname), dirname(dst))
                                        copy2(fname, dst, follow_symlinks=False)

                            # copy2 can't copy dirs, so makedirs then copy
                            # the perms, owner, etc.
                            elif isdir(fname) and not exists(dst):
                                # If not found suppress it, there is probably a dead symlink in the path.
                                with suppress(FileNotFoundError):
                                    makedirs(dst, exist_ok=True)
                                    copystat(fname, dst)

    def create(self):
        """
        Create the needed files for the LiveOS.
        """
        self.log.info("Creating initramfs for the LiveOS")
        self.create_initramfs()

        if self.facts.is_debian_based:
            self.log.info("Create minimal chroot with lb build")
            self.create_chroot_debian()

        if self.facts.is_fedora_based:
            self.log.info("Create minimal chroot with mock")
            self.create_chroot_fedora()

        if self.facts.is_mageia_based:
            self.log.info("Create minimal chroot with mock")
            self.create_chroot_mageia()

        self.log.info("Copying pkg files for the LiveOS's rootfs")
        self.find_libs(self.pkgs)
        self.copy_pkg_files(self.pkgs)
        self.copy_pkg_files(self.lib_pkgs)

        if self.cfg.rc_include_files:
            self.log.info("Copy configured files to include in the LiveOS's rootfs")
            self.copy_include_files()

    def create_chroot_debian(self):
        """
        Create debian chroot with the lb command.
        """
        chdir(self.tmp_dir)

        pkgs = [
            'dbus', 'dosfstools', 'gawk', 'grub2-common', 'kpartx', 'less', 'lsof', 'openssh-client', 'openssh-server',
            'parted', 'procps', f'python{self.facts.pyvers}', 'python3-distro', 'python3-jinja2', 'python3-magic',
            'python3-parted', 'python3-pyudev', 'python3-selinux', 'vim'
        ]
        self.set_common_pkgs(pkgs)

        config_cmd = [
            'lb', 'config', '--firmware-binary', 'false', '--firmware-chroot', 'false', '-d',
            self.facts.distro_codename, '--cache', 'false', '--apt-indices', 'false',
        ]
        if "ubuntu" in self.facts.distro_id:
            config_cmd.extend(['--parent-archive-areas', 'main universe multiverse'])

        ret = run_cmd(config_cmd, ret=True)
        self.log.debug(f"distros: cmd: lb config ret_code: {ret.returncode} stdout: {ret.stdout.decode()}")
        if ret.returncode == 1:
            self.log.error(f" The command {ret.args} returned in error: {ret.stderr.decode()}")
            raise RunCMDError()

        with open(join(self.tmp_dir, "config/package-lists/planb.list.chroot"), "w") as p_files:
            p_files.write("\n".join(pkgs))

        ret = run_cmd(['lb', 'bootstrap'], ret=True)
        self.log.debug(f"distros: cmd: lb bootstrap ret_code: {ret.returncode} stdout: {ret.stdout.decode()}")
        if ret.returncode == 1:
            self.log.error(f" The command {ret.args} returned in error: {ret.stderr.decode()}")
            raise RunCMDError()

        ret = run_cmd(['lb', 'chroot'], ret=True)
        self.log.debug(f"distros: cmd: lb chroot ret_code: {ret.returncode} stdout: {ret.stdout.decode()}")
        if ret.returncode == 1 or ret.returncode == 123:
            self.log.error(f" The command {ret.args} returned in error: {ret.stderr.decode()}")
            raise RunCMDError()

        rename(join(self.tmp_dir, "chroot"), self.tmp_rootfs_dir)

        if not self.opts.keep:
            run_cmd(['lb', 'clean', '--all'])

    def create_chroot_fedora(self):
        """
        Create chroot with mock for fedora like distros.
        """
        chdir(self.tmp_dir)
        pkgs = [
            'authselect', 'bash-completion', 'dbus', 'device-mapper-multipath', 'dosfstools', 'e2fsprogs',
            'grub2-common', 'grub2-tools', 'iproute', 'iputils', 'kdb', 'kmod', 'kpartx', 'less', 'lsof',
            'NetworkManager', 'ncurses', 'openssh-server', 'parted', 'passwd', 'plymouth', 'polkit', 'procps-ng',
            'python3', 'python3-distro', 'python3-jinja2', 'python3-libselinux', 'python3-magic', 'python3-pyparted',
            'python3-pyudev', 'python3-pyroute2', 'python3-rpm', 'rng-tools', 'rootfiles', 'systemd', 'systemd-udev',
            'vim-enhanced', 'vim-minimal'
        ]
        self.set_common_pkgs(pkgs)
        self.create_chroot_with_mock(pkgs)

    def create_chroot_mageia(self):
        """
        Create chroot with mock for mageia like distros.
        """
        chdir(self.tmp_dir)
        pkgs = [
            'bash-completion', 'chkconfig', 'dbus', 'device-mapper-multipath', 'dosfstools', 'e2fsprogs',
            'grub2-common', 'hostname', 'initscripts', 'iproute2', 'iputils', 'kdb', 'kmod', 'kpartx', 'less',
            'lib64crack2', 'locales', 'locales-en', 'lsof', 'networkmanager', 'ncurses', 'openssh-server', 'parted',
            'passwd', 'plymouth', 'polkit', 'procps-ng', 'python3', 'python3-distro', 'python3-jinja2',
            'python3-libselinux', 'python3-magic', 'python3-parted', 'python3-pyudev', 'python3-pyroute2',
            'python3-rpm', 'rng-tools', 'rootfiles', 'systemd', 'vim-enhanced', 'vim-minimal'
        ]
        if self.facts.distro_version == "8":
            pkgs.extend(['lib64python3.8', 'lib64python3.8-stdlib'])
        elif self.facts.distro_version == "9":
            pkgs.extend(['lib64python3.10', 'lib64python3.10-stdlib'])

        self.set_common_pkgs(pkgs)
        self.create_chroot_with_mock(pkgs)

    def create_chroot_with_mock(self, pkgs):
        """
        Execute mock with the provided pkgs.

        Args:
            pkgs (list): List of pkgs to install in the chroot.
        """
        # Create the initial chroot environment.
        if "centos" in self.facts.distro_id:
            mock_template = f"centos-stream-{self.facts.distro_version}-{self.facts.arch}"
        else:
            mock_template = f"{self.facts.distro_id}-{self.facts.distro_version}-{self.facts.arch}"

        ret = run_cmd(['mock', '-r', mock_template, '--no-bootstrap-chroot', '--isolation', 'simple', '--rootdir',
                       self.tmp_rootfs_dir, '--init'], ret=True)
        self.log.debug(f"distros: cmd: {ret.args} ret_code: {ret.returncode} stdout: {ret.stdout.decode()}"
                       f"stderr: {ret.stderr.decode()}")
        if ret.returncode == 1:
            raise RunCMDError()

        # Install the needed extra packages.
        cmd = ['mock', '-r', mock_template, '--no-bootstrap-chroot', '--isolation', 'simple', '--rootdir',
               self.tmp_rootfs_dir, '--dnf-cmd', '--skip-broken', '-v', '--install']
        if self.facts.is_mageia_based:
            cmd = ['mock', '-r', mock_template, '--no-bootstrap-chroot', '--isolation', 'simple', '--rootdir',
                   self.tmp_rootfs_dir, '-v', '--install']
        cmd.extend(pkgs)

        ret = run_cmd(cmd, ret=True)
        self.log.debug(f"distros: cmd: {ret.args} ret_code: {ret.returncode} stdout: {ret.stdout.decode()}"
                       f"stderr: {ret.stderr.decode()}")
        if ret.returncode == 30 or ret.returncode == 3:
            raise RunCMDError()

        # Clean up the mock cache after the rootfs has been created.
        run_cmd(['mock', '-r', mock_template, '--scrub', 'all', '-v'])

    def create_initramfs(self):
        """
        Create initramfs for booting the ISO.
        """
        initramfs_out = join(self.tmp_isolinux_dir, "initramfs.img")
        if self.cfg.boot_type == "usb":
            initramfs_out = join(self.tmp_syslinux_dir, "initramfs.img")

        if self.facts.is_debian_based:
            cmd = ['mkinitramfs', '-o', initramfs_out]
        else:
            cmd = ['dracut', '-v', '-f', '-N', '-a', 'dmsquash-live', '-a', 'rescue',
                   '--no-early-microcode', '--tmpdir', self.tmp_dir, initramfs_out]

        run_cmd(cmd)

    def create_squashfs(self):
        """
        Create squashfs of the tmp rootfs for booting the ISO.
        """
        # Create the output directory.
        if self.cfg.boot_type == "usb":
            if self.facts.is_debian_based:
                liveos_dir = join(self.tmp_dir, "usbfs/live")
            else:
                liveos_dir = join(self.tmp_dir, "usbfs/LiveOS")
        else:
            if self.facts.is_debian_based:
                liveos_dir = join(self.tmp_dir, "isofs/live")
            else:
                liveos_dir = join(self.tmp_dir, "isofs/LiveOS")

        makedirs(liveos_dir, exist_ok=True)

        # Create the squashfs img file.
        out_file = "squashfs.img"
        if self.facts.is_debian_based:
            out_file = "filesystem.squashfs"

        run_cmd(['mksquashfs', self.tmp_rootfs_dir, join(liveos_dir, out_file), '-noappend'])

    def find_libs(self, pkgs):
        """
        For each pkg, run ldd on any compiled binary, and find any required dependency pkgs needed.

        Args:
            pkgs (list): List of pkg names.
        """
        for pkg in pkgs:
            with suppress(TypeError):
                # Loop through all the files in the pkg.
                for f in pkg_files(pkg):
                    fname = f"{f}"
                    if not exists(fname):
                        continue

                    # Check the magic of the file.
                    mg = magic.detect_from_filename(fname).name

                    # If the file type is ELF, then run ldd against it.
                    if search("ELF", mg):
                        ret = run_cmd(['/usr/bin/ldd', '-v', fname], ret=True)
                        if ret.returncode > 1:
                            self.log.error(f" This command {ret.args} returned in error: {ret.stderr.decode()}")
                            raise RunCMDError()

                        for x in ret.stdout.decode().split():
                            if search("^/", x):
                                # For any lib file not already in libs append it to the list.
                                if x not in self.libs:
                                    self.libs.append(x)

        # Loop through the lib files, and find the pkgs they belong to,
        # then append those pkg names to the lib_pkgs list.
        for x in self.libs:
            pkg = pkg_query_file(x)
            if pkg not in self.lib_pkgs:
                self.lib_pkgs.append(pkg)

    def set_common_pkgs(self, pkgs):
        """
        Set common packages.

        Args:
            pkgs (list): List of pkgs needed for iso rootfs.
        """
        # Check if lvm is installed, if so add lvm pkgs.
        if self.facts.lvm_installed:
            pkgs.append("lvm2")

        # Check if luks is in use, and set the proper pkgs.
        if self.facts.luks:
            pkgs.append("cryptsetup")

        # Add efibootmgr if it's an uefi install.
        if self.facts.uefi:
            pkgs.append('efibootmgr')

        # Include the specific pkgs for the bk_location_types.
        if self.cfg.bk_location_type == "nfs":
            # On opensuse the pkg name is nfs-client not nfs-utils.
            if is_installed("nfs-client"):
                pkgs.append('nfs-client')
            elif is_installed("nfs-common"):
                pkgs.append('nfs-common')
            elif is_installed("nfs-utils"):
                pkgs.append('nfs-utils')
        elif self.cfg.bk_location_type == "cifs":
            pkgs.append('cifs-utils')
        elif self.cfg.bk_location_type == "rsync":
            pkgs.append('rsync')

        if is_installed("mdadm"):
            pkgs.append("mdadm")

        if is_installed("xfsprogs"):
            pkgs.append("xfsprogs")

        # If there are additional pkgs set in the cfg, include them in the list.
        if self.cfg.rc_include_pkgs:
            for x in self.cfg.rc_include_pkgs:
                if x not in pkgs:
                    pkgs.append(x)

    def set_pkgs(self):
        """
        Append to the base pkgs array.

        Returns:
            pkgs (list): List of pkgs needed for iso rootfs.
        """
        # Set distro specific pkgs.
        pkgs = set_distro_pkgs(self.facts)
        if not self.facts.is_debian_based:
            self.set_common_pkgs(pkgs)

            # Check if lvm is installed, if so add lvm pkgs.
            if self.facts.lvm_installed:
                pkgs.extend(['device-mapper', 'device-mapper-event', 'device-mapper-persistent-data'])

            # Check if luks is in use, and set the proper pkgs.
            if self.facts.luks:
                pkgs.extend(['device-mapper'])

            # Add the needed bootloader pkgs.
            pkgs.extend(['grub2-common', 'grub2-pc', 'grub2-pc-modules', 'grub2-tools', 'grub2-tools-extra',
                         'grub2-tools-minimal'])
            if self.facts.arch == "ppc64le":
                pkgs.extend(['grub2-ppc64le', 'grub2-ppc64le-modules'])
            elif self.facts.arch == "s390x":
                pkgs.extend(['s390utils-base'])

        return pkgs


def customize_rootfs_debian(tmp_rootfs_dir):
    """
    Copy the needed systemd files to the tmp rootfs.

    Args:
        tmp_rootfs_dir (str): The tmp rootfs directory for the iso.
    """
    # Enable the needed services.
    chdir(join(tmp_rootfs_dir, "usr/lib/systemd/system/pbr.target.wants"))

    if exists("../networking.service"):
        symlink("../networking.service", "networking.service")

    if exists("../networkd-dispatcher.service"):
        symlink("../networkd-dispatcher.service", "networkd-dispatcher.service")

    if exists("../systemd-networkd.service"):
        symlink("../systemd-networkd.service", "systemd-networkd.service")

    if not exists(join(tmp_rootfs_dir, "etc/network/interfaces")) and exists("/etc/network/interfaces"):
        copy2("/etc/network/interfaces", join(tmp_rootfs_dir, "etc/network/interfaces"))

    if exists("/etc/netplan"):
        for netplan_cfg in glob("/etc/netplan/*.yaml"):
            copy2(netplan_cfg, join(tmp_rootfs_dir, "etc/netplan/"))

    for ssh_cfg in glob("/etc/ssh/ssh_*"):
        if isfile(ssh_cfg):
            copy2(ssh_cfg, join(tmp_rootfs_dir, "etc/ssh/"))


def customize_rootfs_rh(tmp_rootfs_dir):
    """
    Copy the needed systemd files to the tmp rootfs.

    Args:
        tmp_rootfs_dir (str): The tmp rootfs directory for the iso.
    """
    if exists(join(tmp_rootfs_dir, "/usr/bin/authselect")):
        # Store the tmp rootfs dir fd, so it can exit the chroot.
        rroot = o_open("/", O_RDONLY)
        try:
            # Chroot into the tmp_rootfs_dir.
            chroot(tmp_rootfs_dir)

            # Starting in F40 the minimal profile is now named local.
            # So we need to check what profiles exist before running the select command.
            ret = run_cmd(['/usr/bin/authselect', 'list'], ret=True)
            logger.debug(f"distros: customize_rootfs_rh: cmd: authselect list ret_code: {ret.returncode}"
                         f"stdout: {ret.stdout.decode()}")
            if ret.returncode == 1:
                logger.error(f" The command {ret.args} returned in error: {ret.stderr.decode()}")
                raise RunCMDError()

            if "minimal" in ret.stdout.decode():
                profile = "minimal"
            else:
                profile = "local"

            run_cmd(['/usr/bin/authselect', 'select', profile, '--force'])

            # Cd back to the rroot fd, then chroot back out.
            chdir(rroot)
            chroot('.')
        except (FileNotFoundError, RunCMDError):
            chdir(rroot)
            chroot('.')
            raise RunCMDError

    # Enable the needed services.
    chdir(join(tmp_rootfs_dir, "usr/lib/systemd/system/pbr.target.wants"))
    symlink("../NetworkManager.service", "NetworkManager.service")

    if exists("../rngd.service"):
        # Replace the execstart of rngd so enough urandom is generated.
        symlink("../rngd.service", "rngd.service")
        for line in fileinput.input(join(tmp_rootfs_dir, "usr/lib/systemd/system/rngd.service"), inplace=True):
            if search("^ExecStart", line):
                print("ExecStart=/usr/sbin/rngd -f -r /dev/urandom")
            else:
                print(line, end='')

    chdir(join(tmp_rootfs_dir, "usr/lib/systemd/system/"))
    # Fedora renamed dbus to dbus-broker, and symlinks dbus and messsagebus from
    # the /etc/systemd/system directory for some reason. So only create the symlinks
    # if dbus-broker exist.
    if exists("dbus-broker.service"):
        symlink("dbus-broker.service", "dbus.service")
        symlink("dbus.service", "messagebus.service")

    if exists("NetworkManager-dispatcher.service"):
        symlink("NetworkManager-dispatcher.service", "dbus-org.freedesktop.nm-dispatcher.service")

    makedirs(join(tmp_rootfs_dir, "usr/lib/systemd/system/network-online.target.wants"), exist_ok=True)
    chdir(join(tmp_rootfs_dir, "usr/lib/systemd/system/network-online.target.wants"))
    symlink("../NetworkManager-wait-online.service", "NetworkManager-wait-online.service")

    # On Mageia /etc/init.d is symlinked to /etc/rc.d/init.d so manually create it.
    chdir(tmp_rootfs_dir)
    if exists("etc/rc.d/init.d") and not exists('etc/init.d'):
        symlink("etc/rc.d/init.d", "etc/init.d")

    if exists("usr/bin/vim-enhanced") and not exists("usr/bin/vim"):
        symlink("usr/bin/vim-enhanced", "usr/bin/vim")


def customize_rootfs_suse(tmp_rootfs_dir):
    """
    Copy the needed systemd files to the tmp rootfs.

    Args:
        tmp_rootfs_dir (str): The tmp rootfs directory for the iso.
    """
    # Store the tmp rootfs dir fd, so it can exit the chroot.
    rroot = o_open("/", O_RDONLY)

    # Chroot into the tmp_rootfs_dir.
    chroot(tmp_rootfs_dir)

    run_cmd(['/usr/sbin/pam-config', '-a', '--unix-nullok'])

    # Cd back to the rroot fd, then chroot back out.
    chdir(rroot)
    chroot('.')

    # Enable the needed services.
    chdir(join(tmp_rootfs_dir, "usr/lib/systemd/system/pbr.target.wants"))
    symlink("../rng-tools.service", "rng-tools.service")
    symlink("../wicked.service", "wicked.service")

    # Replace the execstart of rngd so enough urandom is generated.
    for line in fileinput.input(join(tmp_rootfs_dir, "usr/lib/systemd/system/rng-tools.service"), inplace=True):
        if search("^ExecStart", line):
            print("ExecStart=/usr/sbin/rngd -f -r /dev/urandom")
        else:
            print(line, end='')

    makedirs(join(tmp_rootfs_dir, "usr/lib/systemd/system/network-online.target.wants"), exist_ok=True)
    chdir(join(tmp_rootfs_dir, "usr/lib/systemd/system/network-online.target.wants"))
    symlink("../wicked.service", "wicked.service")

    chdir(join(tmp_rootfs_dir, "usr/lib/systemd/system/"))
    symlink("wicked.service", "network.service")
    symlink("wickedd-auto4.service", "dbus-org.opensuse.Network.AUTO4.service")
    symlink("wickedd-dhcp4.service", "dbus-org.opensuse.Network.DHCP4.service")
    symlink("wickedd-dhcp6.service", "dbus-org.opensuse.Network.DHCP6.service")
    symlink("wickedd-nanny.service", "dbus-org.opensuse.Network.Nanny.service")

    for cfg in glob("/etc/sysconfig/network/ifcfg-*"):
        if not exists(join(tmp_rootfs_dir, cfg[1:])):
            copy2(cfg, join(tmp_rootfs_dir, cfg[1:]))


def prep_rootfs(cfg, tmp_dir, tmp_rootfs_dir):
    """
    Prep the rootfs with the app specific customization.

    Args:
        cfg (obj): App cfg file.
        tmp_dir (str): The generated tmp working directory.
        tmp_rootfs_dir (str): The tmp rootfs directory for the iso.
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

    # Copy our custom pbr service and target file.
    copy2("/usr/share/planb/pbr.target", join(tmp_rootfs_dir, "usr/lib/systemd/system"))
    copy2("/usr/share/planb/pbr.service", join(tmp_rootfs_dir, "usr/lib/systemd/system"))

    # Link the default target to our custom target.
    etc_default_target = join(tmp_rootfs_dir, "etc/systemd/system/default.target")
    if exists(etc_default_target):
        remove(etc_default_target)

    chdir(join(tmp_rootfs_dir, "usr/lib/systemd/system/"))
    remove("default.target")
    symlink("pbr.target", "default.target")

    # Create the needed getty wants dir and lnk the service files.
    getty_targets_wants = join(tmp_rootfs_dir, "usr/lib/systemd/system/getty.target.wants")
    if not exists(getty_targets_wants):
        makedirs(getty_targets_wants)
        chdir(getty_targets_wants)
        symlink("../getty@.service", "getty@tty1.service")

    # Create the custom target wants dir, and lnk the needed service and target files.
    pbr_target_wants = join(tmp_rootfs_dir, "usr/lib/systemd/system/pbr.target.wants")
    makedirs(pbr_target_wants, exist_ok=True)
    chdir(pbr_target_wants)
    symlink("../dbus.service", "dbus.service")
    symlink("../getty.target", "getty.target")
    symlink("../systemd-logind.service", "systemd-logind.service")
    symlink("../plymouth-quit.service", "plymouth-quit.service")
    symlink("../plymouth-quit-wait.service", "plymouth-quit-wait.service")

    # Enable dbus socket.
    chdir(join(tmp_rootfs_dir, "usr/lib/systemd/system/sockets.target.wants"))
    # In r8 the dbus-daemon pkg contains the symlink, so if it exists skip it.
    if not exists("dbus.socket"):
        symlink("../dbus.socket", "dbus.socket")
    symlink("../dm-event.socket", "dm-event.socket")

    # Enable sshd to start by default or not, depending on cfg setting.
    if cfg.rc_enable_sshd:
        symlink("../sshd.service", "sshd.service")

    # Remove the fstab so nothing tries to mount on boot.
    if exists(join(tmp_rootfs_dir, "etc/fstab")):
        remove(join(tmp_rootfs_dir, "etc/fstab"))

    # Remove the crypttab so the luks generator doesn't start on boot.
    if exists(join(tmp_rootfs_dir, "etc/crypttab")):
        remove(join(tmp_rootfs_dir, "etc/crypttab"))

    # Check if the mdadm.conf file exist if it does copy it.
    if exists("/etc/mdadm.conf"):
        copy2("/etc/mdadm.conf", join(tmp_rootfs_dir, "etc"))
        # Remove the monitor service, it seems to cause issues when restoring sometimes.
        remove(join(tmp_rootfs_dir, "lib/systemd/system/mdmonitor.service"))

    # Check if the multipath.conf file exist if it does copy it.
    if exists("/etc/multipath.conf"):
        copy2("/etc/multipath.conf", join(tmp_rootfs_dir, "etc"))
        if exists("/etc/multipath"):
            for f in listdir("/etc/multipath"):
                copy2(join("/etc/multipath", f), join(tmp_rootfs_dir, "etc/multipath"))

    if not exists(join(tmp_rootfs_dir, "etc/group")):
        copy2("/etc/group", join(tmp_rootfs_dir, "etc/group"))

    if not exists(join(tmp_rootfs_dir, "etc/passwd")):
        copy2("/etc/passwd", join(tmp_rootfs_dir, "etc/passwd"))

    if not exists(join(tmp_rootfs_dir, "etc/shadow")):
        copy2("/etc/shadow", join(tmp_rootfs_dir, "etc/shadow"))

    # Set the root password to empty for the iso environment, unless set not to in the cfg.
    if not cfg.rc_keep_root_password:
        for line in fileinput.input(join(tmp_rootfs_dir, "etc/shadow"), inplace=True):
            if search("^root:", line):
                print("root:::0:99999:7:::")
            else:
                print(line, end='')

    # Create a profile script that creates an env var,
    # in order to tell if we're booted into the ISO.
    with open(join(tmp_rootfs_dir, "etc/profile.d/pbr.sh"), "w+") as fd:
        fd.write("export RECOVERY_MODE='1'\n")

    # Append to the iso's sshd_config file the option to ssh as root,
    # and to ssh with empty a password.
    with open(join(tmp_rootfs_dir, "etc/ssh/sshd_config"), "a+") as fd:
        fd.write("PermitEmptyPasswords yes\n")
        fd.write("PermitRootLogin yes\n")

    # Create mnt directories on the ISO.
    makedirs(join(tmp_rootfs_dir, "mnt/backup"))
    makedirs(join(tmp_rootfs_dir, "mnt/rootfs"))


def set_distro_pkgs(facts):
    """
    Append distro specific pkgs to the pkgs array.

    Args:
        facts (obj): Facts object.
    """
    # List of base packages that need to be installed, WARNING the order of this array does matter.
    suse_base_pkgs = [
        'filesystem', 'glibc', 'glibc-common', 'glibc-locale-base', 'systemd', 'systemd-sysvinit', 'udev', 'bash',
        'bash-completion', 'bash-sh', 'aaa_base', 'aaa_base-extras', 'coreutils', 'pam', 'pam-config', 'util-linux',
        'util-linux-systemd', 'dbus-1', 'polkit', 'python3', 'python3-base', 'update-alternatives', 'binutils',
        'dosfstools', 'e2fsprogs', 'gawk', 'grep', 'gzip', 'iproute2', 'iputils', 'kbd', 'kmod', 'kmod-compat',
        'kpartx', 'less', 'libpwquality1', 'libtirpc-netconfig', 'login_defs', 'lsof', 'mdadm', 'ncurses-utils',
        'netcfg', 'nfs-client', 'openssh', 'openssh-clients', 'openssh-server', 'openSUSE-release', 'parted', 'planb',
        'plymouth', 'procps', 'python3-appdirs', 'python3-distro', 'python3-Jinja2', 'python3-magic',
        'python3-MarkupSafe', 'python3-packaging', 'python3-parted', 'python3-pyparsing', 'python3-pyroute2',
        'python3-pyudev', 'python3-rpm', 'python3-selinux', 'python3-setuptools', 'python3-six', 'rng-tools',
        'rootfiles', 'rpcbind', 'rpm', 'sed', 'shadow', 'sysconfig', 'terminfo-base', 'vim', 'vim-data-common',
        'wicked', 'wicked-service', 'xfsprogs'
    ]

    if facts.is_fedora_based:
        return ['planb']
    elif "openSUSE" in facts.distro:
        return suse_base_pkgs
    elif "Mageia" in facts.distro:
        return ['planb']
    elif facts.is_debian_based:
        return ['planb']
    else:
        return ['planb']
