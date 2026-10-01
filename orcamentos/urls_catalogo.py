from django.urls import path
from . import views

# Rotas públicas (sem login) do catálogo online enviado aos clientes
app_name = 'catalogo'

urlpatterns = [
    path('<str:token>/', views.catalogo_publico, name='publico'),
    path('<str:token>/foto/<int:item_id>/', views.catalogo_foto, name='foto'),
    path('<str:token>/logo/', views.catalogo_logo, name='logo'),
]
