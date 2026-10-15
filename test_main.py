from unittest.mock import Mock, call, patch

import requests

import main


CART_URL = "https://cart-service-539115724269.us-central1.run.app"
SHIPPING_URL = "https://shipping-service-539115724269.us-central1.run.app"
PAYMENT_URL = "https://payment-service-539115724269.us-central1.run.app"


def response_with_json(payload):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = payload
    return response


def test_get_checkout_returns_cart_total_and_shipping_cost():
    cart_response = response_with_json({
        "user_id": "cart1",
        "cart": [
            {"product_id": "p1", "price_usd": 10.25},
            {"product_id": "p2", "price_usd": 4.75},
        ],
    })
    shipping_response = response_with_json({
        "order_id": "cart1",
        "item_count": 2,
        "shipping_estimate": 16.99,
    })

    with patch.object(
        main.requests,
        "get",
        side_effect=[cart_response, shipping_response],
    ) as mock_get:
        response = main.app.test_client().get("/checkout/cart1")

    assert response.status_code == 200
    assert response.get_json() == {
        "user_id": "cart1",
        "cart": [
            {"product_id": "p1", "price_usd": 10.25},
            {"product_id": "p2", "price_usd": 4.75},
        ],
        "shipping_estimate": 16.99,
        "total": 31.99,
    }
    assert mock_get.call_args_list == [
        call(f"{CART_URL}/cart/cart1", timeout=5),
        call(f"{SHIPPING_URL}/shipping/cart1", timeout=5),
    ]


def test_get_checkout_preserves_cart_service_item_format():
    cart_items = [
        {
            "categories": ["electronics", "audio"],
            "description": "Over-ear headphones",
            "name": "Wired Headphones",
            "price": 4999.99,
            "product_id": "102",
        },
        {
            "categories": ["electronics", "audio"],
            "description": "Over-ear headphones",
            "name": "Wired Headphones",
            "price": 4999.99,
            "product_id": "102",
        },
        {
            "categories": ["electronics", "audio"],
            "description": (
                "Over-ear Bluetooth headphones with a charging case."
            ),
            "name": "Wireless Headphones",
            "price": 49.99,
            "product_id": "101",
        },
        {
            "categories": ["electronics", "audio"],
            "description": (
                "Over-ear Bluetooth headphones with a charging case."
            ),
            "name": "Wireless Headphones",
            "price": 49.99,
            "product_id": "101",
        },
        {
            "categories": ["electronics", "audio"],
            "description": (
                "Over-ear Bluetooth headphones with a charging case."
            ),
            "name": "Wireless Headphones",
            "price": 49.99,
            "product_id": "101",
        },
        {
            "categories": ["electronics", "audio"],
            "description": "Over-ear headphones",
            "name": "Wired Headphones",
            "price": 4999.99,
            "product_id": "102",
        },
    ]
    cart_response = response_with_json({
        "cart": cart_items,
        "user_id": "123",
    })
    shipping_response = response_with_json({"shipping_estimate": 10})

    with patch.object(
        main.requests,
        "get",
        side_effect=[cart_response, shipping_response],
    ):
        response = main.app.test_client().get("/checkout/123")

    assert response.status_code == 200
    assert response.get_json()["cart"] == cart_items
    assert response.get_json()["total"] == 15159.94


def test_get_checkout_uses_price_when_price_usd_is_missing():
    cart_response = response_with_json({
        "user_id": "cart1",
        "cart": [
            {"price": 10.25},
            {"price": 100, "price_usd": 4.75},
        ],
    })
    shipping_response = response_with_json({
        "shipping_estimate": 16.99,
    })

    with patch.object(
        main.requests,
        "get",
        side_effect=[cart_response, shipping_response],
    ):
        response = main.app.test_client().get("/checkout/cart1")

    assert response.status_code == 200
    assert response.get_json()["total"] == 31.99


def test_get_checkout_uses_items_from_cart_service():
    cart_response = response_with_json({
        "user_id": "cart1",
        "items": [{"product_id": "p1", "price_usd": 10.25}],
    })
    shipping_response = response_with_json({"shipping_estimate": 5.5})

    with patch.object(
        main.requests,
        "get",
        side_effect=[cart_response, shipping_response],
    ):
        response = main.app.test_client().get("/checkout/cart1")

    assert response.status_code == 200
    assert response.get_json()["items"] == [
        {"product_id": "p1", "price_usd": 10.25},
    ]
    assert response.get_json()["total"] == 15.75


