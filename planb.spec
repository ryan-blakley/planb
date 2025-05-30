%{?python_disable_dependency_generator}
%define debug_package   %{nil}

Name:           planb
Version:        0.7
Release:        1%{?dist}
Summary:        Plan B Recovery is a backup and recovery utility.

License:        GPL-3.0
URL:            https://github.com/ryan-blakley/planb
Source0:        %{name}-%{version}.tar.gz

BuildRequires:  python3-devel
BuildRequires:  python3-setuptools

Requires:       dracut
Requires:       parted
Requires:       python3
Requires:       python3-distro
%if 0%{?fedora} >= 42
Requires:       python3-file-magic
%else
Requires:	    python3-magic
%endif
Requires:       python3-pyudev
Requires:       python3-rpm
Requires:       python3-six

# The syslinux pkg is only available for x86_64.
%ifarch x86_64
Requires:       syslinux
%endif

%ifarch s390x
Requires:       s390utils-base >= 2.15.0-2
%endif

%if 0%{?fedora}%{?el8}%{?el9}
Requires:       authselect-libs >= 1.2
Requires:       dracut-live
Requires:       genisoimage
Requires:       mock
Requires:       python3-jinja2
Requires:       python3-libselinux
Requires:       python3-pyparted
Requires:       squashfs-tools
%endif

%if 0%{?suse_version} >= 1500
Requires:       mkisofs
Requires:       python3-Jinja2
Requires:       python3-selinux
Requires:       python3-parted
Requires:       squashfs
%endif

%if 0%{?mageia}
Requires:       cdrkit-genisoimage
Requires:       mock
Requires:       python3-jinja2
Requires:       python3-libselinux
Requires:       python3-parted
Requires:       squashfs-tools
%endif

%description
Plan B Recovery is a backup and recovery utility.

%prep
%autosetup -n %{name}-%{version}

%build
%py3_build

%install
%py3_install

