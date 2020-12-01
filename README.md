# Plan (B)ackup Recovery

![Linux](https://img.shields.io/badge/-Linux-grey?logo=linux)
![Python](https://img.shields.io/badge/Python-v3.6%5E-orange?logo=python)

## Description
Plan B Recovery is a full backup and recovery tool. My goal was to create a simple but stable backup and 
recovery tool, but with a more limited configuration. That is well documented, and doesn't integrate other 
third party backup tools, or other unsupported(in RHEL) options. Again my main goal was simplicity, and stability.
I feel the more customization that's added, the more chances for issues to arise, and for a backup/recovery tool,
the last thing you want are issues to arise.

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

## TODO

- [x] Add man page(s).
- [x] Add arg for specifying the backup archive to use.
- [x] Add in restore data only argument.
- [x] Test other archs beside x86.
- [x] Add support for luks.
- [ ] Continue adding debugging output and comments through out the app.
- [ ] Potentially find a better way to do the pam files, instead of including them in the pkg.
- [ ] Need to figure out how to implement an option, that can be called from a cron job that rebuilds the iso on layout changes.
- [ ] Add option for secondary backup location for backup archive duplication.
- [ ] Add option to name the backup archive, and iso files.
- [ ] Add option for pre/post scripting.
- [ ] Add support for stratis.
- [ ] Add support for scp and lftp possibly.
- [ ] Would like to add an option to create pxe boot entries.
- [ ] Possibly add support for btrfs, granted it shouldn't be needed.
- [ ] Possibly add in hooks to cockpit or ansible way down the line.
- [ ] Possibly add other distros, this is a maybe since all I run is Fedora/RHEL based.
