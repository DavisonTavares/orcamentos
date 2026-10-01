from django.db import models
from django.utils import timezone
from accounts.models import Empresa, Usuario
from orcamentos.models import Cliente, Orcamento


class HistoricoMensagem(models.Model):
    """Armazena o histórico de mensagens trocadas entre o sistema e o cliente via WhatsApp."""

    DIRECAO_CHOICES = [
        ("enviada", "Enviada pelo sistema"),
        ("recebida", "Recebida do cliente"),
    ]

    TIPO_CHOICES = [
        ("texto", "Texto"),
        ("imagem", "Imagem"),
        ("documento", "Documento"),
        ("botao", "Botão"),
        ("audio", "Áudio"),
        ("outro", "Outro"),
    ]

    phone_number = models.CharField("Número do cliente", max_length=20)
    nome_cliente = models.CharField("Nome do cliente", max_length=100, blank=True, null=True)
    mensagem = models.TextField("Conteúdo da mensagem")
    direcao = models.CharField("Direção", max_length=10, choices=DIRECAO_CHOICES)
    tipo = models.CharField("Tipo de mensagem", max_length=20, choices=TIPO_CHOICES, default="texto")
    origem = models.CharField("Origem do fluxo", max_length=50, blank=True, null=True)  # ex: "menu inicial", "pré-orçamento"
    data_envio = models.DateTimeField("Data/Hora", default=timezone.now)

    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name="mensagens",
        null=True,
        blank=True
    )

    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mensagens"
    )

    orcamento = models.ForeignKey(
        Orcamento,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mensagens"
    )

    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mensagens_enviadas"
    )

    anexo = models.FileField("Anexo", upload_to="mensagens/anexos/", blank=True, null=True)

    def __str__(self):
        prefixo = "➡️" if self.direcao == "enviada" else "⬅️"
        return f"{prefixo} {self.phone_number} - {self.mensagem[:50]}"

    class Meta:
        verbose_name = "Histórico de Mensagem"
        verbose_name_plural = "Histórico de Mensagens"
        ordering = ["-data_envio"]
