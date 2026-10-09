from django.contrib import admin

from .models import SpikeAlert


@admin.register(SpikeAlert)
class SpikeAlertAdmin(admin.ModelAdmin):
    list_display = ["day", "category", "reason", "count", "baseline", "ratio", "updated_at"]
    list_filter = ["category"]
    date_hierarchy = "day"
    list_select_related = ["category", "reason"]
    readonly_fields = ["created_at", "updated_at"]
    filter_horizontal = ["read_by"]
