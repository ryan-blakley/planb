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
