from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render
from django.views.generic import FormView

from .forms import CNPJAuthenticationForm, CompanyRegistrationForm


class CNPJLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = CNPJAuthenticationForm


class CompanyRegistrationView(FormView):
    template_name = "accounts/register.html"
    form_class = CompanyRegistrationForm

    def form_valid(self, form):
        user = form.save()
        login(self.request, user)
        messages.success(self.request, "Sua empresa foi cadastrada com sucesso.")
        return redirect("quotes:dashboard")


def home(request):
    if request.user.is_authenticated:
        return redirect("quotes:dashboard")
    return render(request, "home.html")
