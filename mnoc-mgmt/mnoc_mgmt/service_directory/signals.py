import logging

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from mnoc_jobtools.tools import SyncJob, SyncJobException
from .models import Vlan


logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s %(levelname)-8s %(message)s"
)


@receiver(
    [post_save, post_delete],
    sender=Vlan,
    dispatch_uid="service_directory.signals.submit_vlan_sync_job",
)
def submit_vlan_sync_job(sender, instance: Vlan, **kwargs):
    submit_all_vlans_sync_job(device_id=instance.device.id)


def submit_all_vlans_sync_job(device_id: int):
    try:
        logging.warning(f"Vlan data for the device id {device_id} has changed")
        job = SyncJob(device_id=device_id, sync_from="db", sync_to="device")
        job.put_to_queue()
        logging.warning(f"Job has been submitted: {job}")
    except SyncJobException:
        logging.exception("Failed to submit sync job")
