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
import sys


def set_log_cfg(opts, cfg):
    """
    Set the logging configuration.
    :param opts: Argparse options.
    :param cfg: Config file variables.
    :return:
    """
    # Create the main logger.
    logger = logging.getLogger('')
    
    # Set the log level based on cfg file.
    if cfg.log_verbosity == "debug":
        logger.setLevel(logging.DEBUG)
    elif cfg.log_verbosity == "info":
        logger.setLevel(logging.INFO)

    # Create the log formatter.
    log_format = logging.Formatter('%(asctime)s - PBR - %(levelname)s: %(message)s')

    # Create console handler and set level depending opts.verbose.
    log_con = logging.StreamHandler(sys.stdout)
    if opts.verbose:
        con_format = logging.Formatter('%(asctime)s - %(levelname)s: %(message)s')
        log_con.setLevel(logging.DEBUG)
    else:
        con_format = logging.Formatter('%(levelname)s: %(message)s')
        log_con.setLevel(logging.WARNING)

    log_con.setFormatter(con_format)
    logger.addHandler(log_con)

    # Create log file handler and the log level will be set above
    # based on what the cfg file log level is set to.
    log_file = logging.FileHandler('/var/log/pbr.log', mode='w')
    log_file.setFormatter(log_format)
    logger.addHandler(log_file)


def log(msg):
    """
    log: Since all levels use the format, I can't make it where info doesn't print the level. So
    use this method for info msgs, it will print and log info, and the minimum level will be set
    to warning so info's aren't printed to the console.
    :param msg: Message to print, and log.
    :return:
    """
    print(msg)
    logging.info(msg)