def test_get_checkout_rejects_null_cart_items():
    cart_response = response_with_json({
        "user_id": "cart1",
        "items": None,
    })

    with patch.object(main.requests, "get", return_value=cart_response) as mock_get:
        response = main.app.test_client().get("/checkout/cart1")

    assert response.status_code == 502
    assert response.get_json() == {
        "error": "Cart service returned an invalid cart",
    }
    mock_get.assert_called_once_with(f"{CART_URL}/cart/cart1", timeout=5)


def test_post_checkout_sends_shipping_address_before_getting_estimate():
    address = {
        "name": "ROSCOE",
        "street": "1234 MSOE Street",
        "city": "CITY",
        "state": "STATE",
        "zip": 12345,
        "country": "Merica",
    }
    cart_response = response_with_json({
        "user_id": "cart1",
        "cart": [{"price_usd": 20}],
    })
    create_shipping_response = response_with_json({
        "order_id": "cart1",
        "tracking_number": "699830377747",
    })
    shipping_response = response_with_json({"shipping_estimate": 5.5})
    payment_response = response_with_json({
        "amount": 25.5,
        "card_last4": "1234",
        "status": "Transaction approved",
        "transaction_id": "transaction-1",
    })
    card_info = {
        "card_number": "1234567890121234",
        "expiration_date": "01/28",
        "svn": "679",
    }

    with (
        patch.object(
            main.requests,
            "get",
            side_effect=[cart_response, shipping_response],
        ) as mock_get,
        patch.object(
            main.requests,
            "post",
            side_effect=[create_shipping_response, payment_response],
        ) as mock_post,
    ):
        response = main.app.test_client().post(
            "/checkout/cart1",
            json={"shipping_address": address, **card_info},
        )

    assert response.status_code == 200
    assert response.get_json()["total"] == 25.5
    assert response.get_json()["payment"] == payment_response.json.return_value
    assert mock_post.call_args_list == [
        call(
            f"{SHIPPING_URL}/shipping/cart1",
            json=address,
            timeout=5,
        ),
        call(
            f"{PAYMENT_URL}/charges",
            json={"amount": 25.5, **card_info},
            timeout=5,
        ),
    ]
    assert mock_get.call_count == 2


def test_post_checkout_requires_shipping_address():
    with patch.object(
        main.requests,
        "get",
        return_value=response_with_json({
            "user_id": "cart1",
            "cart": [],
        }),
    ):
        response = main.app.test_client().post("/checkout/cart1", json={})

    assert response.status_code == 400
    assert response.get_json() == {
        "error": "shipping_address must be an object",
    }


def test_post_checkout_requires_credit_card_fields():
    with patch.object(
        main.requests,
        "get",
        return_value=response_with_json({
            "user_id": "cart1",
            "cart": [],
        }),
    ):
        response = main.app.test_client().post(
            "/checkout/cart1",
            json={"shipping_address": {"street": "123 Main St"}},
        )

    assert response.status_code == 400
    assert response.get_json() == {
        "error": (
            "card_number, expiration_date, and svn must be "
            "non-empty strings"
        ),
    }


def test_checkout_rejects_invalid_cart_price():
    cart_response = response_with_json({
        "user_id": "cart1",
        "cart": [{"price_usd": "not-a-number"}],
    })

    with patch.object(main.requests, "get", return_value=cart_response):
        response = main.app.test_client().get("/checkout/cart1")

    assert response.status_code == 502
    assert response.get_json() == {
        "error": "Cart service returned an invalid price or price_usd field",
    }


def test_checkout_returns_bad_gateway_when_cart_service_fails():
    with patch.object(
        main.requests,
        "get",
        side_effect=requests.Timeout("cart service timed out"),
    ):
        response = main.app.test_client().get("/checkout/cart1")

    assert response.status_code == 502
    assert response.get_json()["error"] == "Cart service request failed"


def test_checkout_returns_bad_gateway_when_shipping_estimate_is_invalid():
    cart_response = response_with_json({
        "user_id": "cart1",
        "cart": [{"price_usd": 10}],
    })
    shipping_response = response_with_json({
        "shipping_estimate": "unknown",
    })

    with patch.object(
        main.requests,
        "get",
        side_effect=[cart_response, shipping_response],
    ):
        response = main.app.test_client().get("/checkout/cart1")

    assert response.status_code == 502
    assert response.get_json() == {
        "error": "Shipping service returned an invalid shipping_estimate",
    }
