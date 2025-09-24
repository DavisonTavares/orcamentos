from django.urls import path
from . import views

app_name = 'orcamentos'

urlpatterns = [
    path('', views.lista_orcamentos, name='lista_orcamentos'),
    path('novo/', views.novo_orcamento, name='novo_orcamento'),
    path('<int:orcamento_id>/', views.detalhes_orcamento, name='detalhes_orcamento'),
    path('<int:orcamento_id>/editar/', views.editar_orcamento, name='editar_orcamento'),
    path('<int:orcamento_id>/excluir/', views.excluir_orcamento, name='excluir_orcamento'),
    path('<int:orcamento_id>/baixar-pdf/', views.baixar_pdf, name='baixar_pdf'),
    path('<int:orcamento_id>/alterar-status/', views.alterar_status, name='alterar_status'),
    path('clientes/novo/', views.novo_cliente, name='adicionar_cliente'),
    path('clientes/', views.lista_clientes, name='lista_clientes'),
    path('clientes/<int:cliente_id>/', views.cliente_detalhes, name='cliente_detalhes'),
    path('clientes/<int:cliente_id>/excluir/', views.excluir_cliente, name='excluir_cliente'),
    path('agendamentos/', views.agendamentos, name='agendamentos'),
    path('agendamentos/<int:orcamento_id>/concluir/', views.concluir_agendamento, name='concluir_agendamento'),
    path('agendamentos/<int:orcamento_id>/reabrir/', views.reabrir_agendamento, name='reabrir_agendamento'),
    path('itens/novo/', views.novo_item, name='adicionar_item'),
    path('itens/', views.lista_itens, name='lista_itens'),
    path('itens/editar/<int:item_id>/', views.editar_item, name='editar_item'),
    path('itens/excluir/<int:item_id>/', views.excluir_item, name='excluir_item'),
]