all:	clean build cleanbuild

clean:
	-/usr/bin/rm -rf dist BUILD BUILDROOT RPMS SOURCE SRPMS SPECS MANIFEST

build:
	python3 setup.py sdist
	rpmbuild -ba -D "_topdir $(PWD)" -D "_sourcedir $(PWD)/dist" pbr.spec

ifdef fedora
ifdef x86
	mock -r fedora-33-x86_64 --rebuild SRPMS/pbr-*.src.rpm
endif
ifdef aarch64
	mock -r fedora-33-aarch64 --rebuild SRPMS/pbr-*.src.rpm
endif
ifdef s390x
	mock -r fedora-33-s390x --rebuild SRPMS/pbr-*.src.rpm
endif
ifdef ppc64le
	mock -r fedora-33-ppc64le --rebuild SRPMS/pbr-*.src.rpm
endif
endif
ifdef epel
ifdef x86
	mock -r epel-8-x86_64 --rebuild SRPMS/pbr-*.src.rpm
endif
ifdef aarch64
	mock -r epel-8-aarch64 --rebuild SRPMS/pbr-*.src.rpm
endif
ifdef ppc64le
	mock -r epel-8-ppc64le --rebuild SRPMS/pbr-*.src.rpm
endif
endif
ifdef suse
ifdef x86
	mock -r opensuse-leap-15.2-x86_64 --rebuild SRPMS/pbr-*.src.rpm
endif
ifdef aarch64
	mock -r opensuse-leap-15.2-aarch64 --rebuild SRPMS/pbr-*.src.rpm
endif
ifdef ppc64le
	mock -r opensuse-leap-15.2-ppc64le --rebuild SRPMS/pbr-*.src.rpm
endif
endif

cleanbuild:
	-/usr/bin/rm -rf dist BUILD BUILDROOT SOURCE SPECS MANIFEST

