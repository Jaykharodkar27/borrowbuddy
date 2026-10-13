from django.contrib import admin
from .models import BorrowRequest, Payment, Review


@admin.register(BorrowRequest)
class BorrowRequestAdmin(admin.ModelAdmin):
    list_display = ("item", "borrower", "start_date", "end_date", "status", "payment_status")
    list_filter = ("status", "payment_status")


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("reviewer", "reviewee", "rating", "request", "created_at")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("razorpay_order_id", "request", "amount", "platform_fee", "lender_amount", "status")