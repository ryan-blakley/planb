# Plan (B)ackup Recovery
![Linux](https://img.shields.io/badge/-Linux-grey?style=flat-square&logo=linux)
![Python](https://img.shields.io/badge/Python-v3.6%5E-orange?style=flat-square&logo=python)

## Description
Plan B Recovery is a full server backup and recovery tool. Plan B Recovery is designed to be simple with few
configuration options, this is to prevent complexity. The more complexity added, the potential for loss of 
stability is added. Stability is the most important thing needed in a backup and recovery tool.

## Supported setups
- Boot methods
  - ISO
  - USB
  - Both uefi and legacy boot supported.
- Backup location methods
  - NFS
  - CIFS
  - RSYNC
  - USB
- Storage layouts
  - LVM
  - Standard Partitions
  - Multipath(only tested on fake mpath via virt-manager)
  - MD Raid
  - LUKS
- Filesystems
  - ext[2-4]
  - xfs
  - vfat
  - swap
- Architectures
  - x86_64
  - Aarch64
  - ppc64le
  - s390x
- OS's
  - Fedora(whatever versions are currently being supported)
  - RHEL 8+
  - CentOS 8+
  - Oracle Linux 8+
  - openSUSE Leap 15+

## TODO
- [x] Add man page(s).
- [x] Add arg for specifying the backup archive to use.
- [x] Add in restore data only argument.
- [x] Test other archs beside x86.
- [x] Add support for luks.
- [x] Add a backup only option.
- [x] Need to add checks for what's in the fstab and what's actually mounted.
- [x] Need to figure out how to implement an option, that can be called from a cron job that rebuilds the iso on layout changes.
- [x] Add option to name the backup archive, and iso files.
- [x] Potentially find a better way to do the pam files, instead of including them in the pkg.
- [ ] Add option for secondary backup location for backup archive duplication.
- [ ] Add option for pre/post scripting.
- [ ] Add support for stratis.
- [ ] Add support for scp and lftp possibly.
- [ ] Would like to add an option to create pxe boot entries.
- [ ] Possibly add other distros, this is a maybe since all I run is Fedora/RHEL based.
