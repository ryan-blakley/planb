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

import json
import logging
from os.path import exists

from .exceptions import RunCMDError
from .logger import log
from .utils import dev_from_file, get_dev_type, run_cmd


def activate_vg(vg):
    """
    Run vgchange to activate the specific volume group.
    :param vg: Volume group to activate.
    :return:
    """
    run_cmd(['/usr/sbin/vgchange', '-ay', vg], timeout=15)


def deactivate_vgs():
    """
    Run vgchange to deactivate all the volume groups.
    :return:
    """
    ret = run_cmd(['/usr/sbin/vgchange', '-an'], ret=True)
    if ret.returncode:
        stderr = ret.stderr.decode()
        if "open logical volume" in stderr:
            logging.error("Can't deactivate volume groups because one or more is still open,"
                          "more than likely it's mounted, please make sure nothing is mounted before continuing.")
            raise RunCMDError()
        else:
            logging.warning(f"{ret.args} returned in error: {ret.stderr.decode()}")


def get_lvm_report(udev_ctx):
    """
    Run pvs, pvs, and lvs and store the output.
    :param udev_ctx: The udev ctx to use for querying.
    :return: The lvm dictionary.
    """
    lvm = dict()

    cmds = ['pvs', 'vgs', 'lvs']
    for c in cmds:
        # Capture the output of each command and add to the dict.
        ret = run_cmd([f"/usr/sbin/{c}", "-v", "--reportformat", "json"], ret=True)
        if ret.returncode:
            logging.error(f" The command {ret.args} returned in error: {ret.stderr.decode()}")
            raise RunCMDError()

        if c == "pvs":
            i = 0
            report = json.loads(ret.stdout.decode())['report'][0][c[:-1]]

            for x in report:
                udev_info = dev_from_file(udev_ctx, x['pv_name'])
                d_type = get_dev_type(udev_info)

                # Update the pvs output to reference the md_devname, also weather it's an md dev,
                # and what the device type is.
                if udev_info.get('MD_DEVNAME', False):
                    report[i]['pv_name'] = f"/dev/md/{udev_info['MD_DEVNAME']}"
                    report[i]['md_dev'] = 1
                    report[i]['d_type'] = d_type
                else:
                    report[i]['md_dev'] = 0
                    report[i]['d_type'] = d_type

                if d_type == "part" or d_type == "part-raid":
                    report[i]['parent'] = udev_info.find_parent('block').device_node
                elif d_type == "part-mpath":
                    report[i]['parent'] = f"/dev/mapper/{udev_info.get('DM_MPATH', '')}"
                else:
                    report[i]['parent'] = None

                i += 1

            lvm.update({c.upper(): report})
        else:
            lvm.update({c.upper(): json.loads(ret.stdout.decode())['report'][0][c[:-1]]})

    return lvm


def restore_pv_metadata(bk_pv, bk_pv_uuid, bk_vg):
    """
    Recreate the physical volume using the backed up metadata file.
    :param bk_pv: The physical volume device name.
    :param bk_pv_uuid: The uuid to used to restore the proper physical volume from the metadata file.
    :param bk_vg: The volume group the physical volume will be a part of.
    :return:
    """
    # Wipe any lvm metadata if there is any.
    ret = run_cmd(['/usr/sbin/pvremove', '-ffy', bk_pv], ret=True)
    if ret.returncode:
        logging.warning(f" {ret.args} returned in error, re-running vgchange -an: {ret.stderr.decode()}")
        deactivate_vgs()

    log(f"  Restoring the pv metadata on {bk_pv}")

    # Recreate the pv metadata from the backup metadata.
    run_cmd(['/usr/sbin/pvcreate', '-ff', '--uuid', bk_pv_uuid,
             '--restorefile', f"/facts/vgcfg/{bk_vg}", bk_pv], timeout=15)


def restore_vg_metadata(bk_vg):
    """
    Restore volume group from the backed up metadata file.
    :param bk_vg: The volume group name being restored.
    :return:
    """
    log(f"  Restoring the vg metadata for the {bk_vg} volume group.")

    # Restore volume group metadata from backup metadata.
    run_cmd(['/usr/sbin/vgcfgrestore', '--force', '-f', f"/facts/vgcfg/{bk_vg}", bk_vg], timeout=15)


class RecoveryLVM(object):
    def __init__(self, facts, bk_mnts, bk_lvm):
        self.facts = facts
        self.bk_mnts = bk_mnts
        self.bk_lvm = bk_lvm

    def lvm_check(self, bk_vgs):
        """
        Check if any volume groups need their layout actually restored, then activate said volume group.
        :param bk_vgs: The list of volume groups needing to be checked.
        :return:
        """
        rc_vgs = []

        for vg in bk_vgs:
            if not self.matching_lvm(vg):
                rc_vgs.append(vg)

        # Recover any vgs needing it.
        if rc_vgs:
            logging.debug("LVM doesn't match.")
            # Deactivate any vgs in case it was never run prior.
            deactivate_vgs()

            for vg in rc_vgs:
                logging.debug(f"lvm: lvm_check: vg:{vg}")
                for pv in self.bk_lvm['PVS']:
                    if vg == pv['vg_name'] and exists(pv['pv_name']):
                        logging.debug(f"lvm: lvm_check: pv:{pv['pv_name']} vg:{vg}")
                        restore_pv_metadata(pv['pv_name'], pv['pv_uuid'], vg)

                restore_vg_metadata(vg)

        # Activate the volume groups, so mkfs can be ran.
        for vg in bk_vgs:
            log(f"  Activating the {vg} volume group")
            activate_vg(vg)

            # Double check that the backup lvm matches the restored lvm.
            if not self.matching_lvm(vg):
                logging.error(f" After restoring lvm metadata for {vg}, "
                              "the lvm layout doesn't match the layout from the backup.")
                raise RunCMDError()

    def matching_lvm(self, vg):
        """
        Compare the backup lvm layout to the current, if they don't match fix.
        :param vg: Volume group to compare.
        :return: True/False
        """
        lvm = get_lvm_report(self.facts.udev_ctx)
        match = 0
        total = 0
        try:
            for lv in self.bk_lvm['LVS']:
                # Check to make sure the vg_name of the lv matches the vg.
                if lv['vg_name'] == vg:
                    total += 1
                    for lv2 in lvm['LVS']:
                        # Check if the lv entry exist in lv2, and that it's size match.
                        if lv['lv_name'] == lv2['lv_name'] and lv['lv_size'] == lv2['lv_size']:
                            match += 1
                    # If there wasn't any entries where the name
                    # and size matches, then return false.
                    if not match:
                        return False
        except KeyError:
            return False

        if match == total:
            return True
        else:
            return False
