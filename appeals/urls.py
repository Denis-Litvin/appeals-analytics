from django.urls import path

from . import views

app_name = "appeals"

urlpatterns = [
    path("", views.appeal_list, name="list"),
    path("new/", views.appeal_create, name="create"),
    path("export/", views.appeal_export, name="export"),
    path("<int:pk>/", views.appeal_detail, name="detail"),
    path("<int:pk>/edit/", views.appeal_edit, name="edit"),
    path("<int:pk>/auto-category/", views.appeal_auto_category, name="auto_category"),
]
