all:	clean build cleanbuild

clean:
	-/usr/bin/rm -rf build dist *.egg-info BUILD BUILDROOT RPMS SRPMS MANIFEST

build:
	python3 setup.py sdist
	rpmbuild -ba -D "_topdir $(PWD)" -D "_sourcedir $(PWD)/dist" *.spec

ifdef fedora
ifdef x86
	mock -r fedora-38-x86_64 --rebuild SRPMS/*.src.rpm
endif
ifdef aarch64
	mock -r fedora-38-aarch64 --rebuild SRPMS/*.src.rpm
endif
ifdef s390x
	mock -r fedora-38-s390x --rebuild SRPMS/*.src.rpm
endif
ifdef ppc64le
	mock -r fedora-38-ppc64le --rebuild SRPMS/*.src.rpm
endif
endif

ifdef epel-8
ifdef x86
	mock -r epel-8-x86_64 --rebuild SRPMS/*.src.rpm
endif
ifdef aarch64
	mock -r epel-8-aarch64 --rebuild SRPMS/*.src.rpm
endif
ifdef ppc64le
	mock -r epel-8-ppc64le --rebuild SRPMS/*.src.rpm
endif
endif

ifdef epel-9
ifdef x86
	mock -r epel-9-x86_64 --rebuild SRPMS/*.src.rpm
endif
ifdef aarch64
	mock -r epel-9-aarch64 --rebuild SRPMS/*.src.rpm
endif
ifdef ppc64le
	mock -r epel-9-ppc64le --rebuild SRPMS/*.src.rpm
endif
endif

ifdef suse
ifdef x86
	mock -r opensuse-leap-15.2-x86_64 --rebuild SRPMS/*.src.rpm
endif
ifdef aarch64
	mock -r opensuse-leap-15.2-aarch64 --rebuild SRPMS/*.src.rpm
endif
ifdef ppc64le
	mock -r opensuse-leap-15.2-ppc64le --rebuild SRPMS/*.src.rpm
endif
endif

cleanbuild:
	-/usr/bin/rm -rf build dist *.egg-info BUILD BUILDROOT MANIFEST

