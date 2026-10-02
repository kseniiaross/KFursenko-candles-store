from django.db import models


class Shipment(models.Model):
    """One row per order, holding whatever Shippo has told us about it.

    OneToOne rather than FK: the status field below is what stops a double
    purchase, and that only works if there is exactly one row to lock.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PURCHASING = "purchasing", "Purchasing"
        PURCHASED = "purchased", "Purchased"
        FAILED = "failed", "Failed"
        REFUNDED = "refunded", "Refunded"

    order = models.OneToOneField(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="shipment",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )

    # Chosen at checkout, before the Stripe intent exists. Rate objects expire
    # on Shippo's side, so treat a stale one as a reason to re-quote.
    rate_id = models.CharField(max_length=64, blank=True, default="")
    shippo_shipment_id = models.CharField(max_length=64, blank=True, default="")
    transaction_id = models.CharField(max_length=64, blank=True, default="")

    carrier = models.CharField(max_length=80, blank=True, default="")
    service_level = models.CharField(max_length=160, blank=True, default="")

    amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=10, blank=True, default="usd")

    tracking_number = models.CharField(max_length=128, blank=True, default="")
    tracking_url = models.URLField(max_length=500, blank=True, default="")

    # Shippo does not host these forever. Mirror the PDF to Cloudinary before
    # the link rots if you need long-term access.
    label_url = models.URLField(max_length=500, blank=True, default="")

    is_test = models.BooleanField(default=True)
    error_message = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["tracking_number"]),
        ]

    def __str__(self) -> str:
        return f"Shipment for order #{self.order_id} ({self.status})"
