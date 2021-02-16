Name:           pbr
Version:        0.4
Release:        1%{?dist}
Summary:        Plan B Recovery is a backup and recovery utility.

License:        GPL-3.0
URL:            https://github.com/ryan-blakley/pbr
Source0:        %{name}-%{version}.tar.gz

BuildRequires:  python3-devel
BuildRequires:  python3-setuptools

Requires: dracut
Requires: python3
Requires: python3-distro
Requires: python3-magic
Requires: python3-pyudev
Requires: python3-rpm
Requires: python3-six
Requires: python3-tqdm

%if 0%{?is_opensuse}
Requires: mkisofs
Requires: python3-Jinja2
Requires: python3-selinux
Requires: python3-parted
Requires: squashfs
# The syslinux pkg is only available for x86_64.
%ifarch x86_64
Requires: syslinux
%endif
%else
Requires: authselect-libs >= 1.2
Requires: dracut-live
Requires: genisoimage
Requires: python3-jinja2
Requires: python3-libselinux
Requires: python3-pyparted
Requires: squashfs-tools
# The syslinux pkg is only available for x86_64.
%ifarch x86_64
Requires: syslinux
Requires: syslinux-extlinux
%endif
%endif

%description
Plan B Recovery is a backup and recovery utility.

# Had to remove BuildArch noarch, so I could filter Requires for syslinux,
# doing that switched it to wanting to build a debuginfo rpm. Since this is
# purely python, it doesn't need a debuginfo rpm, so disable generating one.
%global debug_package %{nil}

%prep
%setup -q -n %{name}-%{version}

%build

%install
rm -rf $RPM_BUILD_ROOT
%{__python3} setup.py install -O1 --root $RPM_BUILD_ROOT

%files
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

