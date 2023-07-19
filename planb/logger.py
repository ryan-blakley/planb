import logging
import sys


def set_log_cfg(opts, cfg):
    """
    Set the logging configuration.

    Args:
        opts (obj): Argparse object.
        cfg (obj): Config file variables.

    Returns:
        logger (obj): Logging object.
    """
    # Create the main logger.
    logger = logging.getLogger('pbr')

    # Set the log level based on cfg file.
    if cfg.log_verbosity == "debug":
        logger.setLevel(logging.DEBUG)
    elif cfg.log_verbosity == "info":
        if opts.verbose:
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.INFO)

    # Create the log formatter.
    log_format = logging.Formatter('%(asctime)s - PBR - %(levelname)s: %(message)s')

    # Create console handler and set level depending opts.verbose.
    log_con = logging.StreamHandler(sys.stdout)
    if opts.verbose:
        con_format = logging.Formatter('%(asctime)s - %(levelname)s: %(message)s')
        log_con.setLevel(logging.DEBUG)
    else:
        con_format = logging.Formatter('%(message)s')
        log_con.setLevel(logging.INFO)

    log_con.setFormatter(con_format)
    logger.addHandler(log_con)

    # Create log file handler and the log level will be set above
    # based on what the cfg file log level is set to.
    log_file = logging.FileHandler('/var/log/pbr.log', mode='a')
    log_file.setFormatter(log_format)
    logger.addHandler(log_file)

    return logger
