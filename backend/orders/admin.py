import stripe
from django.contrib import admin, messages
from django.db.models import Count, DecimalField, F, Sum, Value
from django.db.models.expressions import ExpressionWrapper
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.urls import path
from django.utils import timezone

from .models import Order, OrderItem, PaymentIncident
from .payments import IntentRelease, cancel_pending_order


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    autocomplete_fields = ("candle",)
    # The discount columns are what the shopper's cart showed for each line —
    # what a person handling a partial refund needs to see.
    fields = (
        "candle",
        "product_name",
        "unit_price",
        "quantity",
        "line_total_display",
        "free_quantity",
        "discount_amount",
        "discount_label",
    )
    readonly_fields = (
        "product_name",
        "unit_price",
        "quantity",
        "line_total_display",
        "free_quantity",
        "discount_amount",
        "discount_label",
    )

    def line_total_display(self, obj):
        if not obj.pk:
            return "-"
        return obj.line_total()

    line_total_display.short_description = "Line total"


class PaymentIncidentInline(admin.TabularInline):
    """Shown on the order itself, so whoever opens it sees the refund."""

    model = PaymentIncident
    extra = 0
    can_delete = False
    fields = ("created_at", "kind", "outcome", "amount", "stripe_refund_id", "resolved_at")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "status", "total_amount", "currency", "created_at")
    list_filter = ("status", "currency", "created_at")
    search_fields = ("id", "user__email", "stripe_payment_intent_id")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    # Status is read-only here: editing it directly would skip
    # Order.transition_to, and with it the stock that a cancellation or
    # refund returns. Cancel with the action below; other moves go through
    # the staff status endpoint.
    readonly_fields = (
        "status",
        "total_amount",
        "stripe_payment_intent_id",
        "created_at",
        "updated_at",
    )
    inlines = (OrderItemInline, PaymentIncidentInline)
    actions = ("cancel_unpaid_orders",)

    @admin.action(description="Cancel selected unpaid orders (returns stock)")
    def cancel_unpaid_orders(self, request, queryset):
        cancelled = 0
        skipped = queryset.exclude(status=Order.Status.PENDING).count()

        for order in queryset.filter(status=Order.Status.PENDING):
            try:
                outcome = cancel_pending_order(order)
            except (ValueError, stripe.StripeError) as error:
                self.message_user(
                    request, f"Order #{order.pk} not cancelled: {error}", messages.ERROR
                )
                continue

            if outcome is IntentRelease.IN_PROGRESS:
                self.message_user(
                    request,
                    f"Order #{order.pk} not cancelled: a payment is in progress.",
                    messages.WARNING,
                )
                continue

            cancelled += 1

        self.message_user(
            request,
            f"Cancelled {cancelled} order(s)."
            + (f" Skipped {skipped} that were not pending." if skipped else ""),
        )

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
                f"<tr><td>{row['user__email'] or row['user__id']}</td>"
                f"<td>{row['orders']}</td><td>{row['revenue']}</td></tr>"
            )
        html.append("</table>")

        html.append("<h2>Revenue by product</h2>")
        html.append("<table border='1' cellpadding='6' cellspacing='0'>")
        html.append("<tr><th>Product</th><th>Qty sold</th><th>Revenue</th></tr>")
        for row in by_product:
            html.append(
                f"<tr><td>{row['candle__name'] or row['candle__id']}</td>"
                f"<td>{row['qty']}</td><td>{row['revenue']}</td></tr>"
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



class UnresolvedFilter(admin.SimpleListFilter):
    title = "status"
    parameter_name = "state"

    def lookups(self, request, model_admin):
        return (("open", "Unresolved"), ("resolved", "Resolved"), ("all", "All"))

    def choices(self, changelist):
        # Open on unresolved by default: that list is the to-do.
        for value, label in self.lookup_choices:
            yield {
                "selected": (self.value() or "open") == value,
                "query_string": changelist.get_query_string({self.parameter_name: value}),
                "display": label,
            }

    def queryset(self, request, queryset):
        value = self.value() or "open"
        if value == "open":
            return queryset.filter(resolved_at__isnull=True)
        if value == "resolved":
            return queryset.filter(resolved_at__isnull=False)
        return queryset


@admin.register(PaymentIncident)
class PaymentIncidentAdmin(admin.ModelAdmin):
    """Payments taken for orders that will never ship.

    Each was refunded automatically (or the refund failed and says so). The
    list opens on the unresolved ones; mark them resolved once checked
    against the Stripe dashboard.
    """

    list_display = (
        "created_at",
        "order",
        "kind",
        "outcome",
        "amount",
        "currency",
        "stripe_refund_id",
        "resolved_at",
    )
    list_filter = (UnresolvedFilter, "outcome", "kind")
    search_fields = ("order__id", "stripe_payment_intent_id", "stripe_refund_id")
    readonly_fields = (
        "order",
        "kind",
        "outcome",
        "amount",
        "currency",
        "stripe_payment_intent_id",
        "stripe_refund_id",
        "detail",
        "created_at",
        "updated_at",
        "resolved_at",
    )
    actions = ("mark_resolved",)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Mark selected incidents resolved")
    def mark_resolved(self, request, queryset):
        updated = queryset.filter(resolved_at__isnull=True).update(resolved_at=timezone.now())
        self.message_user(request, f"Marked {updated} incident(s) resolved.")
