from django.urls import path
from . import views

# Rotas públicas (sem login) do catálogo online enviado aos clientes
app_name = 'catalogo'

urlpatterns = [
    # Painel do dono do cupom (link privado): /catalogo/cupom/<token>/
    path('cupom/<str:token>/', views.painel_cupom, name='painel_cupom'),
    path('<str:token>/', views.catalogo_publico, name='publico'),
    path('<str:token>/foto/<int:item_id>/', views.catalogo_foto, name='foto'),
    path('<str:token>/logo/', views.catalogo_logo, name='logo'),
    path('<str:token>/liberar/', views.catalogo_liberar, name='liberar'),
    path('<str:token>/interesse/', views.catalogo_interesse, name='interesse'),
    path('<str:token>/cupom/', views.catalogo_cupom, name='cupom'),
    path('<str:token>/pedido/', views.catalogo_pedido, name='pedido'),
    path('<str:token>/pedido/<str:codigo>/', views.catalogo_pedido_enviado, name='pedido_enviado'),
]
