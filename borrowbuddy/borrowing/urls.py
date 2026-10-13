from django.urls import path
from . import views

urlpatterns = [
    path("request/<int:item_pk>/", views.request_create, name="request_create"),
    path("my/", views.my_requests, name="my_requests"),
    path("request/<int:pk>/<slug:action>/", views.request_action, name="request_action"),
    path("review/<int:pk>/", views.review_create, name="review_create"),
    path("earnings/", views.earnings, name="earnings"),
    path("pay/<int:pk>/", views.pay, name="pay"),
    path("pay/<int:pk>/verify/", views.pay_verify, name="pay_verify"),
]