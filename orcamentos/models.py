import secrets
import unicodedata
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from django.db import models
from django.utils import timezone
from accounts.models import Empresa, ImagemArmazenada, Usuario


# Folga exigida entre um evento e outro (montagem/desmontagem): ao confirmar,
# avisa se outro evento confirmado começa ou termina a menos disso
MARGEM_CONFLITO = timedelta(hours=1)


def tipo_conflito(intervalo_a, intervalo_b):
    """
    Regra única de conflito entre dois eventos (início, fim):
    'sobrepoe' se os horários se cruzam, 'margem' se ficam a menos de
    MARGEM_CONFLITO um do outro, ou None se não há conflito.
    """
    if not intervalo_a or not intervalo_b:
        return None
    (ini_a, fim_a), (ini_b, fim_b) = intervalo_a, intervalo_b
    if not (ini_b < fim_a + MARGEM_CONFLITO and fim_b > ini_a - MARGEM_CONFLITO):
        return None
    return 'sobrepoe' if (ini_b < fim_a and fim_b > ini_a) else 'margem'


def itens_alem_do_estoque(orcamento_a, orcamento_b):
    """
    Itens dos dois eventos que, somados, passam do estoque da empresa
    (ex.: "Pula Pula Médio (2 de 1)"). Itens com preço progressivo (balões
    etc.) são consumo, não entram. Usa os itens já carregados (prefetch).
    """
    qtd_a = {}
    for oi in orcamento_a.itens.all():
        qtd_a[oi.item_id] = qtd_a.get(oi.item_id, 0) + oi.quantidade
    faltando = []
    for oi in orcamento_b.itens.all():
        item = oi.item
        if oi.item_id not in qtd_a or item.progressivo:
            continue
        total = qtd_a[oi.item_id] + oi.quantidade
        if total > item.quantidade_estoque:
            faltando.append(f"{item.nome or item.descricao} ({total} de {item.quantidade_estoque})")
    return faltando


def assinatura_conflito(orcamento_a, intervalo_a, orcamento_b, intervalo_b):
    """
    Retrato dos dois eventos (horários + itens/quantidades) no momento em que
    o conflito foi verificado: se qualquer um mudar, a assinatura muda e o
    conflito volta a aparecer.
    """
    def retrato(o, intervalo):
        itens = ','.join(f"{oi.item_id}x{oi.quantidade}" for oi in sorted(o.itens.all(), key=lambda x: (x.item_id, x.quantidade)))
        return f"{o.pk}@{intervalo[0]:%Y%m%d%H%M}-{intervalo[1]:%Y%m%d%H%M}[{itens}]"
    pares = sorted([(orcamento_a.pk, retrato(orcamento_a, intervalo_a)), (orcamento_b.pk, retrato(orcamento_b, intervalo_b))])
    return '|'.join(r for _, r in pares)[:500]


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


# Acessórios que todo brinquedo inflável leva (entram automaticamente na
# lista de conferência dos itens marcados como "inflável")
KIT_INFLAVEL = ['Lona de proteção', 'Extensão elétrica', 'Motor soprador']


