from django import forms
from .models import Item


class ItemForm(forms.ModelForm):
    class Meta:
        model = Item
        fields = ["title", "category", "description", "condition", "max_days", "price_per_day", "image"]