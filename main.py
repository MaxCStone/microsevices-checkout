import os
import requests
from flask import Flask, jsonify, request

app = Flask(__name__)
cart_service_url = os.environ.get(
    "CART_SERVICE_URL",
    "https://cart-service-539115724269.us-central1.run.app",
).rstrip("/")

    

@app.route("/checkout/<user_id>", methods=["GET", "POST"])
def checkout(user_id):
    if not cart_service_url:
        return jsonify({"error": "CART_SERVICE_URL is not configured"}), 500

    url = f"{cart_service_url}/cart/{user_id}"

    try:
        response = requests.request(
            method=request.method,
            url=url,
            json=request.get_json(silent=True) if request.method == "POST" else None,
            timeout=5,
        )
        response.raise_for_status()
        cart_response = response.json()
        if not isinstance(cart_response, dict):
            return jsonify({"error": "Cart service returned an invalid cart"}), 502

        cart = cart_response.get("cart") or []
        if not isinstance(cart, list):
            return jsonify({"error": "Cart service returned an invalid cart"}), 502

        try:
            total = round(sum(float(item["price_usd"]) for item in cart), 2)
        except (KeyError, TypeError, ValueError):
            return jsonify({
                "error": "Cart service returned an invalid price_usd field",
            }), 502

        return jsonify({
            **cart_response,
            "total": total,
        })
    except requests.RequestException as error:
        return jsonify({
            "error": "Cart service request failed",
            "details": str(error),
        }), 502
    except ValueError:
        return jsonify({"error": "Cart service returned invalid JSON"}), 502
    

if __name__ == "__main__":
    app.run(
        debug=True,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8080")),
    )