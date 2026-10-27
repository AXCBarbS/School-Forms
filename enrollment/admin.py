from django.contrib import admin
from .models import EnrollmentRecord


@admin.register(EnrollmentRecord)
class RecordAdmin(admin.ModelAdmin):
    list_display = ("school", "school_year", "status", "source", "updated_at")
    list_filter = ("status", "source", "school_year", "school__district")
    search_fields = ("school__name", "school__school_id")
    readonly_fields = ("created_by", "updated_by", "submitted_by", "created_at", "updated_at", "submitted_at")
