import logging

from mnoc_jobtools.tools import SyncJob, SyncJobException
from pysnmp.entity import engine, config
from pysnmp.carrier.asyncore.dgram import udp
from pysnmp.entity.rfc3413 import ntfrcv


logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s %(levelname)-8s %(message)s"
)

JUNIPER_MIB = {
    "snmpTrapEnterprise": "1.3.6.1.6.3.1.1.4.3.0",
    "jnxCmNotifications": "1.3.6.1.4.1.2636.4.5",
    "jnxCmCfgChgEventUser": "1.3.6.1.4.1.2636.3.18.1.7.1.5",
}
AUTOMATION_USERNAME = "automation"

##################################################################


class Collector:
    """
    SNMP Trap listener/collector/processor
    Traps are not stored anywhere.
    As soon as collector receives trap for a configuration update,
    it creates Synchronization task in Redis Queue.
    """

    def __init__(self):
        self.snmp_engine = engine.SnmpEngine()

    @staticmethod
    def process_trap(
        snmp_engine, state_reference, context_engine_id, context_name, varbinds, cbctx,
    ):
        """Call-back function to run for every received Trap"""

        device_ip = snmp_engine.msgAndPduDsp.getTransportInfo(state_reference)[1][0]

        logging.debug(f"Received snmp-trap from {device_ip}. Starting processing")
        # Build dict for snmp trap OIDs entities:
        varbinds_dict = {}
        for k, v in varbinds:
            k = k.prettyPrint()

            # Remove trailing notification ID number
            if k.startswith(JUNIPER_MIB["jnxCmCfgChgEventUser"]):
                k = ".".join(k.split(".")[:-1])

            varbinds_dict[k] = v.prettyPrint()

        # Process only Change-Management traps
        if (
            varbinds_dict.get(JUNIPER_MIB["snmpTrapEnterprise"])
            != JUNIPER_MIB["jnxCmNotifications"]
        ):
            logging.info("Dropping non Change-management trap")
            return

        # Do not process automatically applied changes
        if (
            varbinds_dict.get(JUNIPER_MIB["jnxCmCfgChgEventUser"])
            == AUTOMATION_USERNAME
        ):
            logging.info("Dropping Trap - Trap was caused by automated configuration")
            return

        device_id = get_device_id_from_db(device_ip)
        try:
            job = SyncJob(device_id=device_id, sync_from="device", sync_to="db")
            job.put_to_queue()
        except SyncJobException:
            logging.exception("Failed to submit job to the Job Queue")

    def run(self):
        """Run collector and start processing incoming traps"""
        config.addSocketTransport(
            self.snmp_engine,
            udp.domainName + (1,),
            udp.UdpTransport().openServerMode(("0.0.0.0", 162)),
        )
        config.addV1System(self.snmp_engine, "new", "public")
        config.addContext(self.snmp_engine, "")
        ntfrcv.NotificationReceiver(self.snmp_engine, self.process_trap)
        self.snmp_engine.transportDispatcher.jobStarted(1)
        try:
            self.snmp_engine.transportDispatcher.runDispatcher()
        except Exception:
            self.snmp_engine.transportDispatcher.closeDispatcher()
            raise


##################################################################


def get_device_id_from_db(device_ip: str):
    """
    Here must be a function to get info
    from the database about the ID of the device
    Instead, we return static ID of the device. We do it for several reasons:
        - For the sake of simplicity
        - Because we have only 1 device
        - When we run the device using the virtual machine,
            the original address is hidden behind the localhost address due to NAT
    """
    logging.info(f"Fetching device_id from MNOC-Mgmt for ip {device_ip}")
    return 1


##################################################################


if __name__ == "__main__":
    collector = Collector()
    logging.warning("Starting SNMP-Collector")
    collector.run()
