from django.contrib import admin
from django.db.models import Count, DecimalField, F, Sum, Value
from django.db.models.functions import Coalesce
from django.db.models.expressions import ExpressionWrapper
from django.http import HttpResponse
from django.urls import path

from .models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    autocomplete_fields = ("candle",)
    fields = ("candle", "product_name", "unit_price", "quantity", "line_total_display")
    readonly_fields = ("product_name", "unit_price", "quantity", "line_total_display")

    def line_total_display(self, obj):
        if not obj.pk:
            return "-"
        return obj.line_total()

    line_total_display.short_description = "Line total"


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "status", "total_amount", "currency", "created_at")
    list_filter = ("status", "currency", "created_at")
    search_fields = ("id", "user__email", "stripe_payment_intent_id")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    readonly_fields = ("total_amount", "stripe_payment_intent_id", "created_at", "updated_at")
    inlines = (OrderItemInline,)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "reports/",
                self.admin_site.admin_view(self.reports_view),
                name="orders_order_reports",
            ),
        ]
        return custom_urls + urls

    def reports_view(self, request):
        qs = Order.objects.all()

        date_from = request.GET.get("from")
        date_to = request.GET.get("to")

        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)

        totals = qs.aggregate(
            orders_count=Count("id"),
            revenue=Coalesce(
                Sum("total_amount"),
                Value(0, output_field=DecimalField(max_digits=12, decimal_places=2)),
            ),
        )

        by_user = (
            qs.values("user__id", "user__email")
            .annotate(
                orders=Count("id"),
                revenue=Coalesce(
                    Sum("total_amount"),
                    Value(0, output_field=DecimalField(max_digits=12, decimal_places=2)),
                ),
            )
            .order_by("-revenue")
        )

        items_qs = OrderItem.objects.select_related("order", "candle").filter(order__in=qs)

        line_total_expr = ExpressionWrapper(
            F("unit_price") * F("quantity"),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )

        by_product = (
            items_qs.values("candle__id", "candle__name")
            .annotate(
                qty=Coalesce(Sum("quantity"), Value(0)),
                revenue=Coalesce(
                    Sum(line_total_expr),
                    Value(0, output_field=DecimalField(max_digits=12, decimal_places=2)),
                ),
            )
            .order_by("-revenue")
        )

        html = ["<h1>Orders Reports</h1>"]
        html.append("<p><b>Filter:</b> ?from=YYYY-MM-DD&to=YYYY-MM-DD</p>")
        html.append(f"<p><b>Orders:</b> {totals['orders_count']} &nbsp; <b>Revenue:</b> {totals['revenue']}</p>")

        html.append("<h2>Revenue by user</h2>")
        html.append("<table border='1' cellpadding='6' cellspacing='0'>")
        html.append("<tr><th>User</th><th>Orders</th><th>Revenue</th></tr>")
        for row in by_user:
            html.append(
                f"<tr><td>{row['user__email'] or row['user__id']}</td><td>{row['orders']}</td><td>{row['revenue']}</td></tr>"
            )
        html.append("</table>")

        html.append("<h2>Revenue by product</h2>")
        html.append("<table border='1' cellpadding='6' cellspacing='0'>")
        html.append("<tr><th>Product</th><th>Qty sold</th><th>Revenue</th></tr>")
        for row in by_product:
            html.append(
                f"<tr><td>{row['candle__name'] or row['candle__id']}</td><td>{row['qty']}</td><td>{row['revenue']}</td></tr>"
            )
        html.append("</table>")

        return HttpResponse("".join(html))


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("id", "order", "candle", "product_name", "unit_price", "quantity", "line_total_display")
    list_filter = ("order__status",)
    search_fields = ("order__id", "product_name", "candle__name", "candle__slug")
    autocomplete_fields = ("order", "candle")
    readonly_fields = ("order", "candle", "product_name", "unit_price")

    def line_total_display(self, obj):
        return obj.line_total()

    line_total_display.short_description = "Line total"