import secrets
from decimal import Decimal, ROUND_HALF_UP
from django.db import models
from django.utils import timezone
from accounts.models import Empresa, Usuario


def arredondar_total(valor):
    """Arredonda o total do orçamento para reais inteiros (548,98 → 549; 548,40 → 548)."""
    return Decimal(str(valor)).quantize(Decimal('1'), rounding=ROUND_HALF_UP).quantize(Decimal('0.01'))


def calcular_total(itens, desconto_geral, valor_adicional):
    """
    Fórmula única do total do orçamento, usada pelo Orcamento.total e pelo
    cálculo em lote da lista de orçamentos (para os dois nunca divergirem).
    itens: iterável de (valor, quantidade, desconto_do_item_em_%).
    """
    zero = Decimal('0')
    cem = Decimal('100')
    subtotal = sum(
        ((valor or zero) * quantidade) * (cem - (desconto or zero)) / cem
        for valor, quantidade, desconto in itens
    )
    desconto_geral = desconto_geral or zero
    total = subtotal - (subtotal * desconto_geral / cem) + (valor_adicional or zero)
    return arredondar_total(total)


class Cliente(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='clientes')
    nome = models.CharField(max_length=100)
    telefone = models.CharField(max_length=20)
    data_cadastro = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.nome

    def total_orcamentos(self):
        return self.orcamentos.count()
    
    def orcamentos_confirmados(self):
        return self.orcamentos.filter(status='confirmado').count()
    
    def orcamentos_concluidos(self):
        return self.orcamentos.filter(status='concluido').count()
    
    def orcamentos_pendentes(self):
        return self.orcamentos.filter(status='pendente').count()
    
    def valor_total_orcamentos(self):
        total = 0
        for orcamento in self.orcamentos.all():
            if hasattr(orcamento, 'total'):
                total += orcamento.total
        return total

    class Meta:
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"


class Item(models.Model):
    CATEGORIA_CHOICES = [
        ('brinquedo', 'Brinquedo'),
        ('comida', 'Comida'),
        ('servico', 'Serviço'),
        ('outro', 'Outro'),
        ('buffet', 'Buffet'),
        ('decoracao', 'Decoração'),
        ('personalizado', 'Personalizado'),
        ('buffet_personalizado', 'Buffet - Personalizado'),
    ]
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='itens')
    descricao = models.CharField(max_length=200)
    valor_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    investimento = models.DecimalField(max_digits=10, decimal_places=2, default=0) # custo do item
    custo_fixo = models.DecimalField(max_digits=10, decimal_places=2, default=0) # custo fixo do item
    percentual_lucro = models.DecimalField(max_digits=5, decimal_places=2, default=0) # percentual de lucro
    desconto = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    categoria = models.CharField(max_length=20, choices=CATEGORIA_CHOICES, default='brinquedo')
    disponivel = models.BooleanField(default=True)
    nome = models.CharField(max_length=100, blank=True, null=True)
    imagem = models.ImageField(upload_to='itens/fotos/', blank=True, null=True)  # foto usada no catálogo online
    exibir_catalogo = models.BooleanField(default=True)  # aparece no catálogo online enviado aos clientes

    def __str__(self):
        return self.descricao

    class Meta:
        verbose_name = "Item"
        verbose_name_plural = "Itens"


TIPOS_EVENTO = [
    'Aniversário',
    'Casamento',
    'Corporativo',
    'Evento Público (com estimativa de público)',
    'Evento Público (sem estimativa de público)',
    'Evento Sem Monitoria',
    'Frente de Loja',
    'Outro',
]


def gerar_token_catalogo():
    return secrets.token_urlsafe(12)


class LinkCatalogo(models.Model):
    """
    Link secreto do catálogo online para um tipo de evento. O preço muda
    conforme o tipo, então cada tipo tem o seu link; o token é aleatório (não
    contém o nome do tipo), para o cliente não conseguir "adivinhar" o link de
    outro tipo e ver outros preços. Gerar um novo link desativa o anterior.
    """
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='links_catalogo')
    tipo_evento = models.CharField(max_length=100)
    token = models.CharField(max_length=32, unique=True, default=gerar_token_catalogo)
    ativo = models.BooleanField(default=True)
    acessos = models.PositiveIntegerField(default=0)
    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Catálogo {self.tipo_evento} ({'ativo' if self.ativo else 'desativado'})"

    class Meta:
        verbose_name = "Link do Catálogo"
        verbose_name_plural = "Links do Catálogo"


