from django.db import models
from django.utils import timezone
from accounts.models import Empresa, Usuario


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

    def __str__(self):
        return self.descricao

    class Meta:
        verbose_name = "Item"
        verbose_name_plural = "Itens"


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
        """Calcula o total do orçamento"""
        total = sum(item.valor * item.quantidade for item in self.itens.all())
        return total - (total * (self.desconto_geral or 0) / 100) + (self.valor_adicional or 0)
    
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