from django.contrib import admin
from .models import District, School


@admin.register(District)
class DistrictAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")
    search_fields = ("name",)


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ("school_id", "name", "district", "sector", "is_active")
    list_filter = ("district", "sector", "is_active")
    search_fields = ("school_id", "name")
