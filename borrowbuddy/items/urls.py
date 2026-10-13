from django.urls import path
from . import views

urlpatterns = [
    path("", views.item_list, name="item_list"),
    path("add/", views.item_create, name="item_create"),
    path("<int:pk>/", views.item_detail, name="item_detail"),
]