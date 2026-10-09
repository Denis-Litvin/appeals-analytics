from django.urls import path

from . import views

app_name = "analytics"

urlpatterns = [
    path("stats/", views.stats, name="stats"),
    path("stats/problems/", views.problems, name="problems"),
    path("stats/compare/", views.compare, name="compare"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("reports/", views.reports, name="reports"),
    path("alerts/", views.alerts, name="alerts"),
]
