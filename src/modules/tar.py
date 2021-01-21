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
import tarfile
from contextlib import suppress
from os import chdir, listdir
from os.path import join, lexists
from tqdm import tqdm


def create_tar(cfg, bk_excludes, tmp_dir):
    """
    create_tar: Create a tar file of the rootfs, and exclude cfg'd dirs.
    """
    logger = logging.getLogger('pbr')

    # Change the directory to / before hand.
    chdir("/")

    # Sort the excludes, they're easier to parse if they are sorted.
    bk_excludes.sort()

    with tarfile.open(join(tmp_dir, f"{cfg.bk_archive_prefix}.tar.gz"), "w:gz") as tar:
        # Filter callback function for tarfile.add.
        def tar_filter(tarinfo):
            f_exclude = [x for x in bk_excludes if tarinfo.name.startswith(f"{x[1:]}/")]

            if f_exclude:
                logger.debug(f"tar: create_tar: tar_filter: excluding {tarinfo.name} from backup.")
                return None
            else:
                return tarinfo

        # Add each directory in / to tar archive, and sort the list.
        dirs = listdir("/")
        dirs.sort()

        # Create a tqdm progress bar, so we can monitor the tar process.
        with tqdm(total=len(dirs), leave=False) as pbar:
            for d in dirs:
                # Set the bar's description to the current directory.
                pbar.set_description(f"Adding {d} to archive.")

                exclude = [x for x in bk_excludes if x[1:] == d]

                if exclude:
                    logger.debug(f"tar: create_tar: excluding {d} from backup.")
                    tar.add(d, recursive=False)
                else:
                    logger.debug(f"tar: create_tar: including {d} in the backup.")
                    tar.add(d, filter=tar_filter)

                pbar.update()


def restore_tar(rootfs_dir, archive):
    """
    restore_tar: Restore the backup archive file to the newly formatted mounts.
    """
    # Cd to the mounted disk, where the data will be restored to.
    chdir(rootfs_dir)

    # Extract the backup archive.
    with tarfile.open(archive) as tar:
        # Create progress bar and set the description.
        with tqdm(total=len(tar.getmembers()), leave=False, desc=archive) as pbar:
            # Loop through the files and extract.
            for member_info in tar.getmembers():
                # If the member is a symlink, check to make sure the link doesn't exist,
                # if the symlink exist, it will causes a massive performance hit on
                # extraction. So skip it if it exist, and move on.
                if member_info.issym() and lexists(member_info.name):
                    continue
                else:
                    with suppress(FileExistsError):
                        tar.extract(member_info)

                # Update the progress.
                pbar.update()

# vim:set ts=4 sw=4 et:
