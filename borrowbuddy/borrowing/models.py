from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Avg, Count
from django.utils import timezone

from items.models import Item


class BorrowRequest(models.Model):
    class Status(models.TextChoices):
        REQUESTED = "REQUESTED", "Requested"
        APPROVED = "APPROVED", "Approved"
        COLLECTED = "COLLECTED", "Collected"
        RETURNED = "RETURNED", "Returned"
        DECLINED = "DECLINED", "Declined"
        CANCELLED = "CANCELLED", "Cancelled"

    class PaymentStatus(models.TextChoices):
        NOT_REQUIRED = "NOT_REQUIRED", "No payment needed"
        UNPAID = "UNPAID", "Unpaid"
        PAID = "PAID", "Paid"
        REFUNDED = "REFUNDED", "Refunded"

    # Only these statuses block other people from booking the same dates.
    BLOCKING_STATUSES = [Status.APPROVED, Status.COLLECTED]

    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="borrow_requests")
    borrower = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="borrow_requests"
    )
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.REQUESTED)
    message = models.TextField(blank=True)
    total_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    payment_status = models.CharField(
        max_length=12, choices=PaymentStatus.choices, default=PaymentStatus.NOT_REQUIRED
    )
    collected_at = models.DateTimeField(null=True, blank=True)
    returned_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_date__gte=models.F("start_date")),
                name="end_not_before_start",
            )
        ]

    def __str__(self):
        return f"{self.item} · {self.borrower} · {self.start_date} to {self.end_date}"

    @property
    def is_overdue(self):
        return self.status == self.Status.COLLECTED and self.end_date < timezone.localdate()

    @property
    def days(self):
        return (self.end_date - self.start_date).days + 1

    @classmethod
    def has_conflict(cls, item, start_date, end_date, exclude_pk=None):
        """True if an approved/collected booking overlaps these dates."""
        qs = cls.objects.filter(
            item=item,
            status__in=cls.BLOCKING_STATUSES,
            start_date__lte=end_date,
            end_date__gte=start_date,
        )
        if exclude_pk:
            qs = qs.exclude(pk=exclude_pk)
        return qs.exists()


class Payment(models.Model):
    class Status(models.TextChoices):
        CREATED = "CREATED", "Created"
        PAID = "PAID", "Paid"
        REFUNDED = "REFUNDED", "Refunded"

    request = models.ForeignKey(BorrowRequest, on_delete=models.CASCADE, related_name="payments")
    # These hold the gateway's order and payment IDs. The names are kept generic enough
    # that a real gateway such as Razorpay can be plugged in later without a migration.
    razorpay_order_id = models.CharField(max_length=64, unique=True)
    razorpay_payment_id = models.CharField(max_length=64, blank=True)
    refund_id = models.CharField(max_length=64, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    platform_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    lender_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.CREATED)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.razorpay_order_id} · ₹{self.amount} · {self.status}"


class Review(models.Model):
    request = models.ForeignKey(BorrowRequest, on_delete=models.CASCADE, related_name="reviews")
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews_given"
    )
    reviewee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews_received"
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["request", "reviewer"], name="one_review_per_person_per_request"
            ),
            models.CheckConstraint(
                condition=models.Q(rating__gte=1) & models.Q(rating__lte=5),
                name="rating_between_1_and_5",
            ),
        ]

    def __str__(self):
        return f"{self.reviewer} → {self.reviewee}: {self.rating}★"


def rating_summary(user):
    """Average rating and number of reviews a user has received."""
    return Review.objects.filter(reviewee=user).aggregate(avg=Avg("rating"), count=Count("id"))