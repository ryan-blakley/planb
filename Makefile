all:	clean build cleanbuild

clean:
	-/usr/bin/rm -rf dist BUILD BUILDROOT RPMS SOURCE SRPMS SPECS MANIFEST

build:
	python3 setup.py sdist
	rpmbuild -bb -D "_topdir $(PWD)" -D "_sourcedir $(PWD)/dist" pbr.spec

cleanbuild:
	-/usr/bin/rm -rf dist BUILD BUILDROOT SOURCE SRPMS SPECS MANIFEST

