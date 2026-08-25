from decimal import Decimal

from rest_framework import serializers

from .models import (Candle, CandleImage, CandleVariant, Category, Collection,
                     Color, Fragrance, GalleryItem, Offer)

SUPPORTED_LOCALES = {"en", "ru", "es", "fr"}


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
        fields = ["id", "name", "slug", "hex"]


class FragranceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Fragrance
        fields = ["id", "name", "slug"]


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
    class Meta:
        model = CandleVariant
        fields = ["id", "size", "price", "stock_qty", "is_active"]


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

    fragrance = FragranceSerializer(read_only=True)
    fragrance_id = serializers.PrimaryKeyRelatedField(
        queryset=Fragrance.objects.all(),
        source="fragrance",
        write_only=True,
        required=False,
        allow_null=True,
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
        """Other sizes of the same scent. Each is its own catalog card;
        the product page uses this for the size switcher."""
        if not obj.fragrance_id:
            return []

        others = (
            Candle.objects.filter(fragrance_id=obj.fragrance_id)
            .exclude(size=obj.size)
            .exclude(pk=obj.pk)
            .order_by("size")
            .distinct("size")
            if False  # distinct("size") is Postgres-only and needs matching order_by
            else Candle.objects.filter(fragrance_id=obj.fragrance_id)
            .exclude(pk=obj.pk)
            .order_by("size")
        )

        return [
            {
                "id": c.id,
                "slug": c.slug,
                "size": c.size,
                "price": c.price,
                "is_sold_out": c.is_sold_out,
            }
            for c in others
        ]

    def get_color_options(self, obj):
        """Every wax color this candle exists in — same scent, same size.
        Each color is a separate product, so the swatch carries its slug
        and its own cover image for the product page."""
        if not obj.color_id or not obj.fragrance_id:
            return []

        group = (
            Candle.objects.filter(
                fragrance_id=obj.fragrance_id,
                size=obj.size,
                color__isnull=False,
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

    def _applicable_offers(self, obj):
        """Offers that apply to this candle: global, directly assigned (m2m
        and reverse m2m), by category, or by any of its collections."""
        qs = Offer.objects.filter(is_active=True)

        return (
            qs.filter(apply_globally=True)
            | obj.offers.filter(is_active=True)
            | qs.filter(candles=obj)
            | qs.filter(categories=obj.category)
            | qs.filter(collections__in=obj.collections.all())
        ).distinct()

    def get_badges(self, obj):
        combined = self._applicable_offers(obj)

        return CandleBadgeSerializer(
            combined.order_by("priority"),
            many=True,
        ).data

    def get_discount_price(self, obj):
        if not obj.price:
            return None

        base = Decimal(obj.price)
        offers = self._applicable_offers(obj).order_by("priority")

        for offer in offers:
            if offer.discount_percent:
                return base - (base * Decimal(offer.discount_percent) / 100)
            if offer.discounted_price:
                return offer.discounted_price

        return None


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