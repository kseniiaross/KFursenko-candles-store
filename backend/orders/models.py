from decimal import Decimal

from collections import defaultdict

from django.conf import settings
from django.db import models, transaction
from django.db.models import F


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        CANCELED = "canceled", "Canceled"
        SHIPPED = "shipped", "Shipped"
        COMPLETED = "completed", "Completed"
        REFUNDED = "refunded", "Refunded"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="orders",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )

    currency = models.CharField(max_length=10, default="usd")

    subtotal_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )

        # Worked out server-side at checkout; the storefront never sends it.
    discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    discount_label = models.CharField(max_length=160, blank=True, default="")

    # Worked out server-side at checkout; the storefront never sends it.
    discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    discount_label = models.CharField(max_length=160, blank=True, default="")

    shipping_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    tax_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    total_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    shipping_full_name = models.CharField(max_length=255, blank=True, default="")
    shipping_line1 = models.CharField(max_length=255, blank=True, default="")
    shipping_line2 = models.CharField(max_length=255, blank=True, default="")
    shipping_city = models.CharField(max_length=255, blank=True, default="")
    shipping_state = models.CharField(max_length=255, blank=True, default="")
    shipping_postal_code = models.CharField(max_length=64, blank=True, default="")
    shipping_country = models.CharField(max_length=120, blank=True, default="United States")
    shipping_phone = models.CharField(max_length=32, blank=True, default="")

    stripe_payment_intent_id = models.CharField(max_length=255, blank=True, default="")
    stripe_tax_calculation_id = models.CharField(max_length=255, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["status"]),
            models.Index(fields=["created_at"]),
        ]
        ordering = ["-created_at"]

    ALLOWED_TRANSITIONS = {
        Status.PENDING: {Status.PAID, Status.CANCELED},
        Status.PAID: {Status.SHIPPED, Status.REFUNDED},
        Status.SHIPPED: {Status.COMPLETED},
        Status.COMPLETED: set(),
        Status.CANCELED: set(),
        Status.REFUNDED: set(),
    }

    # Transitions after which the goods will never ship, so the stock that
    # build_order reserved goes back on the shelf. PAID -> REFUNDED belongs
    # here because SHIPPED -> REFUNDED is not allowed: a refunded order was
    # never sent. Anything after shipping is a return, and whether a returned
    # candle is sellable is a person's call, not this method's.
    STOCK_RELEASING_TRANSITIONS = {
        (Status.PENDING, Status.CANCELED),
        (Status.PAID, Status.REFUNDED),
    }

    def can_transition(self, new_status: str) -> bool:
        return new_status in self.ALLOWED_TRANSITIONS.get(self.status, set())

    def transition_to(self, new_status: str):
        """Move to `new_status`, releasing stock when the goods won't ship.

        The row is re-read under a lock, so two concurrent cancels cannot
        both pass the check and restore the stock twice.
        """
        with transaction.atomic():
            locked = Order.objects.select_for_update().get(pk=self.pk)

            if not locked.can_transition(new_status):
                raise ValueError(
                    f"Cannot transition from {locked.status} to {new_status}"
                )

            previous = locked.status
            locked.status = new_status
            locked.save(update_fields=["status", "updated_at"])

            if (previous, new_status) in self.STOCK_RELEASING_TRANSITIONS:
                locked._release_stock()

        self.status = new_status
        self.updated_at = locked.updated_at

    def _release_stock(self):
        """Return every item's quantity to its variant. Call inside the
        transaction that changed the status — never on its own."""
        from candles.models import CandleVariant

        per_variant = defaultdict(int)

        for item in self.items.all():
            # Every row has a variant since migration 0010; a null here would
            # mean a row nobody can restock automatically.
            if item.variant_id:
                per_variant[item.variant_id] += item.quantity

        for variant_id, quantity in per_variant.items():
            CandleVariant.objects.filter(pk=variant_id).update(
                stock_qty=F("stock_qty") + quantity
            )

    def __str__(self) -> str:
        return f"Order #{self.id} ({self.status})"


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
    )

    candle = models.ForeignKey(
        "candles.Candle",
        on_delete=models.PROTECT,
        related_name="order_items",
    )

    variant = models.ForeignKey(
        "candles.CandleVariant",
        on_delete=models.PROTECT,
        related_name="order_items",
        null=True,
        blank=True,
        help_text="The exact variant ordered. Null on rows created before "
                  "this field existed.",
    )

    product_name = models.CharField(max_length=255)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)
    is_gift = models.BooleanField(default=False)

    # This line's share of the order discount, so a partial refund knows how
    # much of it travels back with a returned candle. The lines of an order
    # always sum to Order.discount_amount. Zero on rows created before the
    # field existed — their discount was only ever stored on the order.
    discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    discount_label = models.CharField(max_length=160, blank=True, default="")

    def line_total(self):
        return (self.unit_price or Decimal("0.00")) * Decimal(self.quantity or 0)

    def __str__(self) -> str:
        return f"{self.product_name} x{self.quantity}"

class PaymentIncident(models.Model):
    """Money Stripe took for an order that will never ship, and what was done.

    Written by the webhook when a payment succeeds on an order that is
    already CANCELED or REFUNDED. The payment is refunded automatically; this
    row is what makes that visible in the admin rather than only in the logs,
    and it stays "unresolved" until a person has looked at it.
    """

    class Kind(models.TextChoices):
        PAID_AFTER_CANCEL = "paid_after_cancel", "Paid after the order was cancelled"
        PAID_AFTER_REFUND = "paid_after_refund", "Paid again after the order was refunded"

    class Outcome(models.TextChoices):
        REFUNDED = "refunded", "Refunded automatically"
        REFUND_FAILED = "refund_failed", "Refund FAILED — refund it by hand in Stripe"

    order = models.ForeignKey(
        Order, on_delete=models.PROTECT, related_name="payment_incidents"
    )
    kind = models.CharField(max_length=32, choices=Kind.choices)
    outcome = models.CharField(max_length=32, choices=Outcome.choices, db_index=True)

    # One incident per payment: Stripe redelivers webhooks, and a redelivery
    # must find this row rather than refund or alert a second time.
    stripe_payment_intent_id = models.CharField(max_length=255, unique=True)
    stripe_refund_id = models.CharField(max_length=255, blank=True, default="")

    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default="usd")
    detail = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} — order #{self.order_id} ({self.get_outcome_display()})"