class ChecklistItem(models.Model):
    """
    Um componente/acessório que o item (brinquedo) precisa levar para o
    evento (ex.: extensão, estacas, soprador). Usado para montar a lista de
    conferência em PDF na hora de separar/carregar o material.
    """
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='checklist_itens')
    descricao = models.CharField(max_length=200)
    ordem = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.descricao} ({self.item.descricao})"

    class Meta:
        verbose_name = "Item do Checklist"
        verbose_name_plural = "Itens do Checklist"
        ordering = ['ordem', 'id']


class Orcamento(models.Model):
    STATUS_CHOICES = [
        ('pendente', 'Pendente'),
        ('confirmado', 'Confirmado'),
        ('cancelado', 'Cancelado'),
        ('concluido', 'Concluído'),
        ('reagendar', 'Reagendado'),
    ]
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='orcamentos')
    criado_por = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, related_name='orcamentos_criados')
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='orcamentos')
    data_criacao = models.DateTimeField(auto_now_add=True)
    data_evento = models.DateField(blank=True, null=True)
    hora_evento = models.TimeField(blank=False, default='16:00') # hora do evento
    periodo_evento = models.CharField(max_length=1, blank= False, default='3') # 1, 2, 3 horas
    desconto_geral = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    observacoes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pendente')
    pdf = models.FileField(upload_to='orcamentos/pdf/', blank=True, null=True)
    png = models.ImageField(upload_to='orcamentos/png/', blank=True, null=True)
    tipo_evento = models.CharField(max_length=100, blank=False, default='Aniversário') # tipo do evento
    valor_adicional = models.DecimalField(max_digits=10, decimal_places=2, default=0) # valor adicional
    endereco = models.TextField(blank=False)
    valor_pago = models.DecimalField(max_digits=10, decimal_places=2, default=0) # valor pago
    custo_operacional = models.DecimalField(max_digits=10, decimal_places=2, default=0) # custo operacional
    
    def __str__(self):
        return f"Orçamento #{self.id} - {self.cliente.nome}"
    
    @property
    def total(self):
        """Calcula o total do orçamento, aplicando o desconto de cada item
        (travado no OrcamentoItem no momento em que foi adicionado) e, por
        cima do subtotal já com desconto, o desconto geral do orçamento.

        Importante: o "or 0" de fallback usa Decimal('0') e não o int 0 —
        um Decimal zerado (ex.: Decimal('0.00')) é "falsy" em Python, então
        "campo_decimal or 0" viraria um int e misturaria Decimal com float
        na divisão por 100 mais abaixo, o que o Python não permite.

        O total final é sempre arredondado para reais inteiros (ex.: os
        descontos em % geram R$ 548,97804 → R$ 549,00)."""
        return calcular_total(
            ((item.valor, item.quantidade, item.desconto) for item in self.itens.all()),
            self.desconto_geral,
            self.valor_adicional,
        )
    
    @property
    def saldo(self):
        """Calcula o saldo devedor"""
        return self.total - (self.valor_pago or 0)
    
    @property
    def dias_para_evento(self):
        """Retorna quantos dias faltam para o evento"""
        if self.data_evento:
            hoje = timezone.now().date()
            return (self.data_evento - hoje).days
        return None
    
    @property
    def data_conclusao(self):
        """Data de conclusão do agendamento"""
        # Você precisa adicionar este campo ao modelo
        return getattr(self, '_data_conclusao', None)

    class Meta:
        verbose_name = "Orçamento"
        verbose_name_plural = "Orçamentos"


class OrcamentoItem(models.Model):
    orcamento = models.ForeignKey(Orcamento, on_delete=models.CASCADE, related_name='itens')
    item = models.ForeignKey(Item, on_delete=models.CASCADE)
    quantidade = models.IntegerField(default=1)
    valor = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    desconto = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)

    def __str__(self):
        return f"{self.quantidade}x {self.item.descricao} - {self.valor}"

    class Meta:
        verbose_name = "Item do Orçamento"
        verbose_name_plural = "Itens do Orçamento"