from django.contrib.auth.decorators import login_not_required
from django.urls import path
from rest_framework.authtoken.views import obtain_auth_token

from . import views

app_name = "api"


def open_view(view):
    """API проверяет токен сам. Middleware входа на сайт отправил бы клиента API на страницу логина."""
    return login_not_required(view if not hasattr(view, "as_view") else view.as_view())


urlpatterns = [
    path("auth/token/", open_view(obtain_auth_token), name="token"),
    path("summary/", open_view(views.SummaryView), name="summary"),
    path("categories/", open_view(views.CategoriesView), name="categories"),
    path("reasons/top/", open_view(views.TopReasonsView), name="top_reasons"),
    path("problems/", open_view(views.ProblemsView), name="problems"),
    path("timeseries/", open_view(views.TimeseriesView), name="timeseries"),
    path("compare/", open_view(views.CompareView), name="compare"),
    path("alerts/", open_view(views.AlertListView), name="alerts"),
    path("appeals/", open_view(views.AppealListView), name="appeals"),
    path("appeals/<int:pk>/", open_view(views.AppealDetailView), name="appeal"),
]
