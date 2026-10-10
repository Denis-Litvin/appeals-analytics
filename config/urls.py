from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_not_required
from django.templatetags.static import static
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="appeals:list"), name="home"),
    # Браузер и админка запрашивают /favicon.ico сами, без ссылки в шаблоне.
    path("favicon.ico", login_not_required(RedirectView.as_view(url=static("favicon.svg"), permanent=True))),
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("admin/", admin.site.urls),
    path("appeals/", include("appeals.urls")),
    path("api/", include("api.urls")),
    path("", include("analytics.urls")),
]
