import pytest

from cart.models import Cart, CartItem
from cart.serializers import CartItemSerializer, MergeCartSerializer

# Endpoints below use transaction.atomic()+select_for_update() (AddCartItemAPIView,
# UpdateCartItemAPIView, MergeCartAPIView) which SQLite's backend does not support
# (django.db.NotSupportedError). The test bodies are written and ready to run
# against Postgres; they're skipped here because the suite runs on SQLite
# (see pytest.ini / config/settings_test.py).
SELECT_FOR_UPDATE_SKIP_REASON = (
    "uses select_for_update() to lock variant/cart-item rows; "
    "unsupported on the SQLite test database"
)


def _cart_item(cart, variant, quantity=1, is_gift=False):
    return CartItem.objects.create(
        cart=cart, variant=variant, quantity=quantity, is_gift=is_gift
    )


# ======================================================
# MyCartAPIView (GET /api/cart/my/)
# ======================================================
@pytest.mark.django_db
class TestMyCartAPIView:
    url = "/api/cart/my/"

    def test_requires_authentication(self, api_client):
        response = api_client.get(self.url)
        assert response.status_code == 401

    def test_creates_and_returns_empty_cart_for_new_user(self, auth_client, user):
        assert not Cart.objects.filter(user=user).exists()

        response = auth_client.get(self.url)

        assert response.status_code == 200
        assert response.data["items"] == []
        assert Cart.objects.filter(user=user).exists()

    def test_returns_existing_cart_with_items(self, auth_client, user, variant):
        cart = Cart.objects.create(user=user)
        _cart_item(cart, variant, quantity=2)

        response = auth_client.get(self.url)

        assert response.status_code == 200
        assert len(response.data["items"]) == 1
        item = response.data["items"][0]
        assert item["quantity"] == 2
        assert item["variant_id"] == variant.id
        assert item["in_stock"] is True

    def test_only_returns_own_cart(self, auth_client, user, other_user, variant):
        other_cart = Cart.objects.create(user=other_user)
        _cart_item(other_cart, variant, quantity=5)

        response = auth_client.get(self.url)

        assert response.status_code == 200
        assert response.data["items"] == []


# ======================================================
# AddCartItemAPIView (POST /api/cart/items/add/)
# ======================================================
@pytest.mark.skip(reason=SELECT_FOR_UPDATE_SKIP_REASON)
@pytest.mark.django_db
class TestAddCartItemAPIView:
    url = "/api/cart/items/add/"

    def test_requires_authentication(self, api_client, variant):
        response = api_client.post(self.url, {"variant_id": variant.id, "quantity": 1})
        assert response.status_code == 401

    def test_add_new_item_happy_path(self, auth_client, variant):
        response = auth_client.post(
            self.url, {"variant_id": variant.id, "quantity": 2}, format="json"
        )

        assert response.status_code == 201
        assert len(response.data["items"]) == 1
        assert response.data["items"][0]["quantity"] == 2

    def test_adding_existing_variant_increments_quantity(self, auth_client, user, variant):
        cart = Cart.objects.create(user=user)
        _cart_item(cart, variant, quantity=1)

        response = auth_client.post(
            self.url, {"variant_id": variant.id, "quantity": 2}, format="json"
        )

        assert response.status_code == 201
        assert response.data["items"][0]["quantity"] == 3

    def test_inactive_variant_rejected(self, auth_client, inactive_variant):
        response = auth_client.post(
            self.url, {"variant_id": inactive_variant.id, "quantity": 1}, format="json"
        )
        assert response.status_code == 400
        assert "variant_id" in response.data

    def test_insufficient_stock_rejected(self, auth_client, out_of_stock_variant):
        response = auth_client.post(
            self.url, {"variant_id": out_of_stock_variant.id, "quantity": 1}, format="json"
        )
        assert response.status_code == 400
        assert "quantity" in response.data

    def test_exceeding_stock_on_increment_rejected(self, auth_client, user, variant):
        cart = Cart.objects.create(user=user)
        _cart_item(cart, variant, quantity=9)  # variant has stock_qty=10

        response = auth_client.post(
            self.url, {"variant_id": variant.id, "quantity": 5}, format="json"
        )
        assert response.status_code == 400

    def test_nonexistent_variant_id_is_invalid(self, auth_client):
        response = auth_client.post(
            self.url, {"variant_id": 999999, "quantity": 1}, format="json"
        )
        assert response.status_code == 400

    def test_missing_variant_id_is_invalid(self, auth_client):
        response = auth_client.post(self.url, {"quantity": 1}, format="json")
        assert response.status_code == 400
        assert "variant_id" in response.data

    def test_quantity_below_one_is_invalid(self, auth_client, variant):
        response = auth_client.post(
            self.url, {"variant_id": variant.id, "quantity": 0}, format="json"
        )
        assert response.status_code == 400

    def test_missing_quantity_defaults_to_one(self, auth_client, variant):
        response = auth_client.post(
            self.url, {"variant_id": variant.id}, format="json"
        )
        assert response.status_code == 201
        assert response.data["items"][0]["quantity"] == 1


