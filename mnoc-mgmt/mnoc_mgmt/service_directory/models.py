from django.db import models


class Device(models.Model):
    name = models.CharField(unique=True, max_length=128, blank=False, null=False)
    management_ip = models.GenericIPAddressField(
        protocol="ipv4", verbose_name="Management IPv4", db_index=True
    )

    def __str__(self):
        return f"{self.name} [{self.management_ip}]"


class Vlan(models.Model):
    tag = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=64)
    description = models.CharField(max_length=128, blank=True, null=True)
    device = models.ForeignKey(Device, on_delete=models.CASCADE)

    class Meta:
        unique_together = (("device", "name"), ("device", "tag"))

    def __str__(self):
        return f"{self.name} [{self.tag}]"
