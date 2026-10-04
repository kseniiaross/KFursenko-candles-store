from rest_framework import serializers

from .models import (Candle, CandleImage, CandleVariant, Category, Collection,
                     Color, GalleryItem, Offer)

from orders.discounts import (campaign_offer_for, get_active_offers,
                              get_welcome_offer, offer_applies_to,
                              unit_display_prices)

SUPPORTED_LOCALES = {"en", "ru", "es", "fr"}


# ======================================================
# PRICES
# ======================================================
# Every price here comes from orders.discounts — the same functions checkout
# charges with. Nothing in this module works out a discount itself.
def _pricing(context):
    """Offers, the shopper's welcome offer and the unit prices worked out so
    far for this response.

    Kept in the serializer context, which every candle in a list (and every
    variant nested in it) shares, so a catalogue page looks offers up once.
    """
    pricing = context.get("_pricing")

    if pricing is None:
        request = context.get("request")
        user = getattr(request, "user", None)
        pricing = {
            "user": user,
            "offers": get_active_offers(),
            "welcome": get_welcome_offer(user),
            "units": {},
        }
        context["_pricing"] = pricing

    return pricing


def unit_price_for(context, variant):
    """What one of this variant costs this shopper — as checkout charges it."""
    pricing = _pricing(context)

    if variant.id not in pricing["units"]:
        pricing["units"].update(
            unit_display_prices(
                user=pricing["user"],
                variants=[variant],
                offers=pricing["offers"],
                welcome_offer=pricing["welcome"],
            )
        )

    return pricing["units"][variant.id]


# ======================================================
# IMAGE UTILS
# ======================================================
def build_cloudinary_image_url(image, width=1000, height=1250):
    """Card frames are 4:5. `limit` only downscales — it never crops,
    so whatever aspect ratio was uploaded is preserved."""
    if not image:
        return None
    try:
        return image.build_url(
            secure=True,
            fetch_format="auto",
            quality="auto",
            width=width,
            height=height,
            crop="limit",
        )
    except Exception:
        return str(image)


# ======================================================
# LOCALE HELPERS
# ======================================================
def get_locale_from_request(request):
    if not request:
        return "en"

    query_locale = (request.query_params.get("lang") or "").lower().strip()
    if query_locale in SUPPORTED_LOCALES:
        return query_locale

    header = (request.headers.get("Accept-Language") or "").lower().strip()
    for locale in SUPPORTED_LOCALES:
        if header.startswith(locale):
            return locale

    return "en"


def localized_value(obj, field_name, locale):
    translated = getattr(obj, f"{field_name}_{locale}", "") or ""
    fallback = getattr(obj, field_name, "") or ""
    return translated.strip() or fallback


# ======================================================
# BASIC
# ======================================================
class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "slug", "allows_wax_color"]


class ColorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Color
        fields = ["id", "name", "hex"]


class CollectionSerializer(serializers.ModelSerializer):
    parent = serializers.SerializerMethodField()
    children = serializers.SerializerMethodField()

    class Meta:
        model = Collection
        fields = ["id", "name", "slug", "is_group", "parent", "children"]

    def get_parent(self, obj):
        if not obj.parent_id:
            return None
        return {
            "id": obj.parent_id,
            "name": obj.parent.name,
            "slug": obj.parent.slug,
        }

    def get_children(self, obj):
        return [
            {"id": c.id, "name": c.name, "slug": c.slug}
            for c in obj.children.all()
        ]


# ======================================================
# MEDIA
# ======================================================
class CandleImageSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model = CandleImage
        fields = ["id", "image", "sort_order"]

    def get_image(self, obj):
        return build_cloudinary_image_url(obj.image)


class CandleVariantSerializer(serializers.ModelSerializer):
    # What one of this variant costs the shopper making the request, from
    # the same function checkout charges with. Equal to `price` when no
    # offer applies to a single unit (buy-two-get-three needs three).
    display_price = serializers.SerializerMethodField()

    class Meta:
        model = CandleVariant
        fields = ["id", "size", "price", "display_price", "stock_qty", "is_active"]

    def get_display_price(self, obj):
        return str(unit_price_for(self.context, obj).display_price)


class CandleBadgeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Offer
        fields = ["slug", "badge_text", "kind", "discount_percent", "priority"]


