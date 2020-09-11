Name:           pbr
Version:        0.2
Release:        1%{?dist}
Summary:        Plan B Recovery is a backup and recovery utility.

License:        GPLv3
URL:            https://github.com/ryan-blakley/pbr
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch

BuildRequires:  python3-devel
BuildRequires:  python3-setuptools

Requires: dracut-live
Requires: genisoimage
Requires: python3
Requires: python3-distro
Requires: python3-jinja2
Requires: python3-libselinux
Requires: python3-magic
Requires: python3-pyparted
Requires: python3-pyudev
Requires: python3-rpm
Requires: python3-six
Requires: python3-tqdm
%ifarch x86_64
Requires: syslinux
%endif

%description
Plan B Recovery is a backup and recovery utility.

%prep
%setup -q -n %{name}-%{version}

%build

%install
rm -rf $RPM_BUILD_ROOT
%{__python3} setup.py install -O1 --root $RPM_BUILD_ROOT

%files
# For cfg files.
%config(noreplace) %{_sysconfdir}/planb/
# For the base scripts in /bin.
%{_bindir}/*
# For noarch packages: sitelib
%{python3_sitelib}/*
# For files under /usr/share.
%{_datadir}/planb/

%changelog
* Fri Jul 24 2020 Ryan Blakley <rblakley@redhat.com> 0.2-1
- new package built with tito
- Push a tag with tito, to test the build process works.

