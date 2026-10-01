from django.urls import path
from whatsapp import views

urlpatterns = [
    path("whatsapp/webhook/", views.whatsapp_webhook, name="whatsapp_webhook"),
    path("instagram/webhook/", views.instagram_webhook, name="instagram_webhook"),
    path("historico/", views.historico_mensagens, name="historico_mensagens"),
    path("get-numbers-names/", views.getNumberAndNameOfClients, name="get_numbers_names"),
    path("get-pdf-orcamento/", views.getPDFOrcamentoWhatsApp, name="get_pdf_orcamento"),
    path("chat/<str:phone_number>/", views.chat_cliente, name="chat_cliente"),
    path("listar-brinquedos/", views.getBrinquedosEValoresWhatsApp, name="listar_brinquedos"),
    path("salva-contato/", views.salvarNovoClienteWhatsApp, name="salva_contato"),
    path("enviar-atualizacao-eventos/", views.enviar_atualizacao_eventos, name="enviar_atualizacao_eventos"),
    path("cancelar-envio-eventos/", views.cancelar_envio_eventos, name="cancelar_envio_eventos"),
]
