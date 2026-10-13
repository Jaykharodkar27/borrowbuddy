from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class Category(models.Model):
    name = models.CharField(max_length=50, unique=True)

    class Meta:
        verbose_name_plural = "categories"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Item(models.Model):
    CONDITION_CHOICES = [
        ("new", "Like new"),
        ("good", "Good"),
        ("fair", "Fair"),
    ]

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="items"
    )
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="items"
    )
    title = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    condition = models.CharField(max_length=10, choices=CONDITION_CHOICES, default="good")
    max_days = models.PositiveIntegerField(default=7, help_text="Longest borrow period in days")
    price_per_day = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Rent per day in ₹ (0 means free)",
    )
    image = models.ImageField(upload_to="items/", blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title