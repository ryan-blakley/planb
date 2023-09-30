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
  - AlmaLinux 8+
  - Rocky Linux 8+
  - EuroLinux 8+
  - Circle Linux 8+
  - openSUSE Leap 15+
  - Mageia 8+
  - Debian 12+
  - Ubuntu 22+

## Installation
You can download the repo from `https://copr.fedorainfracloud.org/coprs/krypto/pbr/` and then install it like any other package.
For any RHEL based OS the epel-X repos should be used.

## Usage
```text
usage: pbr [-h] [-c] [-b] [-bo] [-f] [--format FORMAT] [-k] [-m] [-r] [-v] [-ba BACKUP_ARCHIVE] [-ro]

Plan B Recovery, if all else fails go to Plan B! Plan B Recover comes with ABSOLUTELY NO WARRANTY.

optional arguments:
  -h, --help            show this help message and exit
  -c, --check-facts     Check if the existing facts changed.
  -b, --backup          Create rescue media, and full system backup.
  -bo, --backup-only    Create backup archive only.
  -f, --facts           Print all the facts.
  --format FORMAT       Format the specified usb device.
  -k, --keep            Keep, don't remove temporary backup directory.
  -m, --mkrescue        Create rescue media only.
  -r, --recover         Recover system from backup.
  -v, --verbose         Add verbosity.
  -ba BACKUP_ARCHIVE, --backup-archive BACKUP_ARCHIVE
                        Specify the location of the backup archive to use on restore.
  -ro, --restore-only   Restore backup archive only.
```

## Examples
```text
# pbr -b

Plan (B)ackup Recovery

Created temporary directory /tmp/pbr.d9959zav
Dumping facts
Successfully mounted 10.0.0.10:/backups at /tmp/pbr.d9959zav/backup
Prepping isolinux
  Formatting /tmp/pbr.d9959zav/isofs/images/efiboot.img as vfat
Creating initramfs for the LiveOS
Copying pkg files for the LiveOS's rootfs
Customizing the copied files to work in the ISO environment
Creating the ISO's LiveOS IMG
Creating the ISO file
Creating backup archive, this could take a while, please be patient
[================================================================================================ ] 99%
Un-mounting backup location /tmp/pbr.d9959zav/backup
Finished backing everything up
```
