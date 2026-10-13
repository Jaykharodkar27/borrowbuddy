from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import BorrowRequest, Review


class BorrowRequestForm(forms.ModelForm):
    class Meta:
        model = BorrowRequest
        fields = ["start_date", "end_date", "message"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "message": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, item, borrower, **kwargs):
        super().__init__(*args, **kwargs)
        self.item = item
        self.borrower = borrower

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_date")
        end = cleaned.get("end_date")
        if not start or not end:
            return cleaned

        if self.borrower == self.item.owner:
            raise ValidationError("You can't borrow your own item.")
        if start < timezone.localdate():
            raise ValidationError("The start date can't be in the past.")
        if end < start:
            raise ValidationError("The end date must be on or after the start date.")

        days = (end - start).days + 1
        if days > self.item.max_days:
            raise ValidationError(
                f"This item can be borrowed for at most {self.item.max_days} days."
            )
        if BorrowRequest.has_conflict(self.item, start, end):
            raise ValidationError("Those dates are already booked. Please choose other dates.")
        if BorrowRequest.objects.filter(
            item=self.item,
            borrower=self.borrower,
            status=BorrowRequest.Status.REQUESTED,
            start_date__lte=end,
            end_date__gte=start,
        ).exists():
            raise ValidationError("You already have a pending request for these dates.")
        return cleaned


class ReviewForm(forms.ModelForm):
    rating = forms.TypedChoiceField(
        choices=[(i, f"{i} ★") for i in range(5, 0, -1)],
        coerce=int,
    )

    class Meta:
        model = Review
        fields = ["rating", "comment"]
        widgets = {"comment": forms.Textarea(attrs={"rows": 3})}
