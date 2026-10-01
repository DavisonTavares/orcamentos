from django.contrib import admin
from .models import HistoricoMensagem

@admin.register(HistoricoMensagem)
class HistoricoMensagemAdmin(admin.ModelAdmin):
    list_display = ("phone_number", "nome_cliente", "direcao", "tipo", "data_envio", "empresa")
    list_filter = ("direcao", "tipo", "empresa")
    search_fields = ("phone_number", "nome_cliente", "mensagem")
