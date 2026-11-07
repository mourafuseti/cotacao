from django.urls import path

from . import views


app_name = "quotes"

urlpatterns = [
    path("painel/", views.dashboard, name="dashboard"),
    path("catalogo/", views.catalog, name="catalog"),
    path("catalogo/importar/", views.catalog_import, name="catalog_import"),
    path("cotacoes/", views.quote_list, name="quote_list"),
    path("cotacoes/nova/", views.quote_create, name="quote_create"),
    path("cotacoes/<int:pk>/", views.quote_detail, name="quote_detail"),
    path("cotacoes/<int:pk>/encerrar/", views.quote_close, name="quote_close"),
    path("cotacoes/<int:pk>/selecionar/", views.quote_award, name="quote_award"),
    path("cotacoes/<int:pk>/cancelar/", views.quote_cancel, name="quote_cancel"),
    path("cotacoes/<int:pk>/exportar.csv", views.quote_export, name="quote_export"),
    path("cotacoes/<int:pk>/proposta/", views.offer_create, name="offer_create"),
]