# ======================================================
# UpdateCartItemAPIView (PATCH /api/cart/items/<item_id>/)
# ======================================================
@pytest.mark.skip(reason=SELECT_FOR_UPDATE_SKIP_REASON)
@pytest.mark.django_db
class TestUpdateCartItemAPIView:
    def url(self, item_id):
        return f"/api/cart/items/{item_id}/"

    def test_requires_authentication(self, api_client, user, variant):
        cart = Cart.objects.create(user=user)
        item = _cart_item(cart, variant)
        response = api_client.patch(self.url(item.id), {"quantity": 2}, format="json")
        assert response.status_code == 401

    def test_update_quantity_happy_path(self, auth_client, user, variant):
        cart = Cart.objects.create(user=user)
        item = _cart_item(cart, variant, quantity=1)

        response = auth_client.patch(self.url(item.id), {"quantity": 4}, format="json")

        assert response.status_code == 200
        assert response.data["items"][0]["quantity"] == 4

    def test_quantity_zero_deletes_item(self, auth_client, user, variant):
        cart = Cart.objects.create(user=user)
        item = _cart_item(cart, variant, quantity=1)

        response = auth_client.patch(self.url(item.id), {"quantity": 0}, format="json")

        assert response.status_code == 200
        assert response.data["items"] == []
        assert not CartItem.objects.filter(id=item.id).exists()

    def test_insufficient_stock_rejected(self, auth_client, user, variant):
        cart = Cart.objects.create(user=user)
        item = _cart_item(cart, variant, quantity=1)

        response = auth_client.patch(self.url(item.id), {"quantity": 999}, format="json")

        assert response.status_code == 400

    def test_item_not_found_returns_404(self, auth_client):
        response = auth_client.patch(self.url(999999), {"quantity": 2}, format="json")
        assert response.status_code == 404

    def test_cannot_update_other_users_item(self, auth_client, other_user, variant):
        other_cart = Cart.objects.create(user=other_user)
        item = _cart_item(other_cart, variant, quantity=1)

        response = auth_client.patch(self.url(item.id), {"quantity": 2}, format="json")

        assert response.status_code == 404

    def test_non_numeric_quantity_is_invalid(self, auth_client, user, variant):
        cart = Cart.objects.create(user=user)
        item = _cart_item(cart, variant, quantity=1)

        response = auth_client.patch(self.url(item.id), {"quantity": "abc"}, format="json")

        assert response.status_code == 400


# ======================================================
# RemoveCartItemAPIView (DELETE /api/cart/items/<item_id>/delete/)
# ======================================================
@pytest.mark.django_db
class TestRemoveCartItemAPIView:
    def url(self, item_id):
        return f"/api/cart/items/{item_id}/delete/"

    def test_requires_authentication(self, api_client):
        response = api_client.delete(self.url(1))
        assert response.status_code == 401

    def test_removes_existing_item(self, auth_client, user, variant):
        cart = Cart.objects.create(user=user)
        item = _cart_item(cart, variant)

        response = auth_client.delete(self.url(item.id))

        assert response.status_code == 200
        assert response.data["items"] == []
        assert not CartItem.objects.filter(id=item.id).exists()

    def test_removing_nonexistent_item_is_a_no_op_200(self, auth_client):
        response = auth_client.delete(self.url(999999))
        assert response.status_code == 200

    def test_cannot_remove_other_users_item(self, auth_client, other_user, variant):
        other_cart = Cart.objects.create(user=other_user)
        item = _cart_item(other_cart, variant)

        response = auth_client.delete(self.url(item.id))

        assert response.status_code == 200
        assert CartItem.objects.filter(id=item.id).exists()


# ======================================================
# ClearCartAPIView (DELETE /api/cart/clear/)
# ======================================================
@pytest.mark.django_db
class TestClearCartAPIView:
    url = "/api/cart/clear/"

    def test_requires_authentication(self, api_client):
        response = api_client.delete(self.url)
        assert response.status_code == 401

    def test_clears_all_items(self, auth_client, user, variant, out_of_stock_variant):
        cart = Cart.objects.create(user=user)
        _cart_item(cart, variant)
        _cart_item(cart, out_of_stock_variant)

        response = auth_client.delete(self.url)

        assert response.status_code == 200
        assert response.data["items"] == []
        assert CartItem.objects.filter(cart=cart).count() == 0

    def test_clearing_already_empty_cart_is_a_no_op_200(self, auth_client):
        response = auth_client.delete(self.url)
        assert response.status_code == 200
        assert response.data["items"] == []


