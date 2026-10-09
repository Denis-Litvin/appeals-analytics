from django.urls import path

from . import views

app_name = "appeals"

urlpatterns = [
    path("", views.appeal_list, name="list"),
]
