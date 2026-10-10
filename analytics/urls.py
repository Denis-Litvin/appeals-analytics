from django.urls import path

from . import views

app_name = "analytics"

urlpatterns = [
    path("stats/", views.stats_page, name="stats"),
    path("stats/problems/", views.problems, name="problems"),
    path("stats/compare/", views.compare, name="compare"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("assets/plotly-<str:version>.min.js", views.plotly_js, name="plotly_js"),
    path("reports/", views.reports, name="reports"),
    path("alerts/", views.alerts, name="alerts"),
    path("alerts/read/", views.alerts_read, name="alerts_read_all"),
    path("alerts/<int:pk>/read/", views.alerts_read, name="alerts_read"),
]
