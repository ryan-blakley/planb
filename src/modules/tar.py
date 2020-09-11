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
from os.path import join
from tqdm import tqdm


def create_tar(bk_excludes, tmp_dir):
    """
    create_tar: Create a tar file of the rootfs, and exclude cfg'd dirs.
    """
    # Change the directory to / before hand.
    chdir("/")

    # Sort the excludes, they're easier to parse if they are sorted.
    bk_excludes.sort()

    with tarfile.open(join(tmp_dir, "backup.tar.gz"), "w:gz") as tar:
        # Filter callback function for tarfile.add.
        def tar_filter(tarinfo):
            f_exclude = [x for x in bk_excludes if tarinfo.name.startswith(f"{x[1:]}/")]

            if f_exclude:
                logging.debug(f"tar: create_tar: tar_filter: excluding {tarinfo.name} from backup.")
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
                    logging.debug(f"tar: create_tar: excluding {d} from backup.")
                    tar.add(d, recursive=False)
                else:
                    logging.debug(f"tar: create_tar: including {d} in the backup.")
                    tar.add(d, filter=tar_filter)

                pbar.update()


def restore_tar(rootfs_dir, bk_dir):
    """
    restore_tar: Restore the backup archive file to the newly formatted mounts.
    """
    # Cd to the mounted disk, where the data will be restored to.
    chdir(rootfs_dir)

    # Extract the backup archive.
    with tarfile.open(join(bk_dir, "backup.tar.gz")) as tar:
        # Create progress bar and set the description.
        with tqdm(total=len(tar.getmembers()), leave=False, desc="backup.tar.gz") as pbar:
            # Loop through the files and extract.
            for member_info in tar.getmembers():
                with suppress(FileExistsError):
                    tar.extract(member_info)

                # Update the progress.
                pbar.update()