# ======================================================
# CANDLE
# ======================================================
class CandleSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()

    images = CandleImageSerializer(many=True, read_only=True)
    variants = CandleVariantSerializer(many=True, read_only=True)

    category = CategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        source="category",
        write_only=True,
    )

    color = ColorSerializer(read_only=True)
    color_id = serializers.PrimaryKeyRelatedField(
        queryset=Color.objects.all(),
        source="color",
        write_only=True,
        required=False,
        allow_null=True,
    )

    collections = CollectionSerializer(many=True, read_only=True)
    collection_ids = serializers.PrimaryKeyRelatedField(
        queryset=Collection.objects.all(),
        source="collections",
        many=True,
        write_only=True,
        required=False,
    )

    badges = serializers.SerializerMethodField()
    discount_price = serializers.SerializerMethodField()
    siblings = serializers.SerializerMethodField()
    color_options = serializers.SerializerMethodField()

    class Meta:
        model = Candle
        fields = "__all__"
        read_only_fields = [
            "slug",
            "created_at",
            "images",
            "variants",
            "badges",
            "discount_price",
            "siblings",
            "color_options",
        ]

    def get_name(self, obj):
        return localized_value(
            obj, "name", get_locale_from_request(self.context.get("request"))
        )

    def get_description(self, obj):
        return localized_value(
            obj, "description", get_locale_from_request(self.context.get("request"))
        )

    def get_image(self, obj):
        return build_cloudinary_image_url(obj.image)

    def get_siblings(self, obj):
        """The same scent in other sizes. Candles are matched by name —
        that is what a shopper reads as 'the same candle'."""
        others = (
            Candle.objects.filter(name=obj.name)
            .exclude(pk=obj.pk)
            .exclude(size="")
            .order_by("size")
        )

        seen = set()
        result = []

        for candle in others:
            # One entry per size — wax colors get their own switcher.
            if candle.size in seen:
                continue

            seen.add(candle.size)
            result.append(
                {
                    "id": candle.id,
                    "slug": candle.slug,
                    "size": candle.size,
                    "price": candle.price,
                    "is_sold_out": candle.is_sold_out,
                }
            )

        return result

    def get_color_options(self, obj):
        """Every wax color of this candle in this size. Each color is its
        own product, so the swatch carries a slug and its own cover."""
        if not obj.color_id:
            return []

        group = (
            Candle.objects.filter(
                name=obj.name, size=obj.size, color__isnull=False
            )
            .select_related("color")
            .order_by("color__sort_order", "color__name")
        )

        return [
            {
                "id": c.id,
                "slug": c.slug,
                "image": build_cloudinary_image_url(c.image),
                "color": ColorSerializer(c.color).data,
                "is_current": c.pk == obj.pk,
                "is_sold_out": c.is_sold_out,
            }
            for c in group
        ]
    def get_badges(self, obj):
        """The offer checkout would apply to this candle, if it shows a badge.

        Same precedence as compute_line_discounts: a campaign claims the
        candle; the welcome offer only lands on a candle with no campaign,
        and only for a shopper who qualifies. Never both, so a card can't
        advertise two offers when only one will apply.
        """
        pricing = _pricing(self.context)
        campaign = campaign_offer_for(obj, pricing["offers"])
        welcome = pricing["welcome"]

        if campaign:
            applies = [campaign]
        elif welcome and offer_applies_to(welcome, obj):
            applies = [welcome]
        else:
            applies = []

        return CandleBadgeSerializer(
            [offer for offer in applies if offer.show_badge], many=True
        ).data

    def get_discount_price(self, obj):
        """The card's sale price, or None when the card shows the full price.

        One unit of the cheapest active variant, priced the way checkout
        charges it. Offer.discounted_price is never shown: checkout has never
        applied it, so showing it promised a price nobody was charged.
        """
        active = [v for v in obj.variants.all() if v.is_active]

        if not active:
            return None

        unit = unit_price_for(self.context, min(active, key=lambda v: v.price))

        return unit.display_price if unit.display_price < unit.price else None


# ======================================================
# GALLERY
# ======================================================
class GalleryItemSerializer(serializers.ModelSerializer):
    media = serializers.SerializerMethodField()
    preview_image = serializers.SerializerMethodField()

    class Meta:
        model = GalleryItem
        fields = "__all__"

    def get_media(self, obj):
        return build_cloudinary_image_url(obj.media, 1200, 800)

    def get_preview_image(self, obj):
        return build_cloudinary_image_url(obj.preview_image, 1200, 800)