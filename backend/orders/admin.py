import stripe
from django.conf import settings
from django.contrib import admin, messages
from django.db import transaction
from django.db.models import Case, Count, DecimalField, F, Sum, Value, When
from django.db.models.expressions import ExpressionWrapper
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

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
        "restocked_quantity",
    )
    readonly_fields = (
        "product_name",
        "unit_price",
        "quantity",
        "line_total_display",
        "free_quantity",
        "discount_amount",
        "discount_label",
        "restocked_quantity",
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


def _money(amount, currency):
    return f"{amount:.2f} {(currency or 'usd').upper()}"


def stripe_payment_url(intent_id: str) -> str:
    """The payment in the Stripe dashboard, in the mode the shop runs in."""
    mode = "test/" if settings.STRIPE_SECRET_KEY.startswith("sk_test") else ""
    return f"https://dashboard.stripe.com/{mode}payments/{intent_id}"


class RefundFilter(admin.SimpleListFilter):
    title = "refunds"
    parameter_name = "refunds"

    def lookups(self, request, model_admin):
        return (("partly", "Partly refunded"), ("fully", "Fully refunded"))

    def queryset(self, request, queryset):
        if self.value() == "partly":
            return queryset.filter(refunded_amount__gt=0).exclude(status=Order.Status.REFUNDED)
        if self.value() == "fully":
            return queryset.filter(status=Order.Status.REFUNDED)
        return queryset


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id", "user", "status", "total_amount", "refunded_display", "currency", "created_at",
    )
    list_filter = ("status", RefundFilter, "currency", "created_at")
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
        "refunds",
        "refunded_amount",
        "stripe_payment_intent_id",
        "created_at",
        "updated_at",
    )
    inlines = (OrderItemInline, PaymentIncidentInline)
    actions = ("cancel_unpaid_orders",)

    @admin.display(description="Refunded")
    def refunded_display(self, obj):
        if not obj.refunded_amount:
            return "—"
        return f"{_money(obj.refunded_amount, obj.currency)} of {obj.total_amount:.2f}"

    @admin.display(description="Refunds")
    def refunds(self, obj):
        """What has gone back, where to refund, and where to put back stock
        for a candle that won't be sent."""
        if not obj.pk:
            return "—"

        so_far = (
            f"Refunded so far: {_money(obj.refunded_amount, obj.currency)} "
            f"of {_money(obj.total_amount, obj.currency)}."
        )
        items_url = (
            reverse("admin:orders_orderitem_changelist") + f"?order__id__exact={obj.pk}"
        )

        if not obj.stripe_payment_intent_id:
            return so_far

        return format_html(
            "{} Refunds are made in Stripe: <a href=\"{}\" target=\"_blank\" rel=\"noopener\">"
            "open this payment</a>; this order updates itself. "
            "A candle refunded before shipping: <a href=\"{}\">return items to stock</a>.",
            so_far,
            stripe_payment_url(obj.stripe_payment_intent_id),
            items_url,
        )

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
        """Money the shop kept. Only orders whose payment was taken count —
        not PENDING or CANCELED ones — and refunds come off: a REFUNDED order
        counts as fully refunded even if it was marked by hand before
        refunds were recorded."""
        paid_statuses = (
            Order.Status.PAID,
            Order.Status.SHIPPED,
            Order.Status.COMPLETED,
            Order.Status.REFUNDED,
        )
        qs = Order.objects.filter(status__in=paid_statuses)

        date_from = request.GET.get("from")
        date_to = request.GET.get("to")

        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)

        money = DecimalField(max_digits=12, decimal_places=2)
        zero = Value(0, output_field=money)
        refunded = Case(
            When(status=Order.Status.REFUNDED, then=F("total_amount")),
            default=F("refunded_amount"),
            output_field=money,
        )
        net = ExpressionWrapper(F("total_amount") - refunded, output_field=money)

        totals = qs.aggregate(
            orders_count=Count("id"),
            gross=Coalesce(Sum("total_amount"), zero),
            refunded=Coalesce(Sum(refunded), zero),
            revenue=Coalesce(Sum(net), zero),
        )

        by_user = (
            qs.values("user__id", "user__email")
            .annotate(orders=Count("id"), revenue=Coalesce(Sum(net), zero))
            .order_by("-revenue")
        )

        # Lines of orders that weren't refunded in full, after their
        # discounts and without units put back on the shelf. A partial
        # refund isn't split across products, so it only shows in the totals.
        items_qs = OrderItem.objects.filter(order__in=qs.exclude(status=Order.Status.REFUNDED))

        line_net_expr = ExpressionWrapper(
            F("unit_price") * (F("quantity") - F("restocked_quantity")) - F("discount_amount"),
            output_field=money,
        )

        by_product = (
            items_qs.values("candle__id", "candle__name")
            .annotate(
                qty=Coalesce(Sum(F("quantity") - F("restocked_quantity")), Value(0)),
                revenue=Coalesce(Sum(line_net_expr), zero),
            )
            .order_by("-revenue")
        )

        html = ["<h1>Orders Reports</h1>"]
        html.append("<p><b>Filter:</b> ?from=YYYY-MM-DD&to=YYYY-MM-DD</p>")
        html.append(
            "<p>Paid orders only (paid, shipped, completed, refunded). "
            "Revenue is what was charged less what was refunded.</p>"
        )
        html.append(
            f"<p><b>Paid orders:</b> {totals['orders_count']} &nbsp; "
            f"<b>Charged:</b> {totals['gross']} &nbsp; "
            f"<b>Refunded:</b> {totals['refunded']} &nbsp; "
            f"<b>Revenue:</b> {totals['revenue']}</p>"
        )

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
        html.append(
            "<p>After line discounts, without refunded orders or units returned "
            "to stock. Partial refunds and shipping aren't split across products.</p>"
        )
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
    list_display = (
        "id", "order", "order_status", "candle", "product_name", "unit_price",
        "quantity", "restocked_quantity", "line_total_display",
    )
    list_filter = ("order__status",)
    search_fields = ("order__id", "product_name", "candle__name", "candle__slug")
    autocomplete_fields = ("order", "candle")
    readonly_fields = ("order", "candle", "product_name", "unit_price", "restocked_quantity")
    actions = ("return_one_to_stock",)

    @admin.display(description="Order status")
    def order_status(self, obj):
        return obj.order.get_status_display()

    @admin.action(description="Return items to stock: one unit of each selected line")
    def return_one_to_stock(self, request, queryset):
        """For a candle refunded before the order ships: it stays on the
        shelf. One unit per line per run, so the count is deliberate. Only
        for PAID orders — once shipped, a candle can't come back (a lit one
        can't be sold again), and a full refund returns the rest itself."""
        from candles.models import CandleVariant

        returned = 0

        for item_id in queryset.values_list("pk", flat=True):
            with transaction.atomic():
                item = (
                    OrderItem.objects.select_for_update(of=("self",))
                    .select_related("order")
                    .get(pk=item_id)
                )
                order = Order.objects.select_for_update().get(pk=item.order_id)

                if order.status != Order.Status.PAID:
                    self.message_user(
                        request,
                        f"{item.product_name} on order #{order.pk} not returned: the "
                        f"order is {order.get_status_display().lower()}, not paid and "
                        f"waiting to ship.",
                        messages.WARNING,
                    )
                    continue

                if item.restocked_quantity >= item.quantity:
                    self.message_user(
                        request,
                        f"{item.product_name} on order #{order.pk}: all "
                        f"{item.quantity} already returned to stock.",
                        messages.WARNING,
                    )
                    continue

                if not item.variant_id:
                    self.message_user(
                        request,
                        f"{item.product_name} on order #{order.pk} has no variant to restock.",
                        messages.ERROR,
                    )
                    continue

                item.restocked_quantity += 1
                item.save(update_fields=["restocked_quantity"])
                CandleVariant.objects.filter(pk=item.variant_id).update(
                    stock_qty=F("stock_qty") + 1
                )
                returned += 1

        if returned:
            self.message_user(request, f"Returned {returned} unit(s) to stock.")

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
