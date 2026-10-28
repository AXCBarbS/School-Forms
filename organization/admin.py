
from django.contrib import admin
from .models import District, School


@admin.register(District)
class DistrictAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = (
        "school_id",
        "name",
        "district",
        "school_type",
        "sector",
        "is_active",
    )
    list_filter = (
        "district",
        "school_type",
        "sector",
        "is_active",
    )
    search_fields = ("school_id", "name")
    list_editable = ("school_type",)
    list_per_page = 100
