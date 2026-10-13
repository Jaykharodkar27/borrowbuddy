from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.dateparse import parse_date

from borrowing.models import BorrowRequest, rating_summary
from .forms import ItemForm
from .models import Category, Item


def _date_or_none(value):
    try:
        return parse_date(value)
    except ValueError:
        return None


def item_list(request):
    items = Item.objects.filter(is_active=True).select_related("category", "owner")

    q = request.GET.get("q", "").strip()
    category = request.GET.get("category", "")
    start_raw = request.GET.get("start", "")
    end_raw = request.GET.get("end", "")

    if q:
        items = items.filter(Q(title__icontains=q) | Q(description__icontains=q))
    if category.isdigit():
        items = items.filter(category_id=category)

    start, end = _date_or_none(start_raw), _date_or_none(end_raw)
    if start and end and start <= end:
        busy = BorrowRequest.objects.filter(
            status__in=BorrowRequest.BLOCKING_STATUSES,
            start_date__lte=end,
            end_date__gte=start,
        ).values("item_id")
        items = items.exclude(pk__in=busy)

    context = {
        "items": items,
        "categories": Category.objects.all(),
        "q": q,
        "selected_category": category,
        "start": start_raw,
        "end": end_raw,
    }
    return render(request, "items/item_list.html", context)


def item_detail(request, pk):
    item = get_object_or_404(Item, pk=pk, is_active=True)
    return render(
        request,
        "items/item_detail.html",
        {"item": item, "owner_rating": rating_summary(item.owner)},
    )


@login_required
def item_create(request):
    if request.method == "POST":
        form = ItemForm(request.POST, request.FILES)
        if form.is_valid():
            item = form.save(commit=False)
            item.owner = request.user
            item.save()
            return redirect("item_detail", pk=item.pk)
    else:
        form = ItemForm()
    return render(request, "items/item_form.html", {"form": form})