import logging
import tarfile

from contextlib import suppress
from os import chdir, listdir
from os.path import join, lexists
from shutil import get_terminal_size


def create_tar(cfg, bk_excludes, tmp_dir):
    """
    create_tar: Create a tar file of the rootfs, and exclude configured dirs.

    Args:
        cfg (obj): Cfg object.
        bk_excludes (list): List of directories to exclude.
        tmp_dir (str): The tmp working directory.
    """
    logger = logging.getLogger('pbr')

    # Change the directory to / beforehand.
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

        i = 1
        width = get_terminal_size().columns - 8
        total_percentage = len(dirs) / width

        for d in dirs:
            exclude = [x for x in bk_excludes if x[1:] == d]

            if exclude:
                logger.debug(f"tar: create_tar: excluding {d} from backup.")
                tar.add(d, recursive=False)
            else:
                logger.debug(f"tar: create_tar: including {d} in the backup.")
                tar.add(d, filter=tar_filter)

            print("[{:{}}] {:}%".format("=" * int(i / total_percentage), width,
                                        int((100 / width) * (i / total_percentage))), end='\r')
            i += 1

        print("")


def restore_tar(rootfs_dir, archive):
    """
    Restore the backup archive file to the newly formatted mounts.

    Args:
        rootfs_dir (str): The directory to restore the archive to.
        archive (str): The archive path.
    """
    # Cd to the mounted disk, where the data will be restored to.
    chdir(rootfs_dir)

    i = 1
    width = get_terminal_size().columns - 8

    # Extract the backup archive.
    with tarfile.open(archive) as tar:
        total_percentage = len(tar.getmembers()) / width

        # Loop through the files and extract.
        for member_info in tar.getmembers():
            print("[{:{}}] {:}%".format("=" * int(i / total_percentage), width,
                                        int((100 / width) * (i / total_percentage))), end='\r')

            # If the member is a symlink, check to make sure the link doesn't exist,
            # if the symlink exist, it will cause a massive performance hit on
            # extraction. So skip it if it exists, and move on.
            if member_info.issym() and lexists(member_info.name):
                i += 1
                continue
            else:
                with suppress(FileExistsError):
                    tar.extract(member_info)
                i += 1

        print("")
