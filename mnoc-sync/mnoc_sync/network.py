from jnpr.junos import Device
from jnpr.junos.utils.config import Config

from pathlib import Path


VLAN_CONFIG_TEMPLATE = str(Path(__file__).resolve().parent / "vlan_template.conf")


class NetworkDeviceException(Exception):
    """Base exception related to Network device connection and configuration"""
    pass


class NetworkDevice:
    def __init__(self, host, port, user, password, vendor):
        if vendor.lower() != "juniper":
            raise NotImplementedError("Supported vendors: juniper")
        self.host = host
        self.user = user
        self.port = port
        self.password = password
        self.device = Device(host=self.host, port=self.port, user=self.user, password=self.password)

    def connect(self):
        self.device.open()

    @property
    def connected(self):
        return self.device.connected

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.device.close()

    def get_vlan_list(self):
        if not self.connected:
            self.connect()

        config = self.device.rpc.get_config(filter_xml="vlans", options={"format": "json"})
        return [vlan for vlan in config["configuration"]["vlans"]["vlan"]]

    def sync_config_to_target_vlans(self, vlan_list):
        if not self.connected:
            self.connect()

        with Config(self.device, mode='exclusive') as cu:
            cu.load(template_path=VLAN_CONFIG_TEMPLATE, template_vars={"vlan_list": vlan_list})
            cu.commit()
