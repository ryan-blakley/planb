class ExistsError(Exception):
    """
    ExistError: Exception to raise when a file doesn't exist, or something doesn't return correctly.
    """
    pass


class GeneralError(Exception):
    """
    GeneralError: Exception to raise when a general error occurs.
    """
    pass


class RunCMDError(Exception):
    """
    RunCMDError: Exception to raise when a subprocess cmd fails.
    """
    pass


class MountError(Exception):
    """
    MountError: Exception to raise when a mount command fails.
    """
    pass
