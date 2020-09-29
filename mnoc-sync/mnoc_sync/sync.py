import logging
import os
from typing import List, Dict, Any

from mnoc_jobtools.tools import SyncJob
from mnoc_sync.mgmt_api import MgmtRestApi
from mnoc_sync.network import NetworkDevice
from jnpr.junos.exception import RpcError, ConnectError

logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s %(levelname)-8s %(message)s"
)
logging.getLogger("paramiko").setLevel(logging.WARNING)
logging.getLogger("ncclient").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

MGMT_API_HOSTNAME = "host.docker.internal"
MGMT_API_PORT = 8000
MGMT_API_USER = "mnoc-mgmt-admin"
MGMT_API_PASS = "mnoc-mgmt-password"

DEVICE_PORT = os.getenv('JUNOS_PORT')
DEVICE_USER = "automation"
DEVICE_PASS = "p@ssword"
DEVICE_VENDOR = "juniper"


"""
Vlan here is just a json converted to dict
In the context of mnoc-sync, Vlan can be:
    - serialized representation of Django Vlan model (variable usually called db_vlan)
    OR
    - json representation of Vlan configured at the device (variable usually called device_vlan)
"""
Vlan = Dict[str, Any]


class VlanSyncJobExecutor:
    """
    Executor for the sync job.
    - gets vlans from device using .network module
    - gets vlans from db using .mgmt_api module
    - compares vlans and calculates diff
    - applies diff to the job target (sync_to)
    """

    def __init__(self, sync_job: SyncJob):
        self.sync_job = sync_job
        self.device_id = sync_job.device_id
        self.sync_from = sync_job.sync_from
        self.sync_to = sync_job.sync_to
        self.mgmt_api = MgmtRestApi(
            hostname=MGMT_API_HOSTNAME,
            username=MGMT_API_USER,
            password=MGMT_API_PASS,
            port=MGMT_API_PORT,
        )
        device_management_ip = self.mgmt_api.get_device(device_id=self.device_id)[
            "management_ip"
        ]
        self.device = NetworkDevice(
            host=device_management_ip,
            port=DEVICE_PORT,
            user=DEVICE_USER,
            password=DEVICE_PASS,
            vendor=DEVICE_VENDOR,
        )

    def fetch_vlan_list_from_db(self) -> List[dict]:
        """Get list of currently present vlans from DB for the device"""
        return self.mgmt_api.get_vlans_for_device(device_id=self.device_id)

    def fetch_vlan_list_from_device(self):
        """Gets list of currently configured vlans from device
        excluding default vlan"""
        with self.device as device:
            try:
                vlan_list = device.get_vlan_list()
                non_default_vlans = []
                for vlan in vlan_list:
                    if vlan["name"] == "default" and vlan["vlan-id"] == 1:
                        continue
                    non_default_vlans.append(vlan)
                logging.info("Successfully fetched vlan list from device")
                return non_default_vlans
            except (RpcError, ConnectError):
                logging.exception(
                    f"Failed to fetch Vlans from device."
                    f" Rescheduling the SyncJob {self.sync_job.uid}"
                )
                self.sync_job.reschedule()

    def compare_vlans_against_source_of_truth(
        self, subject_vlans: List[Vlan], source_of_truth_vlans: List[Vlan], sot: str
    ):
        """
        Analyze subject vlan list and calculate the difference between it and source of truth.

        his function finds the following lists:
            - synced_vlans: List of vlans which are in sync between DB and Device,
                nothing needs to be done with this list
            - altered_vlans: List of vlans which exist in both DB and Device,
                but state of these vlans on subject is not in sync with SOT
                and needs to be updated.
            - non_present_vlans: List of vlans which exist in SOT,
                but not exist in Subject. In order to bring device into desired state,
                we should create this Vlan there.
            - removed_vlans: List of vlans which must be removed from Device,
                in order to get in sync with DB

        Args:
            subject_vlans: List of vlans to analyze against source of truth.
            source_of_truth_vlans: List of vlans which are considered to be trustful.
                The diff will show you what needs to be changed in `subject_vlans`
                to make it same as `source_of_truth_vlans`
            sot: name of sot - this should be either "device" or "db"
        Returns:

        """
        mapped_device_vlans = []

        diff = {
            "synced_vlans": [],
            "altered_vlans": [],
            "non_present_vlans": [],
            "removed_vlans": [],
        }
        for sot_vlan in source_of_truth_vlans:
            mapping_found = False
            for subject_vlan in subject_vlans:
                # Case #1: Vlans are identical
                if are_equal_vlans(subject_vlan, sot_vlan, sot=sot):
                    mapping_found = True
                    diff["synced_vlans"].append(sot_vlan)
                # Case #2: The same vlan ID but some info is outdated
                elif are_equal_vlans(
                    subject_vlan, sot_vlan, sot=sot, tag_only=True
                ):
                    mapping_found = True
                    diff["altered_vlans"].append(sot_vlan)
                else:
                    mapping_found = False

                if mapping_found:
                    mapped_device_vlans.append(subject_vlan)
                    break

            # Case #3: We didn't find SOT vlan at the box
            if not mapping_found:
                diff["non_present_vlans"].append(sot_vlan)

        for subject_vlan in subject_vlans:
            # Case #4: device vlan doesn't exist in DB
            if subject_vlan not in mapped_device_vlans:
                diff["removed_vlans"].append(subject_vlan)

        return diff

    def sync_from_db_to_device(self, device_vlans, db_vlans):
        """Push updates to device"""
        diff = self.compare_vlans_against_source_of_truth(
            subject_vlans=device_vlans, source_of_truth_vlans=db_vlans, sot="db"
        )
        logging.info(f"Discovered Altered Vlans: {len(diff['altered_vlans'])}")
        logging.info(f"Discovered Non-present Vlans: {len(diff['non_present_vlans'])}")
        logging.info(f"Discovered Removed vlans Vlans: {len(diff['removed_vlans'])}")

        if not any(
            (diff["altered_vlans"], diff["non_present_vlans"], diff["removed_vlans"])
        ):
            logging.warning("No changes detected, so no need to push vlans to device")
            return

        with self.device as device:
            try:
                device.sync_config_to_target_vlans(db_vlans)
                logging.warning("Successfully pushed Vlans config to Deviec")
            except (RpcError, ConnectError):
                logging.exception("Failed to push Vlans config to Device")

    def sync_from_device_to_db(self, device_vlans, db_vlans):
        diff = self.compare_vlans_against_source_of_truth(
            subject_vlans=db_vlans, source_of_truth_vlans=device_vlans, sot="device"
        )
        logging.info(f"Discovered Altered Vlans: {len(diff['altered_vlans'])}")
        logging.info(f"Discovered Non-present Vlans: {len(diff['non_present_vlans'])}")
        logging.info(f"Discovered Removed vlans Vlans: {len(diff['removed_vlans'])}")

        if diff["altered_vlans"]:
            self.mgmt_api.update_vlans(diff["altered_vlans"])

        if diff["non_present_vlans"]:
            self.mgmt_api.add_vlans_for_device(
                diff["non_present_vlans"], device_id=self.device_id
            )

        if diff["removed_vlans"]:
            self.mgmt_api.delete_vlans(diff["removed_vlans"])

        logging.warning("Successfully synced Device to DB Vlans")

    def execute_job(self):
        device_vlans = self.fetch_vlan_list_from_device()
        db_vlans = self.fetch_vlan_list_from_db()
        if self.sync_from == "db" and self.sync_to == "device":
            self.sync_from_db_to_device(device_vlans=device_vlans, db_vlans=db_vlans)
        elif self.sync_from == "device" and self.sync_to == "db":
            self.sync_from_device_to_db(device_vlans=device_vlans, db_vlans=db_vlans)