%files
%doc README.md
%license LICENSE
# For cfg files.
%config(noreplace) %{_sysconfdir}/planb/
%config(noreplace) %{_sysconfdir}/cron.d/pbr
# For the base scripts in /bin.
%{_bindir}/*
# For noarch packages: sitelib
%{python3_sitelib}/*
# For files under /usr/share.
%{_datadir}/planb/
# Directory for outputting files.
%dir /var/lib/pbr
# Add the man pages to the package.
%doc %{_mandir}/man8/pbr.8*
%doc %{_mandir}/man5/pbr.conf.5*

%changelog
* Mon Jun 10 2024 Ryan Blakley <rblakley@redhat.com> 0.7-1
- Update Makefile to build with F40 and new spec location (rblakley@redhat.com)
- fix: Move the spec file back to the base of the project (rblakley@redhat.com)
- fix: Cleanup mock cache files after creating rootfs (rblakley@redhat.com)
- fix: efibootmgr output format changed (rblakley@redhat.com)
- fix: Issue with authselect on F40 (rblakley@redhat.com)
- fix: Issue when restoring lvm of a different size (rblakley@redhat.com)
- Add Debian to the supported list in README (rblakley@redhat.com)
- Add initial support for Ubuntu (rblakley@redhat.com)
- Fix issue with usb devices not being recognized after partitioning
  (rblakley@redhat.com)
- Update the logger more to function better (rblakley@redhat.com)
- fix: Issue with lvm restoring partial volume groups (rblakley@redhat.com)
- Update logger module (rblakley@redhat.com)
- Fix usb backing up on debian (rblakley@redhat.com)
- Add Mageia 9 support (rblakley@redhat.com)
- Use mock when available to create iso rootfs (rblakley@redhat.com)
- Misc updates (rblakley@redhat.com)
- Add initial Debian support for x86, arm64, and ppc64le (rblakley@redhat.com)

* Thu Jun 15 2023 Ryan Blakley <rblakley@redhat.com> 0.6-1
- Update README
- fix: s390x iso booting issue
- fix: Issues for ppc64le installs
- Dynamically determine the efi file and distro
- feat: Add EuroLinux and Circle Linux support
- Update the README
- feat: Add basic support for Mageia 8
- fix: Issue with incorrect boot uuid is set
- fix: flake8 issue
- fix: Errors on SUSE 15.4
- Add debug boot option
- Remove license header and vim line on all files
- Add in missing distro checks in the recover stage
- Update a few dot imports that I missed
- Switch to Google style doc strings
- fix: Update the requires with the proper module names
- Update makefile with new chroots and arches
- fix: Grammar and other issues reported by pycharm
- feat: Add Alma and Rocky support
- fix: Memory leak and error caused by file not existing
- fix: Issue created by pycharm in the chroot command
- fix: Check if command exists instead of if rpm exists
- fix: Formatting issue in the mkfs.vfat command
- fix: Flake8 issues
- Update the project layout and build
- Some updates to make functions not distro dependent
- pbr: Added two new cfg options.
- pbr: Add a check for rpmnew config file.

* Sat Feb 27 2021 Ryan Blakley <rblakley@redhat.com> 0.5-1
- pbr: Add arguments to the Makefile. (rblakley@redhat.com)
- pbr: Switch to outputting the iso file locally first. (rblakley@redhat.com)
- pbr: Fix iso booting for ppc64le. (rblakley@redhat.com)
- pbr: Add a check before mounting backup mount. (rblakley@redhat.com)
- pbr: Change up how some of the imports are defined. (rblakley@redhat.com)
- pbr: Fix various aarch64 issues. (rblakley@redhat.com)
- pbr: Remove dependency on tqdm for tar progress bar. (rblakley@redhat.com)
- pbr: Add more verbose output. (rblakley@redhat.com)
- pbr: Misc fixes (rblakley@redhat.com)
- pbr: Fix key error for partitioned md raided disk. (rblakley@redhat.com)
- pbr: grub.cfg tweaks (rblakley@redhat.com)
- pbr: Remove included pam files since they're no longer needed.
  (rblakley@redhat.com)
- pbr: Add openSUSE Leap support (rblakley@redhat.com)
- pbr: Add support for OEL (rblakley@redhat.com)
- pbr: Update the man pages with the new params, and cfg options.
  (rblakley@redhat.com)
- pbr: Fix an ordering issue, self.opts was called after defined.
  (rblakley@redhat.com)
- pbr: Rename cfg backup_include_pkgs to recover_include_pkgs since it more
  aligns. (rblakley@redhat.com)
- pbr: Update the README. (rblakley@redhat.com)
- pbr: Fix the logging. (rblakley@redhat.com)
- pbr: Added cfg option to name the recovery iso. (rblakley@redhat.com)
- pbr: Add cfg option to name the backup archive. (rblakley@redhat.com)
- pbr: Update todo and misc pep issues. (rblakley@redhat.com)
- pbr: Add in cron job to rebuild the iso on fact changes.
  (rblakley@redhat.com)
- pbr: Add a check facts cmdline option. (rblakley@redhat.com)
- pbr: Copy the outputted iso locally. (rblakley@redhat.com)
- pbr: Output facts to /var/lib/pbr for future layout checking.
  (rblakley@redhat.com)
- pbr: Compare current mounts to fstab to help prevent can't boots.
  (rblakley@redhat.com)
- pbr: Add a backup only option. (rblakley@redhat.com)
- pbr: Update the todos. (rblakley@redhat.com)

* Tue Dec 01 2020 Ryan Blakley <rblakley@redhat.com> 0.4-1
- Update the README. (rblakley@redhat.com)
- Remove version number from isolinux.cfg. (rblakley@redhat.com)
- Fix issue when multiple swap devices, also ignore zram devices.
  (rblakley@redhat.com)
- Fix a can't boot when on F33, and add build options.
  (rblakley@redhat.com)
- Add in inital LUKS support. (rblakley@redhat.com)
- Move static functions out of the Facts class. (rblakley@redhat.com)
- Removed the un-needed passing of sys.argv to main. (rblakley@redhat.com)
- Fix the facts output, to output everything. (rblakley@redhat.com)

* Thu Nov 05 2020 Ryan Blakley <rblakley@redhat.com> 0.3-1
- Add in man pages, and change pbr.cfg to pbr.conf. (rblakley@redhat.com)
- Update the README with more todo's. (rblakley@redhat.com)
- Remove unneeded check, and switch to lexists. (rblakley@redhat.com)
- Accidently forgot to remove the join, as it's not needed.
  (rblakley@redhat.com)
- Add checks for symlink and if the link already exist in tar extraction.
  (rblakley@redhat.com)
- Add in the cmdline option to restore data only. (rblakley@redhat.com)
- Update the README. (rblakley@redhat.com)
- Added in a cmdline option to specify the backup archive file.
  (rblakley@redhat.com)
- Correct a few hard coded distro name, in a path variable.
  (rblakley@redhat.com)
- Add CentOS support. (rblakley@redhat.com)
- Remove noarch, so I can use ifarch for requires. (rblakley@redhat.com)
- Add s390x support. (rblakley@redhat.com)
- Update the make file and add .gitignore file. (rblakley@redhat.com)
- Stop using TemporaryDirectory. (rblakley@redhat.com)
- Change the mkiso cmdline parameter mkrescue. (rblakley@redhat.com)
- Add in full path of a few commands that were missing it.
  (rblakley@redhat.com)
- Switch to calling genisoimage itself. (rblakley@redhat.com)
- Fix some formatting and pep issues. (rblakley@redhat.com)
- Fix some issues in the parted code. (rblakley@redhat.com)
- Add ppc64le support. (rblakley@redhat.com)
- Comment updates, and a missing parameter. (rblakley@redhat.com)
- Add aarch64 support. (rblakley@redhat.com)
- Added some comments and a missing print message. (rblakley@redhat.com)
- Update the README doc. (rblakley@redhat.com)
- Update the readme. (rblakley@redhat.com)

* Fri Jul 24 2020 Ryan Blakley <rblakley@redhat.com> 0.2-1
- new package built with tito
- Push a tag with tito, to test the build process works.

