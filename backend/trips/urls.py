from django.urls import path
from . import views

urlpatterns = [
    path("health", views.health_check),
    path("plan-trip", views.plan_trip),
    path("autocomplete", views.autocomplete),
]
