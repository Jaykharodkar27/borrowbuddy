from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Sum
from django.http import Http404
from django.conf import settings
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from items.models import Item
from . import services
from .forms import BorrowRequestForm, ReviewForm
from .models import BorrowRequest, Payment, Review, rating_summary
from .payments import make_demo_payment


@login_required
def request_create(request, item_pk):
    item = get_object_or_404(Item, pk=item_pk, is_active=True)

    if request.method == "POST":
        form = BorrowRequestForm(request.POST, item=item, borrower=request.user)
        if form.is_valid():
            borrow = form.save(commit=False)
            borrow.item = item
            borrow.borrower = request.user
            borrow.total_price = item.price_per_day * borrow.days
            borrow.payment_status = (
                BorrowRequest.PaymentStatus.UNPAID
                if borrow.total_price > 0
                else BorrowRequest.PaymentStatus.NOT_REQUIRED
            )
            borrow.save()
            messages.success(request, "Request sent! The owner will review it.")
            return redirect("my_requests")
    else:
        form = BorrowRequestForm(item=item, borrower=request.user)

    booked = BorrowRequest.objects.filter(
        item=item,
        status__in=BorrowRequest.BLOCKING_STATUSES,
        end_date__gte=timezone.localdate(),
    ).order_by("start_date")

    return render(
        request,
        "borrowing/request_form.html",
        {"form": form, "item": item, "booked": booked},
    )


@login_required
def my_requests(request):
    made = BorrowRequest.objects.filter(borrower=request.user).select_related(
        "item", "item__owner"
    )
    received = BorrowRequest.objects.filter(item__owner=request.user).select_related(
        "item", "borrower"
    )
    reviewed_ids = set(
        Review.objects.filter(reviewer=request.user).values_list("request_id", flat=True)
    )
    return render(
        request,
        "borrowing/my_requests.html",
        {
            "made": made,
            "received": received,
            "reviewed_ids": reviewed_ids,
            "my_rating": rating_summary(request.user),
        },
    )


ACTIONS = {
    "approve": services.approve_request,
    "decline": services.decline_request,
    "cancel": services.cancel_request,
    "collect": services.mark_collected,
    "return": services.mark_returned,
}


@login_required
@require_POST
def request_action(request, pk, action):
    handler = ACTIONS.get(action)
    if handler is None:
        raise Http404
    try:
        req = handler(pk, request.user)
        messages.success(request, f"Request updated: {req.get_status_display()}.")
    except BorrowRequest.DoesNotExist:
        raise Http404
    except ValidationError as e:
        messages.error(request, " ".join(e.messages))
    return redirect("my_requests")


@login_required
def review_create(request, pk):
    br = get_object_or_404(
        BorrowRequest.objects.select_related("item", "item__owner", "borrower"), pk=pk
    )
    if request.user.id not in (br.borrower_id, br.item.owner_id):
        raise PermissionDenied
    if br.status != BorrowRequest.Status.RETURNED:
        messages.error(request, "You can review only after the item is returned.")
        return redirect("my_requests")
    if Review.objects.filter(request=br, reviewer=request.user).exists():
        messages.error(request, "You have already reviewed this exchange.")
        return redirect("my_requests")

    other = br.item.owner if request.user.id == br.borrower_id else br.borrower

    if request.method == "POST":
        form = ReviewForm(request.POST)
        if form.is_valid():
            try:
                services.submit_review(
                    pk, request.user, form.cleaned_data["rating"], form.cleaned_data["comment"]
                )
                messages.success(request, "Thanks for your review!")
            except ValidationError as e:
                messages.error(request, " ".join(e.messages))
            return redirect("my_requests")
    else:
        form = ReviewForm()

    return render(request, "borrowing/review_form.html", {"form": form, "br": br, "other": other})


@login_required
def earnings(request):
    paid = Payment.objects.filter(
        request__item__owner=request.user, status=Payment.Status.PAID
    ).select_related("request", "request__item", "request__borrower")
    completed = paid.filter(request__status=BorrowRequest.Status.RETURNED)
    in_progress = paid.exclude(request__status=BorrowRequest.Status.RETURNED)
    return render(
        request,
        "borrowing/earnings.html",
        {
            "completed": completed,
            "total_earned": completed.aggregate(t=Sum("lender_amount"))["t"] or 0,
            "on_hold": in_progress.aggregate(t=Sum("lender_amount"))["t"] or 0,
            "fee_percent": settings.PLATFORM_FEE_PERCENT,
        },
    )


@login_required
def pay(request, pk):
    try:
        req, payment = services.get_or_create_order(pk, request.user)
    except BorrowRequest.DoesNotExist:
        raise Http404
    except ValidationError as e:
        messages.error(request, " ".join(e.messages))
        return redirect("my_requests")

    payment_id, signature = make_demo_payment(payment.razorpay_order_id)
    return render(
        request,
        "borrowing/pay.html",
        {
            "req": req,
            "payment": payment,
            "demo_payment_id": payment_id,
            "demo_signature": signature,
        },
    )


@login_required
@require_POST
def pay_verify(request, pk):
    try:
        services.confirm_payment(
            pk,
            request.user,
            request.POST.get("order_id", ""),
            request.POST.get("payment_id", ""),
            request.POST.get("signature", ""),
        )
        messages.success(request, "Payment received. The lender can now hand over the item.")
    except BorrowRequest.DoesNotExist:
        raise Http404
    except ValidationError as e:
        messages.error(request, " ".join(e.messages))
    return redirect("my_requests")