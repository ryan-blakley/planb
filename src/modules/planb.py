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
from argparse import ArgumentParser
from os import getuid

from .config import LoadConfig
from .facts import Facts
from .logger import log, set_log_cfg


def parse_args():
    """
    Function that parses the args passed on the command line.
    :return:
    """
    parser = ArgumentParser(description="""Plan B Recovery, if all else fails go to Plan B! 
                                        Plan B Recover comes with ABSOLUTELY NO WARRANTY.""")

    parser.add_argument("-b", "--backup", help="Create rescue media, and full system backup.", action='store_true')
    parser.add_argument("-bo", "--backup-only", help="Create backup archive only.", action='store_true')
    parser.add_argument("-f", "--facts", help="Print all the facts.", action='store_true')
    parser.add_argument("--format", help="Format the specified usb device.", action='store', type=str)
    parser.add_argument("-k", "--keep", help="Keep, don't remove temporary backup directory.", action='store_true')
    parser.add_argument("-m", "--mkrescue", help="Create rescue media only.", action='store_true')
    parser.add_argument("-r", "--recover", help="Recover system from backup.", action='store_true')
    parser.add_argument("-v", "--verbose", help="Add verbosity.", action='store_true')
    parser.add_argument("-ba", "--backup-archive", help="Specify the location of the backup archive to use on restore.",
                        action='store', type=str)
    parser.add_argument("-ro", "--restore-only", help="Restore backup archive only.", action='store_true')

    opts = parser.parse_args()

    if not opts.backup and not opts.recover and not opts.mkrescue and not opts.backup_only:
        if not opts.facts and not opts.format:
            logging.error("Please provide a valid argument.")
            parser.print_help()
            exit(1)
    
    if (opts.backup or opts.backup_only) and opts.recover:
        logging.error("Choose either backup or recover not both.")
        parser.print_help()
        exit(1)

    if (opts.backup or opts.backup_only) and opts.mkrescue:
        logging.error("Choose either backup or mkrescue not both.")
        parser.print_help()
        exit(1)

    if opts.backup_archive and not opts.recover:
        logging.error("-bo/--backup-archive can only be specified when running recover.")
        parser.print_help()
        exit(1)

    if opts.restore_only and not opts.recover:
        logging.error("-ro/--restore-only can only be specified when running recover.")
        parser.print_help()
        exit(1)

    if opts.backup and opts.backup_only:
        logging.error("-bo/--backup-only can't be specified when -b/--backup is specified, and vice versa.")
        parser.print_help()
        exit(1)

    if opts.facts and (opts.backup or opts.backup_only or opts.recover or opts.restore_only):
        logging.error("-f/--facts can't be specified if backup or recover is specified also.")
        parser.print_help()
        exit(1)

    if opts.format and (opts.backup or opts.backup_only or opts.recover or opts.restore_only):
        logging.error("--format can't be specified if backup or recover is specified also.")
        parser.print_help()
        exit(1)

    return opts


class PBR(object):
    def __init__(self):
        """
        Main class that handles executing everything.
        """
        self.opts = parse_args()
        self.cfg = LoadConfig()
        set_log_cfg(self.opts, self.cfg)

        if not getuid() == 0:
            logging.error("Please run as root")
            exit(1)

    def run(self):
        """
        Main run function.
        :return:
        """
        logging.info("")
        log("Plan (B)ackup Recovery")
        if self.opts.facts:
            facts = Facts()
            facts.print_facts()
        elif self.opts.backup or self.opts.mkrescue or self.opts.backup_only:
            from .backup import Backup

            bkup = Backup(self.opts, self.cfg)
            bkup.main()
        elif self.opts.recover:
            from .recover import Recover

            recover = Recover(self.opts, self.cfg)
            recover.main()
        elif self.opts.format:
            from .usb import fmt_usb

            fmt_usb(self.opts.format)


def main():
    """
    Main function that executes the main PBR class.
    :return:
    """
    pbr = PBR()
    pbr.run()    

# vim:set ts=4 sw=4 et:
