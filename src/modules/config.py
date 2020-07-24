# This file is part of the Plan (B)ackup Recovery project:
# https://gitlab.cee.redhat.com/rblakley/pbr

# Plan (B)ackup Recovery is free software; you can redistribute 
# it and/or modify it under the terms of the GNU General Public 
# License as published by the Free Software Foundation; either 
# version 3 of the License, or (at your option) any later version.

# Plan (B)ackup Recovery is distributed in the hope that it will
# be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details go to
# <http://www.gnu.org/licenses/>.

import logging
from configparser import ConfigParser


class LoadConfig(object):
    def __init__(self):
        try:
            cfg = ConfigParser()
            cfg.read("/etc/planb/pbr.cfg")
            allowed_boot_types = ['iso', 'usb']
            allowed_bk_types = ['nfs', 'cifs', 'usb', 'iso', 'rsync', 'local']

            if cfg['Default'].get('boot_type', '') and cfg['Default'].get('backup_location_type', ''):
                self.boot_type = cfg['Default']['boot_type']
                if self.boot_type not in allowed_boot_types:
                    logging.error("The boot_type set isn't supported, please set to either iso or usb.")
                    exit(1)

                self.bk_location_type = cfg['Default']['backup_location_type']
                if self.bk_location_type not in allowed_bk_types:
                    logging.error("The backup_location_type set isn't supported, please set to one of the following: "
                                  "nfs, cifs, usb, iso, rsync, local.")
                    exit(1)

                if not self.bk_location_type == "iso":
                    self.bk_mount = cfg['Default']['backup_mount']

                if self.boot_type == "usb" and self.bk_location_type == "iso":
                    logging.error("The backup_location_type can't be iso if the boot_type is set to usb.")
                    exit(1)
            else:
                logging.error(" The backup type/mount or the boot type isn't set in the cfg file, "
                              "please set it and try again.")
                exit(1)

            self.bk_mount_opts = cfg['Default'].get('backup_mount_opts', '')
            self.log_verbosity = cfg['Default'].get('log_verbosity', 'info')
            self.tmp_dir = cfg['Default'].get('tmp_dir', '/tmp')
            self.bk_exclude_paths = list(cfg['Default'].get('backup_exclude_paths', '').split())
            self.bk_include_pkgs = list(cfg['Default'].get('backup_include_pkgs', '').split())
            self.num_of_old_backups = int(cfg['Default'].get('num_of_old_backups', "1"))
            self.bk_exclude_vgs = list(cfg['Default'].get('backup_exclude_vgs', '').split())
            self.bk_exclude_disks = list(cfg['Default'].get('backup_exclude_disks', '').split())
            self.rc_exclude_vgs = list(cfg['Default'].get('recover_exclude_vgs', '').split())
            self.rc_exclude_disks = list(cfg['Default'].get('recover_exclude_disks', '').split())
            self.rc_kernel_args = list(cfg['Default'].get('recovery_kernel_args', '').split())
            self.rc_enable_sshd = int(cfg['Default'].get('recovery_enable_sshd', "0"))
            self.rc_keep_root_password = int(cfg['Default'].get('recovery_keep_root_password', "0"))

        except KeyError as ex:
            logging.exception(" Parsing the cfg file produced a KeyError.")
            exit(1)

# vim:set ts=4 sw=4 et:
