import hashlib
import hmac
import uuid
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings


def split_amount(amount):
    """Return (platform_fee, lender_amount) for a payment amount."""
    amount = Decimal(amount)
    fee = (amount * Decimal(settings.PLATFORM_FEE_PERCENT) / 100).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return fee, amount - fee


def _signature(order_id, payment_id):
    """Sign an order/payment pair with the project's secret key, like a real gateway does."""
    message = f"{order_id}|{payment_id}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), message, hashlib.sha256).hexdigest()


def create_order(amount, receipt):
    """Create an order with the gateway and return its id."""
    return f"demo_order_{uuid.uuid4().hex[:14]}"


def make_demo_payment(order_id):
    """Simulate the customer paying: returns (payment_id, signature)."""
    payment_id = f"demo_pay_{uuid.uuid4().hex[:14]}"
    return payment_id, _signature(order_id, payment_id)


def verify_payment(order_id, payment_id, signature):
    """Raise ValueError if the payment signature is not valid."""
    if not hmac.compare_digest(_signature(order_id, payment_id), signature):
        raise ValueError("invalid signature")


def refund_payment(payment_id, amount):
    """Refund a payment in full and return the refund id."""
    return f"demo_refund_{uuid.uuid4().hex[:14]}"