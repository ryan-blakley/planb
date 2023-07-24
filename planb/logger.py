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

    # Create the handlers.
    log_con = logging.StreamHandler(sys.stdout)
    log_file = logging.FileHandler('/var/log/pbr.log', mode='a')

    # Set the format.
    if opts.verbose:
        con_format = logging.Formatter('%(asctime)s - %(levelname)s: %(message)s')
    else:
        con_format = logging.Formatter('%(message)s')

    log_con.setFormatter(con_format)
    log_file.setFormatter(logging.Formatter('%(asctime)s - PBR - %(levelname)s: %(message)s'))

    # Set the log level based on cfg file and arguments.
    if cfg.log_verbosity == "debug":
        logger.setLevel(logging.DEBUG)
        log_file.setLevel(logging.DEBUG)
        if opts.verbose:
            log_con.setLevel(logging.DEBUG)
        else:
            log_con.setLevel(logging.INFO)
    elif cfg.log_verbosity == "info":
        if opts.verbose:
            logger.setLevel(logging.DEBUG)
            log_con.setLevel(logging.DEBUG)
            log_file.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.INFO)
            log_con.setLevel(logging.INFO)
            log_file.setLevel(logging.INFO)

    logger.addHandler(log_con)
    logger.addHandler(log_file)

    return logger
