from django.contrib import admin
from django.utils.html import format_html

from .models import Shipment


@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display = ("id", "order", "status", "carrier", "tracking_number", "is_test")
    list_filter = ("status", "carrier", "is_test")
    search_fields = ("order__id", "tracking_number", "transaction_id")
    readonly_fields = ("created_at", "updated_at", "label_link")

    def label_link(self, obj):
        if not obj.label_url:
            return "—"
        return format_html('<a href="{}" target="_blank">Open label</a>', obj.label_url)

    label_link.short_description = "Label"