# ======================================================
# MergeCartAPIView (POST /api/cart/merge/)
# ======================================================
@pytest.mark.skip(reason=SELECT_FOR_UPDATE_SKIP_REASON)
@pytest.mark.django_db
class TestMergeCartAPIView:
    url = "/api/cart/merge/"

    def test_requires_authentication(self, api_client, variant):
        response = api_client.post(
            self.url, {"items": [{"variant_id": variant.id, "quantity": 1}]}, format="json"
        )
        assert response.status_code == 401

    def test_merge_into_empty_cart(self, auth_client, variant):
        response = auth_client.post(
            self.url, {"items": [{"variant_id": variant.id, "quantity": 3}]}, format="json"
        )

        assert response.status_code == 200
        assert response.data["items"][0]["quantity"] == 3

    def test_merge_sums_with_existing_cart_item(self, auth_client, user, variant):
        cart = Cart.objects.create(user=user)
        _cart_item(cart, variant, quantity=2)

        response = auth_client.post(
            self.url, {"items": [{"variant_id": variant.id, "quantity": 3}]}, format="json"
        )

        assert response.status_code == 200
        assert response.data["items"][0]["quantity"] == 5

    def test_duplicate_variant_ids_in_payload_are_combined(self, auth_client, variant):
        response = auth_client.post(
            self.url,
            {
                "items": [
                    {"variant_id": variant.id, "quantity": 2},
                    {"variant_id": variant.id, "quantity": 1},
                ]
            },
            format="json",
        )

        assert response.status_code == 200
        assert response.data["items"][0]["quantity"] == 3

    def test_insufficient_stock_rejected(self, auth_client, variant):
        response = auth_client.post(
            self.url, {"items": [{"variant_id": variant.id, "quantity": 999}]}, format="json"
        )
        assert response.status_code == 400

    def test_inactive_variant_rejected(self, auth_client, inactive_variant):
        response = auth_client.post(
            self.url,
            {"items": [{"variant_id": inactive_variant.id, "quantity": 1}]},
            format="json",
        )
        assert response.status_code == 400

    def test_nonexistent_variant_id_rejected(self, auth_client):
        response = auth_client.post(
            self.url, {"items": [{"variant_id": 999999, "quantity": 1}]}, format="json"
        )
        assert response.status_code == 400

    def test_empty_items_list_is_invalid(self, auth_client):
        response = auth_client.post(self.url, {"items": []}, format="json")
        assert response.status_code == 400

    def test_missing_items_key_is_invalid(self, auth_client):
        response = auth_client.post(self.url, {}, format="json")
        assert response.status_code == 400


# ======================================================
# CartItemSerializer (unit tests, no locking involved)
# ======================================================
@pytest.mark.django_db
class TestCartItemSerializer:
    def test_quantity_below_one_is_invalid(self, variant):
        serializer = CartItemSerializer(data={"variant_id": variant.id, "quantity": 0})
        assert not serializer.is_valid()
        assert "quantity" in serializer.errors

    def test_valid_data_passes(self, variant):
        serializer = CartItemSerializer(data={"variant_id": variant.id, "quantity": 2})
        assert serializer.is_valid(), serializer.errors

    def test_serializes_in_stock_true_for_active_stocked_variant(self, user, variant):
        cart = Cart.objects.create(user=user)
        item = _cart_item(cart, variant, quantity=1)

        data = CartItemSerializer(item).data

        assert data["in_stock"] is True
        assert data["price"] == "24.00"
        assert data["size"] == "Medium"

    def test_serializes_in_stock_false_for_out_of_stock_variant(
        self, user, out_of_stock_variant
    ):
        cart = Cart.objects.create(user=user)
        item = _cart_item(cart, out_of_stock_variant, quantity=1)

        data = CartItemSerializer(item).data

        assert data["in_stock"] is False


# ======================================================
# MergeCartSerializer (unit tests)
# ======================================================
class TestMergeCartSerializer:
    def test_empty_items_is_invalid(self):
        serializer = MergeCartSerializer(data={"items": []})
        assert not serializer.is_valid()
        assert "items" in serializer.errors

    def test_negative_variant_id_is_invalid(self):
        serializer = MergeCartSerializer(
            data={"items": [{"variant_id": -1, "quantity": 1}]}
        )
        assert not serializer.is_valid()

    def test_quantity_over_max_is_invalid(self):
        serializer = MergeCartSerializer(
            data={"items": [{"variant_id": 1, "quantity": 1000}]}
        )
        assert not serializer.is_valid()

    def test_valid_items_pass(self):
        serializer = MergeCartSerializer(
            data={"items": [{"variant_id": 1, "quantity": 2, "is_gift": True}]}
        )
        assert serializer.is_valid(), serializer.errors
