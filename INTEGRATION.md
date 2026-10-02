# Подключение Shippo к kfursenko-candles-store

Копируешь папку `shipping/` в `backend/`, дальше по шагам.

---

## 1. Вес и габариты у вариантов

Без этого Shippo не вернёт ничего. В `candles/models.py`, в `CandleVariant`:

```python
from decimal import Decimal

class CandleVariant(models.Model):
    ...
    # Shipping. Вес готового изделия без коробки — тару добавляет
    # shipping.normalize.build_parcels из SHIPPO_BOXES.
    weight_oz = models.DecimalField(
        max_digits=7, decimal_places=2, default=Decimal("8.00"),
        help_text="Вес одной штуки в унциях, без упаковки",
    )
    length_in = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("3.00"))
    width_in = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("3.00"))
    height_in = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("4.00"))
```

`default` поставлен, чтобы миграция прошла на существующих строках. Но дефолты — это выдуманные числа: пройдись по каталогу и проставь настоящие, иначе будешь платить за недовес или получать отказы на приёмке.

```bash
python manage.py makemigrations candles shipping
python manage.py migrate
```

## 2. Телефон в заказе

В `orders/models.py`, в `Order`:

```python
shipping_phone = models.CharField(max_length=32, blank=True, default="")
```

И в `ShippingSerializer` (`orders/serializers.py`):

```python
phone = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
```

Плюс прокинуть в `build_order`: `shipping_phone=shipping.get("phone", "").strip()`.

Для домашних отправлений USPS переживёт и без телефона — сработает `SHIPPO_FALLBACK_PHONE`. Для международки и для UPS/FedEx он обязателен.

## 3. settings.py

В `INSTALLED_APPS` добавь `"shipping",`. В блок с throttle-скоупами:

```python
"shipping_rates": config("THROTTLE_SHIPPING_RATES", default="20/min"),
```

И новая секция в конец файла:

```python
# ------------------------------------------------------------
# Shippo
# ------------------------------------------------------------
from decimal import Decimal  # noqa: E402  (или подними наверх к остальным импортам)

SHIPPO_TOKEN = config("SHIPPO_TOKEN", default="").strip()
SHIPPO_API_BASE = config("SHIPPO_API_BASE", default="https://api.goshippo.com")
SHIPPO_API_VERSION = config("SHIPPO_API_VERSION", default="2018-02-08")
SHIPPO_TIMEOUT_SECONDS = config("SHIPPO_TIMEOUT_SECONDS", default=30, cast=int)
SHIPPO_LABEL_FILE_TYPE = config("SHIPPO_LABEL_FILE_TYPE", default="PDF")
SHIPPO_FALLBACK_PHONE = config("SHIPPO_FALLBACK_PHONE", default="")

# Флэт из orders/serializers.py переезжает сюда — он теперь фолбэк,
# а не основная цена.
SHIPPING_FALLBACK_RATE = Decimal(config("SHIPPING_FALLBACK_RATE", default="15.00"))

SHIPPO_ADDRESS_FROM = {
    "name": config("SHIP_FROM_NAME", default="KFursenko Candles"),
    "company": config("SHIP_FROM_COMPANY", default=""),
    "street1": config("SHIP_FROM_STREET1", default=""),
    "street2": config("SHIP_FROM_STREET2", default=""),
    "city": config("SHIP_FROM_CITY", default=""),
    "state": config("SHIP_FROM_STATE", default=""),
    "zip": config("SHIP_FROM_ZIP", default=""),
    "country": config("SHIP_FROM_COUNTRY", default="US"),
    "phone": config("SHIP_FROM_PHONE", default=""),
    "email": config("SHIP_FROM_EMAIL", default=DEFAULT_FROM_EMAIL),
}

# Коробки, в которые реально пакуешь. Размеры в дюймах, tare_oz — вес
# пустой коробки с наполнителем.
SHIPPO_BOXES = [
    {"name": "small", "length": 6, "width": 6, "height": 6, "tare_oz": 3},
    {"name": "medium", "length": 10, "width": 8, "height": 6, "tare_oz": 6},
    {"name": "large", "length": 14, "width": 12, "height": 10, "tare_oz": 11},
]
```

Склад один, поэтому адрес отправителя в конфиге, а не в БД. Появится второй — вынесешь в модель `Warehouse`, код в `services.quote_rates` трогать не придётся, только источник `address_from`.

## 4. .env

```
SHIPPO_TOKEN=shippo_test_xxxxxxxx
SHIP_FROM_NAME=KFursenko Candles
SHIP_FROM_STREET1=...
SHIP_FROM_CITY=...
SHIP_FROM_STATE=DC
SHIP_FROM_ZIP=...
SHIP_FROM_COUNTRY=US
SHIP_FROM_PHONE=+12025550100
SHIPPO_FALLBACK_PHONE=+12025550100
```

Проверь, что `.env` игнорируется — он у тебя лежит в корне `backend/`:

