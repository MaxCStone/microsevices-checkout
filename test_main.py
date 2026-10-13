from unittest.mock import Mock, call, patch

import requests

import main


CART_URL = "https://cart-service-539115724269.us-central1.run.app"
SHIPPING_URL = "https://shipping-service-539115724269.us-central1.run.app"


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

    with (
        patch.object(
            main.requests,
            "get",
            side_effect=[cart_response, shipping_response],
        ) as mock_get,
        patch.object(
            main.requests,
            "post",
            return_value=create_shipping_response,
        ) as mock_post,
    ):
        response = main.app.test_client().post(
            "/checkout/cart1",
            json={"shipping_address": address},
        )

    assert response.status_code == 200
    assert response.get_json()["total"] == 25.5
    mock_post.assert_called_once_with(
        f"{SHIPPING_URL}/shipping/cart1",
        json=address,
        timeout=5,
    )
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


def test_checkout_rejects_invalid_cart_price():
    cart_response = response_with_json({
        "user_id": "cart1",
        "cart": [{"price_usd": "not-a-number"}],
    })

    with patch.object(main.requests, "get", return_value=cart_response):
        response = main.app.test_client().get("/checkout/cart1")

    assert response.status_code == 502
    assert response.get_json() == {
        "error": "Cart service returned an invalid price_usd field",
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