def are_equal_vlans(
    subject_vlan: Vlan, sot_vlan: Vlan, sot: str, tag_only=False
) -> bool:
    """Function to compare subject vlan with SOT:
        - Device and DB vlans have different attributes
        - We need to compare only significant attributes
        - Specify `sot` as 'db' or 'device' so we know what are the names of the significant attributes
        """
    if sot == "db":
        db_vlan = sot_vlan
        device_vlan = subject_vlan
    elif sot == "device":
        device_vlan = sot_vlan
        db_vlan = subject_vlan
    else:
        raise NotImplementedError(
            f"No implementation for {sot}. Supported SOTs: 'db', 'device'"
        )
    if tag_only:
        return db_vlan["tag"] == device_vlan["vlan-id"]

    return all(
        (
            db_vlan["description"] == device_vlan["description"],
            db_vlan["name"] == device_vlan["name"],
            db_vlan["tag"] == device_vlan["vlan-id"],
        )
    )


def main():
    while True:
        sync_job = SyncJob.get_next_from_queue()
        executor = VlanSyncJobExecutor(sync_job=sync_job)
        logging.warning(f"Starting executing sync job: {sync_job}")
        try:
            executor.execute_job()
        except Exception:
            logging.exception(f"Failed to execute the sync job {sync_job}")
            continue

        logging.warning(f"Finished executing sync job: {sync_job}")


if __name__ == "__main__":
    main()
