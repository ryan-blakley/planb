# Plan (B)ackup Recovery

![Linux](https://img.shields.io/badge/-Linux-grey?logo=linux)
![Python](https://img.shields.io/badge/Python-v3.6%5E-orange?logo=python)

## Description
Plan B Recovery is a full backup and recovery tool. My goal was to create a simple but stable backup and 
recovery tool, but with a more limited configuration. That was well documented, and didn't integrate other 
third party backup tools, or other unsupported options. Again my main goal was simplicity, and stability.
I feel the more customization you add, the more chances for issues to arise, and for a backup/recovery tool,
the last thing you want is issues to arise.

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
- Filesystems
  - ext[2-4]
  - xfs
  - vfat
  - swap
- Architectures
  - x86_64
  - Aarch64

## TODO

- [ ] Potentially change the name to something better, will list some possibilities below.
- [ ] Add man page(s).
- [ ] Add arg for specifying the backup archive to use.
- [ ] Add in restore data only argument.
- [ ] Continue adding debugging output through out the app.
- [ ] Potentially find a better way to do the pam files, instead of including them in the pkg.
- [ ] Need to figure out how to implement something like ReaR's check layout and cron job.
- [ ] Add option for secondary backup location for backup archive duplication.
- [ ] Add support for luks.
- [ ] Add support for btrfs.
- [ ] Add support for scp and lftp possibly.
- [ ] Test other archs beside x86.
- [ ] Would like to add an option to create pxe boot entries.
- [ ] Possibly add in hooks to cockpit or ansible way down the line.
- [ ] Possibly add other distros, this is a maybe since all I run is Fedora/RHEL based.

## List of possible new name

- Simple Backup and Recovery Tool(sbart)
- Backup and Recover Tool(bart)
- Sit Back and Recover(sbar/sbr)
- Kinetic Backup and Recovery(kbar/kbr)
- Forget it and Recover(fart)
- Wipe and Restore(war)
- FOO Backup and Recover(foobar)