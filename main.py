import os
import requests
from google.cloud import logging
from flask import Flask, jsonify, request

app = Flask(__name__)
client = logging.Client()
log_name = "checkout-log"
logger = client.logger(log_name)
client.setup_logging()
cart_service_url = os.environ.get(
    "CART_SERVICE_URL",
    "https://cart-service-539115724269.us-central1.run.app",
).rstrip("/")
shipping_service_url = os.environ.get(
    "SHIPPING_SERVICE_URL",
    "https://shipping-service-539115724269.us-central1.run.app",
).rstrip("/")
payment_service_url = os.environ.get(
    "PAYMENT_SERVICE_URL",
    "https://payment-service-539115724269.us-central1.run.app",
).rstrip("/")

@app.route("/checkout/<user_id>", methods=["GET", "POST"])
def checkout(user_id):
    correlation_id = request.headers.get("correlation_id")
    log_string = f"user_id: {user_id} | Checkout | {request.method} | Correlation ID: {request.headers.get('correlation_id', 'N/A')}"
    if not cart_service_url or not shipping_service_url:
        log_string += " | ERROR: CART_SERVICE_URL and SHIPPING_SERVICE_URL must be configured"
        logger.log_text(log_string)
        return jsonify({
            "error": "CART_SERVICE_URL and SHIPPING_SERVICE_URL must be configured",
        }), 500

    if request.method == "POST" and not payment_service_url:
        log_string += " | ERROR: PAYMENT_SERVICE_URL must be configured"
        logger.log_text(log_string)
        return jsonify({
            "error": "PAYMENT_SERVICE_URL must be configured",
        }), 500

    try:
        cart_response = requests.get(
            f"{cart_service_url}/cart/{user_id}",
            headers=_correlation_headers(correlation_id),
            timeout=5,
        )
        cart_response.raise_for_status()
        cart_response = cart_response.json()
        if not isinstance(cart_response, dict):
            log_string += " | ERROR: Cart service returned an invalid cart"
            logger.log_text(log_string)
            return jsonify({"error": "Cart service returned an invalid cart"}), 502

        cart = cart_response.get(
            "cart",
            cart_response.get("items"),
        )
        if not isinstance(cart, list):
            log_string += " | ERROR: Cart service returned an invalid cart"
            logger.log_text(log_string)
            return jsonify({"error": "Cart service returned an invalid cart"}), 502

        try:
            cart_total = round(sum(
                float(item["price_usd"] if "price_usd" in item else item["price"])
                for item in cart
            ), 2)
        except (KeyError, TypeError, ValueError):
            log_string += " | ERROR: Cart service returned an invalid price or price_usd field"
            logger.log_text(log_string)
            return jsonify({
                "error": "Cart service returned an invalid price or price_usd field",
            }), 502

        if request.method == "POST":
            body = request.get_json(silent=True)
            shipping_address = body.get("shipping_address") if isinstance(body, dict) else None
            if not isinstance(shipping_address, dict):
                log_string += " | ERROR: shipping_address must be an object"
                logger.log_text(log_string)
                return jsonify({
                    "error": "shipping_address must be an object",
                }), 400

            card_fields = ("card_number", "expiration_date", "svn")
            if not all(
                isinstance(body.get(field), str) and body[field]
                for field in card_fields
            ):
                log_string += " | ERROR: card_number, expiration_date, and svn must be non-empty strings"
                logger.log_text(log_string)
                return jsonify({
                    "error": (
                        "card_number, expiration_date, and svn must be "
                        "non-empty strings"
                    ),
                }), 400

            shipping_response = requests.post(
                f"{shipping_service_url}/shipping/{user_id}",
                json=shipping_address,
                headers=_correlation_headers(correlation_id),
                timeout=5,
            )
            shipping_response.raise_for_status()

        shipping_response = requests.get(
            f"{shipping_service_url}/shipping/{user_id}",
            headers=_correlation_headers(correlation_id),
            timeout=5,
        )
        shipping_response.raise_for_status()
        shipping_data = shipping_response.json()
        if not isinstance(shipping_data, dict):
            log_string += " | ERROR: Shipping service returned an invalid response"
            logger.log_text(log_string)
            return jsonify({
                "error": "Shipping service returned an invalid response",
            }), 502

        try:
            shipping_total = round(float(shipping_data["shipping_estimate"]), 2)
        except (KeyError, TypeError, ValueError):
            log_string += " | ERROR: Shipping service returned an invalid shipping_estimate"
            logger.log_text(log_string)
            return jsonify({
                "error": "Shipping service returned an invalid shipping_estimate",
            }), 502

        checkout_data = {
            **cart_response,
            "shipping_estimate": shipping_total,
            "total": round(cart_total + shipping_total, 2),
        }
        if "items" in cart_response:
            checkout_data["items"] = cart

        if request.method == "POST":
            payment_body = {
                "amount": checkout_data["total"],
                "card_number": body["card_number"],
                "expiration_date": body["expiration_date"],
                "svn": body["svn"],
            }
            try:
                payment_response = requests.post(
                    f"{payment_service_url}/charges",
                    json=payment_body,
                    headers=_correlation_headers(correlation_id),
                    timeout=5,
                )
                payment_response.raise_for_status()
                payment_data = payment_response.json()
            except requests.RequestException as error:
                log_string += " | ERROR: Payment service request failed"
                logger.log_text(log_string)
                return jsonify({
                    "error": "Payment service request failed",
                    "details": str(error),
                }), 502
            except ValueError:
                log_string += " | ERROR: Payment service returned invalid JSON"
                logger.log_text(log_string)
                return jsonify({
                    "error": "Payment service returned invalid JSON",
                }), 502

            if not isinstance(payment_data, dict):
                log_string += " | ERROR: Payment service returned an invalid response"
                logger.log_text(log_string)
                return jsonify({
                    "error": "Payment service returned an invalid response",
                }), 502

            checkout_data["payment"] = payment_data
            log_string += " | INFO: Checkout data prepared successfully"
            logger.log_text(log_string)
        return jsonify(checkout_data)
    except requests.RequestException as error:
        log_string += " | ERROR: Cart service request failed"
        logger.log_text(log_string)
        return jsonify({
            "error": "Cart service request failed",
            "details": str(error),
        }), 502
    except ValueError:
        log_string += " | ERROR: Cart service returned invalid JSON"
        logger.log_text(log_string)
        return jsonify({"error": "Cart service returned invalid JSON"}), 502
    

if __name__ == "__main__":
    app.run(
        debug=True,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8080")),
    )