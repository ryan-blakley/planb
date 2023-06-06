import logging

from argparse import ArgumentParser
from os import getuid

from planb.config import LoadConfig
from planb.facts import Facts
from planb.logger import set_log_cfg


def parse_args():
    """
    Function that parses the args passed on the command line.

    Returns:
        opts (obj): Argparse object.
    """
    log = logging.getLogger('pbr')
    parser = ArgumentParser(description="""Plan B Recovery, if all else fails go to Plan B!
                                        Plan B Recover comes with ABSOLUTELY NO WARRANTY.""")

    parser.add_argument("-c", "--check-facts", help="Check if the existing facts changed.", action='store_true')
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

    if not opts.backup and not opts.recover and not opts.mkrescue and not opts.backup_only and not opts.check_facts:
        if not opts.facts and not opts.format:
            log.error("Please provide a valid argument.")
            parser.print_help()
            exit(1)

    if (opts.backup or opts.backup_only) and opts.recover:
        log.error("Choose either backup or recover not both.")
        parser.print_help()
        exit(1)

    if (opts.backup or opts.backup_only) and opts.mkrescue:
        log.error("Choose either backup or mkrescue not both.")
        parser.print_help()
        exit(1)

    if opts.backup_archive and not opts.recover:
        log.error("-bo/--backup-archive can only be specified when running recover.")
        parser.print_help()
        exit(1)

    if opts.restore_only and not opts.recover:
        log.error("-ro/--restore-only can only be specified when running recover.")
        parser.print_help()
        exit(1)

    if opts.backup and opts.backup_only:
        log.error("-bo/--backup-only can't be specified when -b/--backup is specified, and vice versa.")
        parser.print_help()
        exit(1)

    if opts.facts and (opts.backup or opts.backup_only or opts.recover or opts.restore_only):
        log.error("-f/--facts can't be specified if backup or recover is specified also.")
        parser.print_help()
        exit(1)

    if opts.format and (opts.backup or opts.backup_only or opts.recover or opts.restore_only):
        log.error("--format can't be specified if backup or recover is specified also.")
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
        self.log = set_log_cfg(self.opts, self.cfg)
        self.log.debug(f"planb: PBR: __int__: cfg: {dict(self.cfg.__dict__)}")

        if not getuid() == 0:
            self.log.error("Please run as root")
            exit(1)

    def run(self):
        """
        Main run function.
        """
        self.log.info("")
        self.log.info("Plan (B)ackup Recovery")
        self.log.info("")
        if self.opts.facts:
            fact = Facts()
            fact.print_facts()
        elif self.opts.backup or self.opts.mkrescue or self.opts.backup_only or self.opts.check_facts:
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
    """
    pbr = PBR()
    pbr.run()
