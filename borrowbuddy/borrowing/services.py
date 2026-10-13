from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from items.models import Item
from .models import BorrowRequest, Payment, Review
from .payments import create_order, refund_payment, split_amount, verify_payment

S = BorrowRequest.Status
P = BorrowRequest.PaymentStatus


def _lock(request_id):
    """Lock the item row first, then the request row, always in this order.
    Concurrent actions on the same item then queue up instead of racing."""
    item_id = BorrowRequest.objects.values_list("item_id", flat=True).get(pk=request_id)
    Item.objects.select_for_update().get(pk=item_id)
    return (
        BorrowRequest.objects.select_for_update()
        .select_related("item")
        .get(pk=request_id)
    )


@transaction.atomic
def approve_request(request_id, user):
    req = _lock(request_id)
    if req.item.owner_id != user.id:
        raise PermissionDenied
    if req.status != S.REQUESTED:
        raise ValidationError("Only pending requests can be approved.")
    if req.end_date < timezone.localdate():
        raise ValidationError("These dates have already passed.")
    if BorrowRequest.has_conflict(req.item, req.start_date, req.end_date, exclude_pk=req.pk):
        raise ValidationError("Another approved booking overlaps these dates.")
    req.status = S.APPROVED
    req.save(update_fields=["status"])
    return req


def _transition(request_id, user, *, actor, allowed_from, new_status, stamp=None):
    req = _lock(request_id)
    allowed_user = req.item.owner_id if actor == "owner" else req.borrower_id
    if allowed_user != user.id:
        raise PermissionDenied
    if req.status not in allowed_from:
        raise ValidationError(
            f"A {req.get_status_display().lower()} request can't be changed this way."
        )
    req.status = new_status
    fields = ["status"]
    if stamp:
        setattr(req, stamp, timezone.now())
        fields.append(stamp)
    req.save(update_fields=fields)
    return req


@transaction.atomic
def decline_request(request_id, user):
    return _transition(request_id, user, actor="owner",
                       allowed_from=[S.REQUESTED], new_status=S.DECLINED)


@transaction.atomic
def cancel_request(request_id, user):
    req = _lock(request_id)
    if req.borrower_id != user.id:
        raise PermissionDenied
    if req.status not in (S.REQUESTED, S.APPROVED):
        raise ValidationError(
            f"A {req.get_status_display().lower()} request can't be cancelled."
        )

    if req.payment_status == P.PAID:
        payment = req.payments.filter(status=Payment.Status.PAID).first()
        try:
            refund_id = refund_payment(payment.razorpay_payment_id, payment.amount)
        except Exception:
            # Raising rolls back everything, so the request stays as it was.
            raise ValidationError("The refund could not be processed. Please try again.")
        payment.refund_id = refund_id
        payment.status = Payment.Status.REFUNDED
        payment.save(update_fields=["status", "refund_id"])
        req.payment_status = P.REFUNDED

    req.status = S.CANCELLED
    req.save(update_fields=["status", "payment_status"])
    return req


@transaction.atomic
def mark_collected(request_id, user):
    req = _lock(request_id)
    if req.item.owner_id != user.id:
        raise PermissionDenied
    if req.status != S.APPROVED:
        raise ValidationError(
            f"A {req.get_status_display().lower()} request can't be changed this way."
        )
    if req.payment_status == P.UNPAID:
        raise ValidationError("The borrower has not paid yet.")
    req.status = S.COLLECTED
    req.collected_at = timezone.now()
    req.save(update_fields=["status", "collected_at"])
    return req


@transaction.atomic
def mark_returned(request_id, user):
    return _transition(request_id, user, actor="owner", allowed_from=[S.COLLECTED],
                       new_status=S.RETURNED, stamp="returned_at")


def get_or_create_order(request_id, user):
    """Create (or reuse) a gateway order for an approved, unpaid request."""
    req = BorrowRequest.objects.select_related("item").get(pk=request_id)
    if req.borrower_id != user.id:
        raise PermissionDenied
    if req.status != S.APPROVED or req.payment_status != P.UNPAID:
        raise ValidationError("This request doesn't need a payment right now.")

    payment = req.payments.filter(status=Payment.Status.CREATED).first()
    if payment is None:
        order_id = create_order(req.total_price, f"request-{req.pk}")
        payment = Payment.objects.create(
            request=req, razorpay_order_id=order_id, amount=req.total_price
        )
    return req, payment


@transaction.atomic
def confirm_payment(request_id, user, order_id, payment_id, signature):
    req = _lock(request_id)
    if req.borrower_id != user.id:
        raise PermissionDenied
    if req.payment_status == P.PAID:
        return req  # already confirmed, nothing to do
    if req.status != S.APPROVED or req.payment_status != P.UNPAID:
        raise ValidationError("This request can't be paid right now.")

    try:
        payment = Payment.objects.select_for_update().get(
            request=req, razorpay_order_id=order_id
        )
    except Payment.DoesNotExist:
        raise ValidationError("Unknown payment order.")

    try:
        verify_payment(order_id, payment_id, signature)
    except ValueError:
        raise ValidationError("The payment could not be verified.")

    fee, lender_amount = split_amount(payment.amount)
    payment.razorpay_payment_id = payment_id
    payment.platform_fee = fee
    payment.lender_amount = lender_amount
    payment.status = Payment.Status.PAID
    payment.paid_at = timezone.now()
    payment.save()

    req.payment_status = P.PAID
    req.save(update_fields=["payment_status"])
    return req


@transaction.atomic
def submit_review(request_id, user, rating, comment=""):
    req = (
        BorrowRequest.objects.select_for_update()
        .select_related("item", "item__owner", "borrower")
        .get(pk=request_id)
    )
    if user.id == req.borrower_id:
        reviewee = req.item.owner
    elif user.id == req.item.owner_id:
        reviewee = req.borrower
    else:
        raise PermissionDenied
    if req.status != S.RETURNED:
        raise ValidationError("You can review only after the item is returned.")
    if Review.objects.filter(request=req, reviewer=user).exists():
        raise ValidationError("You have already reviewed this exchange.")
    return Review.objects.create(
        request=req, reviewer=user, reviewee=reviewee, rating=rating, comment=comment
    )