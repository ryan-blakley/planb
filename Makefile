ifeq ($(fedora),1)
DIST = fedora-38
else ifeq ($(epel-8),1)
DIST = centos-stream+epel-8
else ifeq ($(epel-9),1)
DIST = centos-stream+epel-9
else ifeq ($(suse),1)
DIST = opensuse-leap-15.4
else ifeq ($(mageia-8),1)
DIST = mageia-8
endif

ifeq ($(x86),1)
ARCH = x86_64
else ifeq ($(aarch64),1)
ARCH = aarch64
else ifeq ($(ppc64le),1)
ARCH = ppc64le
else ifeq ($(s390x),1)
ARCH = s390x
endif

NAME = planb
BUILD_DIR = BUILD
SRPM = SRPMS/$(NAME)-*.src.rpm
VERSION = $(shell grep "Version" packaging/rpm/$(NAME).spec | awk -F ':' '{ print $$2 }' | tr -d " ")
BUILD_ROOT = $(BUILD_DIR)/$(NAME)-$(VERSION)

rpm: buildsrpm buildrpm cleanrpm

cleanrpm:
	rm -rf build dist *.egg-info BUILD BUILDROOT RPMS SRPMS

buildsrpm:
	python3 setup.py sdist
	rpmbuild -bs -D "_topdir $(PWD)" -D "_sourcedir $(PWD)/dist" packaging/rpm/$(NAME).spec

buildrpm:
	mock -r $(DIST)-$(ARCH) --rebuild $(SRPM)

deb: builddeb cleandeb

builddeb:
	mkdir -p $(BUILD_DIR)
	python3 setup.py sdist
	tar -C $(BUILD_DIR) -xf dist/$(NAME)-$(VERSION).tar.gz
	cp -r packaging/debian $(BUILD_ROOT)/
	cd $(BUILD_ROOT)/ ; DEB_BUILD_OPTIONS=nocheck debuild -us -uc -i -b

cleandeb:
	rm -rf dist *.egg-info $(BUILD_ROOT)