def _normalizar_texto(texto):
    sem_acento = unicodedata.normalize('NFKD', texto or '').encode('ascii', 'ignore').decode()
    return ' '.join(sem_acento.lower().split())


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
    # Foto do catálogo online, guardada no banco (funciona também no Vercel)
    foto = models.ForeignKey(ImagemArmazenada, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    exibir_catalogo = models.BooleanField(default=True)  # aparece no catálogo online enviado aos clientes
    inflavel = models.BooleanField(default=False)  # leva o KIT_INFLAVEL na lista de conferência
    # Quantas unidades a empresa tem: o conflito de "mesmo brinquedo" só é
    # apontado quando eventos no mesmo horário somam mais que isso
    quantidade_estoque = models.PositiveIntegerField(default=1)

    # Preço progressivo (ex.: kit de balões): o valor_unitario vale a partir de
    # prog_quantidade_minima e cai prog_reducao a cada prog_a_cada unidades,
    # sem passar de prog_preco_minimo. Todos vazios = preço fixo, como sempre.
    prog_quantidade_minima = models.PositiveIntegerField(null=True, blank=True)
    prog_a_cada = models.PositiveIntegerField(null=True, blank=True)
    prog_reducao = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    prog_preco_minimo = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    @property
    def progressivo(self):
        return bool(self.prog_quantidade_minima and self.prog_a_cada and self.prog_reducao and self.prog_preco_minimo is not None)

    def preco_unitario(self, quantidade=None):
        """
        Preço por unidade para a quantidade informada. Ex. (balões): mínimo 10,
        a cada 10 reduz R$ 0,50, mínimo R$ 5,50 -> 10-19: 8,50 · 20-29: 8,00 ·
        ... · 70+: 5,50. Sem regra progressiva, é o valor_unitario de sempre.
        """
        if not self.progressivo or not quantidade:
            return Decimal(self.valor_unitario)
        degraus = max(0, (int(quantidade) - self.prog_quantidade_minima) // self.prog_a_cada)
        return max(Decimal(self.prog_preco_minimo), Decimal(self.valor_unitario) - degraus * Decimal(self.prog_reducao))

    def faixas_progressivas(self):
        """[(de, até_ou_None, preço)] para mostrar a tabela de faixas."""
        if not self.progressivo:
            return []
        faixas, de = [], self.prog_quantidade_minima
        while True:
            preco = self.preco_unitario(de)
            if preco <= self.prog_preco_minimo or len(faixas) >= 50:
                faixas.append((de, None, Decimal(self.prog_preco_minimo)))
                return faixas
            faixas.append((de, de + self.prog_a_cada - 1, preco))
            de += self.prog_a_cada

    def regra_progressiva_json(self):
        """Mesma regra para o JavaScript (orçamento e catálogo calculam ao vivo)."""
        if not self.progressivo:
            return None
        return {
            'minimo': self.prog_quantidade_minima,
            'a_cada': self.prog_a_cada,
            'reducao': float(self.prog_reducao),
            'piso': float(self.prog_preco_minimo),
        }

    def itens_conferencia(self):
        """
        O que separar para este item na lista de conferência: o kit padrão dos
        infláveis (se for inflável) + o checklist próprio do item, sem repetir
        o que já estiver no kit (comparação sem acento/maiúsculas, então
        "EXTENSÂO ELÉTRICA" digitado à mão não duplica a "Extensão elétrica").
        """
        itens = list(KIT_INFLAVEL) if self.inflavel else []
        vistos = {_normalizar_texto(t) for t in itens}
        for chk in self.checklist_itens.all():
            if _normalizar_texto(chk.descricao) not in vistos:
                vistos.add(_normalizar_texto(chk.descricao))
                itens.append(chk.descricao)
        return itens

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
    
    def intervalo(self):
        """(início, fim) do evento como datetime, ou None se faltar data/hora."""
        if not self.data_evento or not self.hora_evento:
            return None
        hora = self.hora_evento
        if isinstance(hora, str):
            try:
                hora = datetime.strptime(hora[:5], '%H:%M').time()
            except ValueError:
                return None
        try:
            horas = int(self.periodo_evento)
        except (TypeError, ValueError):
            horas = 3
        inicio = datetime.combine(self.data_evento, hora)
        return inicio, inicio + timedelta(hours=horas)

    def conflitos_de_horario(self):
        """
        Eventos confirmados que batem com o horário deste, considerando
        MARGEM_CONFLITO antes e depois (montagem/desmontagem). Retorna uma
        lista de dicts com o orçamento, o horário e os itens que passam do
        estoque. Conflitos já marcados como verificados (e sem mudança desde
        então) ficam de fora.
        """
        meu = self.intervalo()
        if meu is None:
            return []
        eu = Orcamento.objects.prefetch_related('itens__item').get(pk=self.pk) if self.pk else self
        candidatos = (
            Orcamento.objects
            .filter(empresa_id=self.empresa_id, status='confirmado',
                    data_evento__range=[self.data_evento - timedelta(days=1), self.data_evento + timedelta(days=1)])
            .exclude(pk=self.pk)
            .select_related('cliente')
            .prefetch_related('itens__item')
        )
        verificados = ConflitoVerificado.assinaturas(self.empresa_id)
        conflitos = []
        for outro in candidatos:
            dele = outro.intervalo()
            tipo = tipo_conflito(meu, dele)
            if not tipo or assinatura_conflito(eu, meu, outro, dele) in verificados:
                continue
            conflitos.append({
                'orcamento': outro,
                'inicio': dele[0],
                'fim': dele[1],
                'sobrepoe': tipo == 'sobrepoe',  # horários se cruzam (não só a margem)
                'itens_em_comum': itens_alem_do_estoque(eu, outro),
            })
        return sorted(conflitos, key=lambda c: c['inicio'])

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

# Por quantos dias o pré-orçamento do catálogo garante os preços
VALIDADE_PRE_ORCAMENTO_DIAS = 3


class PreOrcamento(models.Model):
    """
    Pedido feito pelo cliente no catálogo online (carrinho + dados da festa).
    Fica separado dos orçamentos — não entra na agenda, relatórios nem na
    verificação de conflito — até a equipe conferir e gerar o orçamento de
    fato. Os preços ficam travados por VALIDADE_PRE_ORCAMENTO_DIAS dias.
    """
    STATUS_CHOICES = [
        ('novo', 'Novo'),
        ('convertido', 'Orçamento gerado'),
        ('descartado', 'Descartado'),
    ]
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='pre_orcamentos')
    link = models.ForeignKey(LinkCatalogo, on_delete=models.SET_NULL, null=True, blank=True, related_name='pre_orcamentos')
    codigo = models.CharField(max_length=32, unique=True, default=gerar_token_catalogo)  # URL da página de confirmação do cliente
    tipo_evento = models.CharField(max_length=100)
    cliente = models.ForeignKey(Cliente, on_delete=models.SET_NULL, null=True, blank=True, related_name='pre_orcamentos')
    nome = models.CharField(max_length=100)
    telefone = models.CharField(max_length=20)
    data_evento = models.DateField()
    hora_evento = models.TimeField()
    periodo_evento = models.CharField(max_length=1, default='3')
    endereco = models.TextField()
    observacoes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='novo')
    criado_em = models.DateTimeField(auto_now_add=True)
    validade_ate = models.DateTimeField()
    orcamento = models.ForeignKey(Orcamento, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')

    @property
    def vencido(self):
        return self.status == 'novo' and timezone.now() > self.validade_ate

    @property
    def total(self):
        """Total com os descontos dos itens (valor no PIX à vista)."""
        return calcular_total(((i.valor_unitario, i.quantidade, i.desconto) for i in self.itens.all()), 0, 0)

    @property
    def total_sem_desconto(self):
        return calcular_total(((i.valor_unitario, i.quantidade, 0) for i in self.itens.all()), 0, 0)

    def __str__(self):
        return f"Pré-orçamento #{self.pk} - {self.nome}"

    class Meta:
        verbose_name = "Pré-orçamento"
        verbose_name_plural = "Pré-orçamentos"
        ordering = ['-criado_em']


class PreOrcamentoItem(models.Model):
    pre_orcamento = models.ForeignKey(PreOrcamento, on_delete=models.CASCADE, related_name='itens')
    item = models.ForeignKey(Item, on_delete=models.SET_NULL, null=True, blank=True)
    nome = models.CharField(max_length=200)  # cópia, para o pedido continuar legível se o item mudar
    quantidade = models.PositiveIntegerField(default=1)
    valor_unitario = models.DecimalField(max_digits=10, decimal_places=2)  # preço do tipo de evento, travado no pedido
    desconto = models.DecimalField(max_digits=5, decimal_places=2, default=0)  # % de desconto do item (PIX à vista)

    def __str__(self):
        return f"{self.quantidade}x {self.nome}"


class ConflitoVerificado(models.Model):
    """
    Conflito de horário que a equipe analisou e marcou como ok (ex.: equipe
    extra contratada). Guarda a assinatura dos dois eventos (horários e
    itens): se algum mudar, a assinatura não bate mais e o conflito volta.
    """
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='conflitos_verificados')
    orcamento_a = models.ForeignKey(Orcamento, on_delete=models.CASCADE, related_name='+')
    orcamento_b = models.ForeignKey(Orcamento, on_delete=models.CASCADE, related_name='+')
    assinatura = models.CharField(max_length=500)
    observacao = models.CharField(max_length=200, blank=True)
    verificado_por = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    verificado_em = models.DateTimeField(auto_now=True)

    @classmethod
    def assinaturas(cls, empresa_id):
        return set(cls.objects.filter(empresa_id=empresa_id).values_list('assinatura', flat=True))

    def __str__(self):
        return f"Conflito #{self.orcamento_a_id} x #{self.orcamento_b_id} verificado"

    class Meta:
        verbose_name = "Conflito verificado"
        verbose_name_plural = "Conflitos verificados"
        unique_together = [('orcamento_a', 'orcamento_b')]
