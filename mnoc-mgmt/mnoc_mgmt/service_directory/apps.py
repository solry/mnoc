from django.apps import AppConfig


class ServiceDirectoryConfig(AppConfig):
    name = 'service_directory'

    def ready(self):
        from . import signals   # For connecting 'signals'
