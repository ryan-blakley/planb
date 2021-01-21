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
from configparser import BasicInterpolation, ConfigParser
from os.path import expandvars
from platform import machine


class EnvironmentExpansion(BasicInterpolation):
    """
    Override interpolation to expand environment variables in config parser.
    """
    def before_get(self, parser, section, option, value, defaults):
        value = super().before_get(parser, section, option, value, defaults)
        return expandvars(value)


class LoadConfig(object):
    def __init__(self):
        """
        Load and parse the config file into a class.
        """
        logger = logging.getLogger('pbr')

        try:
            cfg = ConfigParser(interpolation=EnvironmentExpansion())
            cfg.read("/etc/planb/pbr.conf")
            allowed_boot_types = ['iso', 'usb']
            allowed_bk_types = ['nfs', 'cifs', 'usb', 'iso', 'rsync', 'local']
            arch = machine()

            self.log_verbosity = cfg['App'].get('log_verbosity', 'info')
            self.tmp_dir = cfg['App'].get('tmp_dir', '/tmp')
            
            if cfg['Backup'].get('boot_type', '') and cfg['Backup'].get('backup_location_type', ''):
                self.boot_type = cfg['Backup']['boot_type']
                if self.boot_type not in allowed_boot_types:
                    logger.error("The boot_type set isn't supported, please set to either iso or usb.")
                    exit(1)

                # For the s390x architecture, it doesn't really have usb options since it's a mainframe.
                if self.boot_type == "usb" and arch == "s390x":
                    logger.error("The boot_type of usb isn't supported for the s390x platform, please change to iso.")
                    exit(1)

                self.bk_location_type = cfg['Backup']['backup_location_type']
                if self.bk_location_type not in allowed_bk_types:
                    logger.error("The backup_location_type set isn't supported, please set to one of the following: "
                                 "nfs, cifs, usb, iso, rsync, local.")
                    exit(1)

                if not self.bk_location_type == "iso":
                    self.bk_mount = cfg['Backup']['backup_mount']

                if self.boot_type == "usb" and self.bk_location_type == "iso":
                    logger.error("The backup_location_type can't be iso if the boot_type is set to usb.")
                    exit(1)
            else:
                logger.error(" The backup type/mount or the boot type isn't set in the cfg file, "
                             "please set it and try again.")
                exit(1)

            self.bk_mount_opts = cfg['Backup'].get('backup_mount_opts', '')
            self.bk_archive_prefix = cfg['Backup'].get('backup_archive_prefix', 'backup')
            self.bk_exclude_paths = list(cfg['Backup'].get('backup_exclude_paths', '').split())
            self.num_of_old_backups = int(cfg['Backup'].get('num_of_old_backups', "1"))
            self.bk_exclude_vgs = list(cfg['Backup'].get('backup_exclude_vgs', '').split())
            self.bk_exclude_disks = list(cfg['Backup'].get('backup_exclude_disks', '').split())
            self.rc_iso_prefix = cfg['Recover'].get('recover_iso_prefix', 'recover')
            self.rc_include_pkgs = list(cfg['Recover'].get('recover_include_pkgs', '').split())
            self.rc_exclude_vgs = list(cfg['Recover'].get('recover_exclude_vgs', '').split())
            self.rc_exclude_disks = list(cfg['Recover'].get('recover_exclude_disks', '').split())
            self.rc_kernel_args = list(cfg['Recover'].get('recovery_kernel_args', '').split())
            self.rc_enable_sshd = int(cfg['Recover'].get('recovery_enable_sshd', "0"))
            self.rc_keep_root_password = int(cfg['Recover'].get('recovery_keep_root_password', "0"))

        except KeyError:
            logger.exception(" Parsing the cfg file produced a KeyError.")
            exit(1)

# vim:set ts=4 sw=4 et:
