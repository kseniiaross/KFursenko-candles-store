from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .filters import CandleFilter
from .models import Candle, Category, Collection, GalleryItem
from .permissions import IsStaffOrReadOnly
from .serializers import (CandleSerializer, CategorySerializer,
                          CollectionSerializer, GalleryItemSerializer)


def collection_tree_ids(collection):
    """A collection and every collection nested under it.

    A candle attached only to a berry sub-collection must still appear
    under Spring-Summer, so filtering by a parent has to reach the
    whole subtree, not just its direct children.
    """
    ids = [collection.id]
    frontier = [collection.id]

    while frontier:
        children = list(
            Collection.objects.filter(parent_id__in=frontier).values_list(
                "id", flat=True
            )
        )
        children = [cid for cid in children if cid not in ids]

        if not children:
            break

        ids.extend(children)
        frontier = children

    return ids


# =========================
# CATEGORY
# =========================
class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    search_fields = ["name", "slug"]
    filter_backends = [filters.SearchFilter]
    permission_classes = [IsStaffOrReadOnly]


# =========================
# COLLECTION
# =========================
class CollectionViewSet(viewsets.ModelViewSet):
    queryset = Collection.objects.select_related("parent").prefetch_related("children")
    serializer_class = CollectionSerializer
    search_fields = ["name", "slug"]
    filter_backends = [filters.SearchFilter]
    permission_classes = [IsStaffOrReadOnly]

    def get_queryset(self):
        qs = super().get_queryset()

        root = (self.request.query_params.get("root") or "").strip()
        parent = (self.request.query_params.get("parent") or "").strip()

        if root == "1":
            return qs.filter(parent__isnull=True).order_by("name")

        if parent:
            if parent.isdigit():
                return qs.filter(parent_id=int(parent)).order_by("name")
            return qs.filter(parent__slug__iexact=parent).order_by("name")

        return qs.order_by("name")

    @action(detail=True, methods=["get"])
    def detail(self, request, pk=None):
        collection = self.get_object()

        candles = (
            Candle.objects.select_related("category", "color", "fragrance")
            .prefetch_related(
                "collections",
                "images",
                "variants",
                "offers",
            )
            .filter(collections__id__in=collection_tree_ids(collection))
            .distinct()
        )

        serializer = CandleSerializer(candles, many=True, context={"request": request})
        return Response(serializer.data)


# =========================
# CANDLES
# =========================
class CandleViewSet(viewsets.ModelViewSet):
    queryset = (
        Candle.objects.select_related("category", "color", "fragrance")
        .prefetch_related(
            "collections",
            "images",
            "variants",
            "offers",
        )
        .all()
    )
    serializer_class = CandleSerializer
    lookup_field = "slug"
    permission_classes = [IsStaffOrReadOnly]

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_class = CandleFilter

    search_fields = [
        "name",
        "description",
        "slug",
        "collections__name",
        "category__name",
    ]
    ordering_fields = ["price", "created_at", "name"]
    ordering = ["-created_at"]

    def get_queryset(self):
        qs = super().get_queryset()

        collection_slug = (self.request.query_params.get("collection") or "").strip()

        if collection_slug:
            collection = Collection.objects.filter(
                slug__iexact=collection_slug
            ).first()

            # An unknown slug must return nothing — falling through to an
            # unfiltered list would quietly show the entire catalog.
            if not collection:
                return qs.none()

            qs = qs.filter(
                collections__id__in=collection_tree_ids(collection)
            ).distinct()

        return qs

    @action(detail=True, methods=["get"])
    def collection_scents(self, request, slug=None):
        candle = self.get_object()

        child_collection = candle.collections.filter(parent__isnull=False).first()
        if not child_collection:
            child_collection = candle.collections.filter(parent__isnull=True).first()

        if not child_collection:
            return Response([])

        sibling_candles = (
            Candle.objects.select_related("category", "color", "fragrance")
            .prefetch_related(
                "collections",
                "images",
                "variants",
                "offers",
            )
            .filter(collections=child_collection)
            .exclude(id=candle.id)
            .distinct()
            .order_by("name")
        )

        serializer = CandleSerializer(
            sibling_candles,
            many=True,
            context={"request": request},
        )
        return Response(serializer.data)


# =========================
# GALLERY
# =========================
class GalleryItemViewSet(viewsets.ModelViewSet):
    serializer_class = GalleryItemSerializer
    permission_classes = [IsStaffOrReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["title", "slug", "caption"]
    ordering_fields = ["sort_order", "created_at", "title"]
    ordering = ["sort_order", "-created_at", "id"]

    def get_queryset(self):
        qs = GalleryItem.objects.all()

        content_type = self.request.query_params.get("content_type")
        if content_type:
            qs = qs.filter(content_type=content_type)

        if self.request.user.is_staff:
            return qs.order_by("sort_order", "-created_at", "id")

        return qs.filter(is_active=True).order_by("sort_order", "-created_at", "id")