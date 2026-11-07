from django.contrib.auth import views as auth_views
from django.urls import path

from .views import CNPJLoginView, CompanyRegistrationView, home


app_name = "accounts"

urlpatterns = [
    path("", home, name="home"),
    path("entrar/", CNPJLoginView.as_view(), name="login"),
    path("cadastro/", CompanyRegistrationView.as_view(), name="register"),
    path(
        "sair/",
        auth_views.LogoutView.as_view(),
        name="logout",
    ),
]
