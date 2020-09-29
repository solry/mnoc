from rest_framework import serializers

from .models import Device, Vlan


class DeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Device
        fields = "__all__"


class VlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vlan
        fields = "__all__"
