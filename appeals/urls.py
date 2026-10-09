from django.urls import path

from . import views

app_name = "appeals"

urlpatterns = [
    path("", views.appeal_list, name="list"),
    path("<int:pk>/", views.appeal_detail, name="detail"),
]
