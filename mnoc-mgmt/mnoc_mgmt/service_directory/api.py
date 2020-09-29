import json

from mnoc_jobtools.tools import RedisJobQueue
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Device, Vlan
from .serializers import DeviceSerializer, VlanSerializer
from rest_framework.viewsets import ModelViewSet


class DeviceViewSet(ModelViewSet):
    queryset = Device.objects.all()
    serializer_class = DeviceSerializer
    filterset_fields = ("id", "name", "management_ip")


class VlanViewSet(ModelViewSet):
    queryset = Vlan.objects.select_related("device").all()
    serializer_class = VlanSerializer
    filterset_fields = ("id", "tag", "name", "device__name", "device__id")


class RpcListTaskQueueView(APIView):
    def get(self, request):
        job_queue = RedisJobQueue()
        job_list = job_queue.list("queue:sync", 0, 100)
        job_list_json = [json.loads(job) for job in job_list]
        return Response(job_list_json)
