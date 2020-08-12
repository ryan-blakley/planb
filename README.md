# Plan (B)ackup Recovery

![Linux](https://img.shields.io/badge/-Linux-grey?logo=linux)
![Python](https://img.shields.io/badge/Python-v3.6%5E-orange?logo=python)

## Description
Plan B Recovery(pbr) is a backup and recovery tool written in python. My goal was to create a simple but stable backup
and recovery tool that was similar to ReaR in functionality. But with a more limited configuration, that was well
documented, and didn't include all of the unsupported third party stuff that ReaR does. Again my main goal with
simplicity, and stability.

## Supported setups

- Boot methods
  - ISO
  - USB
  - Both uefi/legacy on the above.
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
  - ext*
  - xfs
  - vfat
  - swap

## TODO

- [ ] Change the name to something better, plan b is just a place holder for now.
- [ ] Add man page(s).
- [ ] Add support for luks.
- [ ] Add support for btrfs.
- [ ] Add support for scp and lftp possibly.
- [ ] Test other archs beside x86.
- [ ] Eventually add other distros possibly, this is a maybe.

## Possible names

- Simple Backup and Recovery Tool(sbart)
- Sit Back and Recover(sbar/sbr)
- Kinetic Backup and Recovery(kbar/kbr)
- Forget it and Recover(fart)
- Wipe and Restore(war)
- FOO Backup and Recover(foobar)
- I don't know what else to do so recover(idkwetds)
