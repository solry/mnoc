from django.contrib import admin
from .models import Vlan, Device

admin.site.register(Vlan)
admin.site.register(Device)
