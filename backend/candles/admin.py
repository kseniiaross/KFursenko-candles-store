from django.contrib import admin
from django.utils.html import format_html

from .models import (Candle, CandleImage, CandleVariant, Category, Collection,
                     Color, GalleryItem, Offer)


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
# WAX COLOR
# =========================
@admin.register(Color)
class ColorAdmin(admin.ModelAdmin):
    list_display = ("swatch", "name", "hex", "sort_order", "candle_count")
    list_display_links = ("name",)
    list_editable = ("sort_order",)
    search_fields = ("name", "hex")
    ordering = ("sort_order", "name")

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
    """Price and stock for this one candle.

    Capped at a single row: stacking two sizes here is what previously
    stopped the photos from switching, since a variant has no images of
    its own. A second size belongs in a second candle with the same name.
    """

    model = CandleVariant
    extra = 1
    max_num = 1
    fields = ("size", "price", "stock_qty", "is_active")
    verbose_name = "Price & stock"
    verbose_name_plural = "Price & stock"


class CandleImageInline(admin.TabularInline):
    model = CandleImage
    extra = 1
    max_num = 5
    fields = ("image", "sort_order")
    ordering = ("sort_order", "id")
    verbose_name = "Extra photo"
    verbose_name_plural = "More photos — shown after the cover, in sort order"


# =========================
# CANDLE
# =========================
@admin.register(Candle)
class CandleAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "size",
        "wax_color",
        "price",
        "sibling_sizes",
        "is_sold_out",
        "is_bestseller",
        "created_at",
    )
    list_filter = (
        "category",
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
        "mood_tags",
        "use_case_tags",
        "ideal_spaces",
        "season_tags",
    )
    ordering = ("-created_at",)

    readonly_fields = ("slug", "created_at")
    list_editable = ("is_sold_out", "is_bestseller")
    list_select_related = ("color", "category")
    autocomplete_fields = ("color",)
    filter_horizontal = ("collections", "offers")
    inlines = [CandleVariantInline, CandleImageInline]

    fieldsets = (
        (
            "Main",
            {
                "fields": (
                    "name",
                    "size",
                    "price",
                    "stock_qty",
                    "category",
                    "collections",
                    "offers",
                    "description",
                ),
                "description": (
                    "Candles sharing a name are one scent. To add a second "
                    "size, duplicate the candle, keep the name identical and "
                    "change the size — the product page will then switch "
                    "between them, photos included."
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
            "Display",
            {
                "fields": (
                    "is_sold_out",
                    "is_bestseller",
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
                "classes": ("collapse",),
                "description": (
                    "Use JSON arrays for notes/tags. Example: "
                    '["cozy", "warm", "bedroom", "relaxing"]'
                ),
            },
        ),
        (
            "Meta",
            {
                "fields": ("slug", "created_at"),
                "classes": ("collapse",),
            },
        ),
        # Last so the cover sits directly above the extra photos below.
        (
            "Cover photo",
            {
                "fields": ("image",),
                "description": "First photo on the card and the product page.",
            },
        ),
    )

    @admin.display(description="Color", ordering="color__name")
    def wax_color(self, obj):
        if not obj.color:
            return "—"
        return format_html("{} {}", color_dot(obj.color.hex, 14), obj.color.name)

    @admin.display(description="Also in")
    def sibling_sizes(self, obj):
        sizes = (
            Candle.objects.filter(name=obj.name)
            .exclude(pk=obj.pk)
            .exclude(size="")
            .values_list("size", flat=True)
        )
        return ", ".join(sorted(set(sizes))) or "—"


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
            {"fields": ("title", "slug", "caption")},
        ),
        (
            "Media",
            {"fields": ("media_type", "media", "preview_image")},
        ),
        (
            "Display",
            {"fields": ("sort_order", "is_active")},
        ),
        (
            "Meta",
            {"fields": ("created_at",), "classes": ("collapse",)},
        ),
    )