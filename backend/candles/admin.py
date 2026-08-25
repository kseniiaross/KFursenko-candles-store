from django.contrib import admin
from django.utils.html import format_html

from .models import (Candle, CandleImage, CandleVariant, Category, Collection,
                     Color, Fragrance, GalleryItem, Offer)


def color_dot(hex_value, size=18):
    """Small round swatch so colors are recognizable at a glance."""
    return format_html(
        '<span style="display:inline-block;width:{}px;height:{}px;'
        'border-radius:50%;border:1px solid rgba(0,0,0,.2);'
        'background:{};vertical-align:middle"></span>',
        size,
        size,
        hex_value,
    )


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "slug", "allows_wax_color")
    list_filter = ("allows_wax_color",)
    list_editable = ("allows_wax_color",)
    search_fields = ("name", "slug")
    ordering = ("name",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "parent", "is_group", "slug")
    search_fields = ("name", "slug", "parent__name")
    ordering = ("parent__name", "name")
    prepopulated_fields = {"slug": ("name",)}
    list_filter = ("is_group", "parent")


# =========================
# FRAGRANCE
# =========================
@admin.register(Fragrance)
class FragranceAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "slug", "size_count", "sizes")
    search_fields = ("name", "slug")
    ordering = ("name",)
    prepopulated_fields = {"slug": ("name",)}

    @admin.display(description="Sizes")
    def size_count(self, obj):
        return obj.candles.count()

    @admin.display(description="Available as")
    def sizes(self, obj):
        values = [c.size for c in obj.candles.order_by("size") if c.size]
        return ", ".join(values) or "—"


# =========================
# WAX COLOR
# =========================
@admin.register(Color)
class ColorAdmin(admin.ModelAdmin):
    list_display = ("swatch", "name", "hex", "sort_order", "candle_count")
    list_display_links = ("name",)
    list_editable = ("sort_order",)
    search_fields = ("name", "slug", "hex")
    ordering = ("sort_order", "name")
    prepopulated_fields = {"slug": ("name",)}

    @admin.display(description="")
    def swatch(self, obj):
        return color_dot(obj.hex, 22)

    @admin.display(description="Used by")
    def candle_count(self, obj):
        return obj.candles.count()


@admin.register(Offer)
class OfferAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "kind",
        "badge_text",
        "discount_percent",
        "discounted_price",
        "is_active",
        "priority",
    )
    list_filter = ("is_active", "kind")
    search_fields = ("title", "slug", "badge_text")
    ordering = ("priority", "title")
    prepopulated_fields = {"slug": ("title",)}
    filter_horizontal = ("categories", "collections", "candles")


# =========================
# INLINES
# =========================
class CandleVariantInline(admin.TabularInline):
    model = CandleVariant
    extra = 1
    fields = ("size", "price", "stock_qty", "is_active")
    ordering = ("id",)


class CandleImageInline(admin.TabularInline):
    model = CandleImage
    extra = 0
    max_num = 5
    fields = ("image", "sort_order")
    ordering = ("sort_order", "id")


# =========================
# CANDLE
# =========================
@admin.register(Candle)
class CandleAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "size",
        "fragrance",
        "wax_color",
        "fragrance_family",
        "intensity",
        "variant_stock_total",
        "has_active_stock",
        "is_sold_out",
        "is_bestseller",
        "created_at",
    )
    list_filter = (
        "category",
        "fragrance",
        "color",
        "size",
        "fragrance_family",
        "intensity",
        "is_sold_out",
        "is_bestseller",
        "created_at",
    )
    search_fields = (
        "name",
        "slug",
        "description",
        "fragrance_family",
        "fragrance__name",
        "mood_tags",
        "use_case_tags",
        "ideal_spaces",
        "season_tags",
    )
    ordering = ("-created_at",)
    prepopulated_fields = {"slug": ("name",)}

    readonly_fields = ("created_at", "variant_stock_total", "has_active_stock")
    list_editable = ("is_sold_out", "is_bestseller")
    list_select_related = ("fragrance", "color", "category")
    autocomplete_fields = ("fragrance", "color")
    filter_horizontal = ("collections", "offers")
    inlines = [CandleVariantInline, CandleImageInline]

    fieldsets = (
        (
            "Main",
            {
                "fields": (
                    "category",
                    "collections",
                    "offers",
                    "name",
                    "slug",
                    "description",
                    "image",
                    "price",
                ),
            },
        ),
        (
            "Scent & size",
            {
                "fields": (
                    "fragrance",
                    "size",
                ),
                "description": (
                    "Each size is its own product with its own catalog card. "
                    "Give both the 8 oz and the 11 oz the same fragrance, and "
                    "the product page will offer a switch between them."
                ),
            },
        ),
        (
            "Wax color",
            {
                "fields": ("color",),
                "description": (
                    "Molded candles only. Leave empty unless the category has "
                    "'allows wax color' enabled — otherwise saving will fail."
                ),
            },
        ),
        (
            "AI Search / Scent Profile",
            {
                "fields": (
                    "fragrance_family",
                    "intensity",
                    "top_notes",
                    "heart_notes",
                    "base_notes",
                    "mood_tags",
                    "use_case_tags",
                    "ideal_spaces",
                    "season_tags",
                ),
                "description": (
                    "Use JSON arrays for notes/tags. Example: "
                    '["cozy", "warm", "bedroom", "relaxing"]'
                ),
            },
        ),
        (
            "Display",
            {
                "fields": (
                    "is_sold_out",
                    "is_bestseller",
                ),
            },
        ),
        (
            "Variant stock summary",
            {
                "fields": (
                    "variant_stock_total",
                    "has_active_stock",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Meta",
            {
                "fields": ("created_at",),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.display(description="Color", ordering="color__name")
    def wax_color(self, obj):
        if not obj.color:
            return "—"
        return format_html("{} {}", color_dot(obj.color.hex, 14), obj.color.name)

    @admin.display(description="Variant stock total")
    def variant_stock_total(self, obj):
        return sum(
            variant.stock_qty
            for variant in obj.variants.all()
            if variant.is_active
        )

    @admin.display(boolean=True, description="Has active variant stock")
    def has_active_stock(self, obj):
        return obj.variants.filter(is_active=True, stock_qty__gt=0).exists()


# =========================
# GALLERY
# =========================
@admin.register(GalleryItem)
class GalleryItemAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "media_type",
        "sort_order",
        "is_active",
        "created_at",
    )
    list_filter = ("media_type", "is_active", "created_at")
    search_fields = ("title", "slug", "caption")
    ordering = ("sort_order", "-created_at", "id")
    list_editable = ("sort_order", "is_active")
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ("created_at",)

    fieldsets = (
        (
            "Content",
            {
                "fields": (
                    "title",
                    "slug",
                    "caption",
                ),
            },
        ),
        (
            "Media",
            {
                "fields": (
                    "media_type",
                    "media",
                    "preview_image",
                ),
            },
        ),
        (
            "Display",
            {
                "fields": (
                    "sort_order",
                    "is_active",
                ),
            },
        ),
        (
            "Meta",
            {
                "fields": ("created_at",),
                "classes": ("collapse",),
            },
        ),
    )