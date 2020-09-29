from django.urls import re_path, include
from .api import VlanViewSet, DeviceViewSet, RpcListTaskQueueView
from rest_framework.routers import DefaultRouter


app_name = "service_directory"
urlpatterns = []
router = DefaultRouter()

router.register(r"vlans", VlanViewSet, basename="vlans")
router.register(r"devices", DeviceViewSet, basename="devices")

urlpatterns.append(re_path(r"api/", include(router.urls)))
urlpatterns.append(re_path(r"api/rpc_list_task_queue/$", RpcListTaskQueueView.as_view()))
