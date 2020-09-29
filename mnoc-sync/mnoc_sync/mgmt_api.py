import logging
from copy import deepcopy

from requests import Session, Response, HTTPError
from requests.auth import HTTPBasicAuth


class MgmtRestApi:
    """
    Class to interact with MNOC Management Django Rest Api
    Since we use service oriented architecture,
    we don't want to keep Django and database as dependencies.
    So in this case Mgmt service is accessible via Rest API.
    """

    API_URL_PREFIX = "/service_directory/api"
    VLAN_URL = "/vlans"
    DEVICE_URL = "/devices"

    def __init__(self, hostname: str, username: str, password: str, port: int = None):
        self._hostname = hostname
        self._username = username
        self._password = password
        self._port = port
        self._session = self.__get_requests_session()
        if port:
            self.__api_base_url = (
                f"http://{self._hostname}:{self._port}{self.API_URL_PREFIX}"
            )
        else:
            self.__api_base_url = f"http://{self._hostname}{self.API_URL_PREFIX}"

        self.__api_vlan_url = self.__api_base_url + self.VLAN_URL + "/"
        self.__api_device_url = self.__api_base_url + self.DEVICE_URL + "/"

    def __get_requests_session(self, trust_env: bool = False) -> Session:
        session = Session()
        session.auth = HTTPBasicAuth(username=self._username, password=self._password)
        session.trust_env = trust_env
        return session

    @staticmethod
    def __check_response(response: Response, operation: str):
        try:
            response.raise_for_status()
        except HTTPError:
            logging.exception("[Failure]: " + operation)
            raise
        logging.info(f"[Success]: " + operation)

    def get_device(self, device_id: int):
        response = self._session.get(self.__api_device_url + str(device_id) + "/")
        self.__check_response(response, f"Get device data for {device_id} from MgmtApi")
        return response.json()

    def get_vlans_for_device(self, device_id: int):
        response = self._session.get(
            self.__api_vlan_url, params={"device__id": device_id},
        )
        self.__check_response(response, f"Get vlans data for {device_id} from MgmtApi")
        return response.json()

    def add_vlans_for_device(self, new_vlans: list, device_id):
        for vlan in new_vlans:
            vlan_to_submit = deepcopy(vlan)
            vlan_to_submit["device"] = device_id
            if "vlan-id" in vlan_to_submit:
                vlan_to_submit["tag"] = vlan_to_submit.pop("vlan-id")
            response = self._session.post(self.__api_vlan_url, json=vlan_to_submit)
            self.__check_response(
                response, f"Create new vlan {vlan['name']} for {device_id} in MgmtApi"
            )

    def update_vlans(self, updated_vlans_list: list):
        for vlan in updated_vlans_list:
            response = self._session.put(
                self.__api_vlan_url + str(vlan["id"]), json=vlan
            )
            self.__check_response(response, f"Update vlan {vlan['tag']} in MgmtApi")
            logging.info(f"Updated {vlan['name']} in MgmtApi")

    def delete_vlans(self, removed_vlans_list: list):
        for vlan in removed_vlans_list:
            response = self._session.delete(self.__api_vlan_url + str(vlan["id"]))
            self.__check_response(response, f"Delete vlan {vlan['tag']} in MgmtApi")
