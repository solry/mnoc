from mnoc_sync.sync import (
    MGMT_API_HOSTNAME,
    MGMT_API_USER,
    MGMT_API_PASS,
    MGMT_API_PORT,
    DEVICE_PORT,
    DEVICE_USER,
    DEVICE_PASS,
    DEVICE_VENDOR,
    VlanSyncJobExecutor,
    are_equal_vlans,
)
from mnoc_jobtools.tools import SyncJob
from mnoc_sync.mgmt_api import MgmtRestApi
from mnoc_sync.network import NetworkDevice
from pytest import fixture

# STATICS #########################################################################

DEVICE_DB_ID = 1
DEVICE_DB_IP = "host.docker.internal"

# FIXTURES #########################################################################

@fixture(params=[["db", "device"], ["device", "db"]])
def sync_job(request):
    return SyncJob(
        device_id=DEVICE_DB_ID, sync_from=request.param[0], sync_to=request.param[1]
    )

@fixture
def sync_job_db_to_device():
    return SyncJob(device_id=1, sync_from="db", sync_to="device")

@fixture
def sync_job_device_to_db():
    return SyncJob(device_id=1, sync_from="device", sync_to="db")

@fixture
def mgmt_api():
    return MgmtRestApi(
        hostname=MGMT_API_HOSTNAME,
        username=MGMT_API_USER,
        password=MGMT_API_PASS,
        port=MGMT_API_PORT,
    )

@fixture
def network_device():
    return NetworkDevice(
        host=DEVICE_DB_IP,
        port=DEVICE_PORT,
        user=DEVICE_USER,
        password=DEVICE_PASS,
        vendor=DEVICE_VENDOR,
    )

@fixture
def job_executor(sync_job):
    return VlanSyncJobExecutor(sync_job=sync_job)

@fixture
def device_vlan_list():
    return [
        {"name": "pytest-device-vlan-100", "vlan-id": 100, "description": "pytest",}
    ]

@fixture
def device_vlan_list_new():
    return [
        {"name": "pytest-device-vlan-333", "vlan-id": 333, "description": "pytest",}
    ]

@fixture
def db_vlan_list():
    return [
        {
            "name": "pytest-db-vlan-200",
            "tag": 200,
            "description": "pytest",
            "device": DEVICE_DB_ID,
        }
    ]

@fixture
def db_vlan_list_altered():
    return [
        {
            "name": "pytest-db-vlan-200",
            "tag": 200,
            "description": "pytest",
            "device": DEVICE_DB_ID,
        },
        {
            "name": "pytest-db-vlan-100",
            "tag": 100,
            "description": "ALTERED IN DB",
            "device": DEVICE_DB_ID,
        }
    ]

@fixture
def device_vlan_list_altered():
    return [
        {"name": "pytest-device-vlan-100", "tag": 100, "description": "pytest",},
        {"name": "pytest-device-vlan-300", "tag": 300, "description": "pytest",}
    ]


# TESTS #########################################################################


class TestMgmtRestApi:
    def test_api_get_vlans(self, mgmt_api):
        response = mgmt_api.get_vlans_for_device(DEVICE_DB_ID)
        assert isinstance(response, list)

    def test_api_add_delete_vlan(self, mgmt_api, device_vlan_list_new):
        vlan = device_vlan_list_new[0]
        mgmt_api.add_vlans_for_device(device_vlan_list_new, device_id=DEVICE_DB_ID)
        vlan_found = False
        for db_vlan in mgmt_api.get_vlans_for_device(DEVICE_DB_ID):
            vlan_found = are_equal_vlans(db_vlan, vlan, sot="device")
            if vlan_found:
                mgmt_api.delete_vlans([db_vlan])

        assert vlan_found


class TestSyncJobExecutor:
    def test_executor_resolve_device_ip(self, job_executor):
        assert job_executor.device.host == DEVICE_DB_IP

    def test_fetch_vlans_from_device(self, job_executor):
        assert job_executor.fetch_vlan_list_from_device()

    def test_fetch_vlans_from_db(self, job_executor):
        assert job_executor.fetch_vlan_list_from_db()

    def test_vlan_comparison_against_db(
        self, job_executor, db_vlan_list_altered, device_vlan_list
    ):
        diff = job_executor.compare_vlans_against_source_of_truth(
            device_vlan_list, db_vlan_list_altered, sot="db"
        )
        assert diff["altered_vlans"] == db_vlan_list_altered
        assert diff["removed_vlans"] == device_vlan_list

    def test_vlan_comparison_against_db_altered(
        self, job_executor, db_vlan_list, device_vlan_list
    ):
        diff = job_executor.compare_vlans_against_source_of_truth(
            device_vlan_list, db_vlan_list, sot="db"
        )
        assert diff["non_present_vlans"] == db_vlan_list
        assert diff["removed_vlans"] == device_vlan_list

    def test_sync_from_db_to_device(self, job_executor, db_vlan_list):
        device_vlan_list = job_executor.fetch_vlan_list_from_device()
        job_executor.sync_from_db_to_device(
            device_vlans=device_vlan_list, db_vlans=db_vlan_list
        )

    def test_push_config_to_device(self, network_device, device_vlan_list_altered):
        network_device.sync_config_to_target_vlans(device_vlan_list_altered)

    def test_sync_from_device_to_db(self, job_executor, device_vlan_list_altered):
        job_executor.device.sync_config_to_target_vlans(device_vlan_list_altered)
        device_vlan_list = job_executor.fetch_vlan_list_from_device()
        db_vlan_list = job_executor.fetch_vlan_list_from_db()
        job_executor.sync_from_device_to_db(
            device_vlans=device_vlan_list, db_vlans=db_vlan_list
        )

    def test_job_executor(self, job_executor):
        job_executor.execute_job()
