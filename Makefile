all:	clean build cleanbuild

clean:
	-/usr/bin/rm -rf dist BUILD BUILDROOT RPMS SOURCE SRPMS SPECS MANIFEST

build:
	python3 setup.py sdist
	rpmbuild -ba -D "_topdir $(PWD)" -D "_sourcedir $(PWD)/dist" pbr.spec
	mock -r fedora-31-x86_64 --rebuild SRPMS/pbr-*.src.rpm
	mock -r fedora-32-x86_64 --rebuild SRPMS/pbr-*.src.rpm
	mock -r fedora-33-x86_64 --rebuild SRPMS/pbr-*.src.rpm
	mock -r epel-8-x86_64 --rebuild SRPMS/pbr-*.src.rpm

cleanbuild:
	-/usr/bin/rm -rf dist BUILD BUILDROOT SOURCE SPECS MANIFEST

