# relatorios/urls.py
from django.urls import path
from . import views

app_name = 'relatorios'

urlpatterns = [
    path('dashboard/', views.dashboard_relatorios, name='dashboard'),
    #path('relatorios-mensais/', views.relatorios_mensais, name='relatorios_mensais'),
    #path('relatorios-clientes/', views.relatorios_clientes, name='relatorios_clientes'),
]