import logging

from planb.exceptions import RunCMDError
from planb.utils import dev_from_file, get_dev_type, run_cmd


def activate_vg(vg):
    """
    Run vgchange to activate the specific volume group.

    Args:
        vg (str): Volume group to activate.
    """
    run_cmd(['/usr/sbin/vgchange', '-ay', vg], timeout=15)


def deactivate_vgs():
    """
    Run vgchange to deactivate all the volume groups.
    """
    logger = logging.getLogger('pbr')

    ret = run_cmd(['/usr/sbin/vgchange', '-an'], ret=True)
    if ret.returncode:
        stderr = ret.stderr.decode()
        if "open logical volume" in stderr:
            logger.error("Can't deactivate volume groups because one or more is still open,"
                         "more than likely it's mounted, please make sure nothing is mounted before continuing.")
            raise RunCMDError()
        else:
            logger.warning(f"{ret.args} returned in error: {ret.stderr.decode()}")


def get_lvm_report(udev_ctx):
    """
    Run pvs, pvs, and lvs and store the output.

    Args:
        udev_ctx (obj): The udev ctx to use for querying.

    Returns:
        lvm (dict): LVM report information.
    """
    import json

    logger = logging.getLogger('pbr')
    lvm = dict()

    cmds = ['pvs', 'vgs', 'lvs']
    for c in cmds:
        # Capture the output of each command and add to the dict.
        ret = run_cmd([f"/usr/sbin/{c}", "-v", "--reportformat", "json"], ret=True)
        if ret.returncode:
            logging.getLogger('pbr').error(f" The command {ret.args} returned in error: {ret.stderr.decode()}")
            raise RunCMDError()

        if c == "pvs":
            i = 0
            report = json.loads(ret.stdout.decode())['report'][0][c[:-1]]
            logger.debug(f"lvm: get_lvm_report: c: {c} report: {report}")

            for x in report:
                if "unknown" not in x['pv_name']:
                    udev_info = dev_from_file(udev_ctx, x['pv_name'])
                    d_type = get_dev_type(udev_info)

                    # Update the pvs output to reference the md_devname, also weather it's a md dev,
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

    Args:
        bk_pv (str): The physical volume device name.
        bk_pv_uuid (str): The uuid to used to restore the proper physical volume from the metadata file.
        bk_vg (str): The volume group the physical volume will be a part of.
    """
    logger = logging.getLogger('pbr')
    # Wipe any lvm metadata if there is any.
    ret = run_cmd(['/usr/sbin/pvremove', '-ffy', bk_pv], ret=True)
    if ret.returncode:
        logger.warning(f" {ret.args} returned in error, re-running vgchange -an: {ret.stderr.decode()}")
        deactivate_vgs()

    logger.info(f"  Restoring the pv metadata on {bk_pv}")

    # Recreate the pv metadata from the backup metadata.
    run_cmd(['/usr/sbin/pvcreate', '-ff', '--uuid', bk_pv_uuid,
             '--restorefile', f"/facts/vgcfg/{bk_vg}", bk_pv], timeout=15)


def restore_vg_metadata(bk_vg):
    """
    Restore volume group from the backed up metadata file.

    Args:
        bk_vg (str): The volume group name being restored.
    """
    logging.getLogger('pbr').info(f"  Restoring the vg metadata for the {bk_vg} volume group.")

    # Restore volume group metadata from backup metadata.
    run_cmd(['/usr/sbin/vgcfgrestore', '--force', '-f', f"/facts/vgcfg/{bk_vg}", bk_vg], timeout=15)


class RecoveryLVM(object):
    def __init__(self, facts, bk_mnts, bk_lvm):
        self.log = logging.getLogger('pbr')
        self.facts = facts
        self.bk_mnts = bk_mnts
        self.bk_lvm = bk_lvm
        # Query a fresh lvm report after re-partitioning.
        self.rc_lvm = get_lvm_report(facts.udev_ctx)

    def lvm_check(self, bk_vgs):
        """
        Check if any volume groups need their layout actually restored, then activate said volume group.

        Args:
            bk_vgs (list): The list of volume groups needing to be checked.
        """
        from os.path import exists

        rc_vgs = []

        # Check for any partial vgs due to missing pv.
        for pv in self.rc_lvm.get('PVS'):
            if "unknown" in pv['pv_name']:
                rc_vgs.append(pv['vg_name'])

        for vg in bk_vgs:
            if not self.matching_lvm(vg) and vg not in rc_vgs:
                rc_vgs.append(vg)

        # Recover any vgs needing it.
        if rc_vgs:
            self.log.debug(f"lvm: lvm_check: rc_vgs: {rc_vgs}")
            # Deactivate any vgs in case it was never run prior.
            deactivate_vgs()

            for vg in rc_vgs:
                self.log.debug(f"lvm: lvm_check: vg:{vg}")
                for pv in self.bk_lvm['PVS']:
                    if vg == pv['vg_name'] and exists(pv['pv_name']):
                        self.log.debug(f"lvm: lvm_check: pv:{pv['pv_name']} vg:{vg}")
                        restore_pv_metadata(pv['pv_name'], pv['pv_uuid'], vg)

                restore_vg_metadata(vg)

        # Activate the volume groups, so mkfs can be run.
        for vg in bk_vgs:
            self.log.info(f"  Activating the {vg} volume group")
            activate_vg(vg)

            # Double check that the backup lvm matches the restored lvm.
            if not self.matching_lvm(vg):
                self.log.error(f" After restoring lvm metadata for {vg}, "
                               "the lvm layout doesn't match the layout from the backup.")
                raise RunCMDError()

    def matching_lvm(self, vg):
        """
        Compare the backup lvm layout to the current, if they don't match fix.

        Args:
            vg (str): Volume group to compare.

        Returns:
            (bool): Whether the lvm matches or not.
        """
        match = 0
        total = 0
        try:
            for lv in self.bk_lvm['LVS']:
                # Check to make sure the vg_name of the lv matches the vg.
                if lv['vg_name'] == vg:
                    total += 1
                    for lv2 in self.rc_lvm['LVS']:
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