```bash
git check-ignore -v backend/.env
```

Если команда молчит, файл в индексе и токен уедет в репозиторий.

## 5. urls

В `config/urls.py`:

```python
path("api/shipping/", include("shipping.urls")),
```

## 6. build_order

Здесь самое существенное. Сейчас в `orders/serializers.py`:

```python
SHIPPING_FLAT_RATE = Decimal("15.00")
...
shipping_amount=SHIPPING_FLAT_RATE,
```

Меняем на реальный расчёт. `build_order` получает новый необязательный аргумент:

```python
from django.conf import settings
from shipping.normalize import payload_to_address
from shipping.services import resolve_shipping_cost


@transaction.atomic
def build_order(*, user, lines, shipping, shipping_rate_id=None):
    ...
    # после того, как variant_map собран, но до Order.objects.create
    quote_lines = [
        (variant_map[vid], int(payload["quantity"]))
        for vid, payload in merged.items()
    ]

    shipping_amount, rate = resolve_shipping_cost(
        address_to=payload_to_address(shipping),
        lines=quote_lines,
        rate_id=shipping_rate_id,
    )

    order = Order.objects.create(
        ...
        shipping_amount=shipping_amount,
        ...
    )

    if rate:
        from shipping.models import Shipment

        Shipment.objects.create(
            order=order,
            rate_id=rate["rate_id"],
            carrier=rate["carrier"],
            service_level=rate["service_level"],
            amount=rate["amount"],
            currency=rate["currency"].lower(),
        )
```

`resolve_shipping_cost` не бросает исключений на сетевых проблемах — если Shippo лежит, вернётся `SHIPPING_FALLBACK_RATE` и `rate=None`. Заказ оформится, покупатель заплатит, тариф подберётся уже при покупке этикетки. Ронять чекаут из-за чужого API нельзя.

В `OrderCreateSerializer` и `OrderFromCartSerializer` добавь поле:

```python
shipping_rate_id = serializers.CharField(required=False, allow_blank=True, default="")
```

и прокинь в `build_order(..., shipping_rate_id=validated_data.get("shipping_rate_id") or None)`.

## 7. Фикстура для тестов

`tests.py` ждёт `paid_order` в `conftest.py`:

```python
@pytest.fixture
def paid_order(db, django_user_model):
    user = django_user_model.objects.create_user(
        email="buyer@example.com", password="pw12345!"
    )
    return Order.objects.create(
        user=user,
        status=Order.Status.PAID,
        shipping_full_name="Jane Doe",
        shipping_line1="965 Mission St",
        shipping_city="San Francisco",
        shipping_state="CA",
        shipping_postal_code="94105",
        shipping_country="United States",
    )
```

Сигнатуру `create_user` подгони под свою `accounts.User`.

---

## Порядок вызовов на фронте

1. Покупатель вводит адрес → `POST /api/shipping/rates/` → список тарифов.
2. Выбирает тариф → `POST /api/orders/from-cart/` с `shipping_rate_id`.
3. `POST /api/orders/create-intent/` — интент уже на правильную сумму.
4. Оплата → вебхук Stripe переводит заказ в `paid`.
5. Стафф: `POST /api/shipping/orders/<id>/label/` → этикетка, трек, заказ уходит в `shipped`.

Шаг 3 обязан идти после шага 2. Сейчас `total_amount` фиксируется в `build_order`, и если тариф придёт позже — спишешь не ту сумму.

## Что не сделано осознанно

**Международка.** `payload_to_address` пропустит любую страну из `COUNTRIES`, но таможенная декларация (`customs_declarations`) не подключена — для отправки за пределы США её надо добавить. И отдельно: воск и ароматические масла у ряда перевозчиков идут как ограниченный груз, в декларации это надо указывать честно. Если продаёшь только по США — просто убери лишние страны из `COUNTRIES`, чтобы форма не пропускала то, что ты не повезёшь.

**Асинхронность.** Celery в проекте нет, поэтому покупка синхронная. Терпимо, пока её дёргает стафф руками. Если появится автопокупка на вебхуке Stripe — выноси в очередь, вебхук нельзя держать пять секунд.

**Трекинг.** Вебхуки Shippo (`track_updated`) не подключены. Пока статус доставки смотришь по `tracking_url` вручную.

**Хранение этикеток.** `label_url` живёт на стороне Shippo не вечно. Cloudinary у тебя уже подключён — если этикетки нужны в архиве, скачивай PDF и клади туда.

## Заодно, вне Shippo

В `orders/models.py` поля `discount_amount` и `discount_label` объявлены дважды подряд, вместе с комментарием на восьми пробелах отступа. Python это проглатывает — второе определение просто затирает первое в namespace класса, — но выглядит как след неудачного мержа. То же самое в `candles/models.py`: `priority`, `is_active` и `apply_globally` в `Offer` продублированы. Стоит убрать, пока никто не отредактировал не ту копию.
