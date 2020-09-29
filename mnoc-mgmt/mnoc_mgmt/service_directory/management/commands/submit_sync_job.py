from django.core.management.base import BaseCommand, CommandError
from service_directory.models import Device
from service_directory.signals import submit_all_vlans_sync_job


class Command(BaseCommand):
    help = "Submits sync job for specified device"

    def add_arguments(self, parser):
        parser.add_argument('device_ids', nargs='+', type=int)

    def handle(self, *args, **options):
        for device_id in options['poll_ids']:
            try:
                Device.objects.get(pk=device_id)
            except Device.DoesNotExist:
                raise CommandError(f"Device with id {device_id} doesn't exist")

            submit_all_vlans_sync_job(device_id)
