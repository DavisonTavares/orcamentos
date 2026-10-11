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


TIPOS_DESCONTO_CUPOM = [
    ('percentual', '% de desconto'),
    ('valor', 'Valor fixo (R$)'),
]


def desconto_do_cupom(base, tipo, valor):
    """
    Desconto em R$ que o cupom dá sobre `base` (o valor depois dos descontos
    dos itens e do desconto geral, antes do valor adicional). Nunca passa da base.
    """
    zero = Decimal('0')
    if not tipo or not valor:
        return zero
    base = Decimal(str(base))
    valor = Decimal(str(valor))
    desconto = base * valor / Decimal('100') if tipo == 'percentual' else valor
    return max(zero, min(desconto, base))


def detalhar_total(itens, desconto_geral, valor_adicional, cupom_tipo='', cupom_valor=0):
    """
    Partes do total do orçamento: subtotal (com desconto dos itens), desconto
    geral, desconto do cupom e o total final (arredondado em reais inteiros).
    itens: iterável de (valor, quantidade, desconto_do_item_em_%).
    """
    zero = Decimal('0')
    cem = Decimal('100')
    subtotal = sum(
        (((valor or zero) * quantidade) * (cem - (desconto or zero)) / cem
         for valor, quantidade, desconto in itens),
        zero,
    )
    valor_desconto_geral = subtotal * (desconto_geral or zero) / cem
    base = subtotal - valor_desconto_geral
    valor_cupom = desconto_do_cupom(base, cupom_tipo, cupom_valor)
    return {
        'subtotal': subtotal,
        'desconto_geral': valor_desconto_geral,
        'desconto_cupom': valor_cupom,
        'total': arredondar_total(base - valor_cupom + (valor_adicional or zero)),
    }


def calcular_total(itens, desconto_geral, valor_adicional, cupom_tipo='', cupom_valor=0):
    """
    Fórmula única do total do orçamento, usada pelo Orcamento.total e pelo
    cálculo em lote da lista de orçamentos (para os dois nunca divergirem).
    itens: iterável de (valor, quantidade, desconto_do_item_em_%).
    """
    return detalhar_total(itens, desconto_geral, valor_adicional, cupom_tipo, cupom_valor)['total']


def normalizar_codigo_cupom(codigo):
    """'  joao 10 ' -> 'JOAO10' (só letras e números, maiúsculas)."""
    sem_acento = unicodedata.normalize('NFKD', codigo or '').encode('ascii', 'ignore').decode()
    return ''.join(c for c in sem_acento.upper() if c.isalnum())[:30]


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


class Cupom(models.Model):
    """
    Cupom de indicação: cada funcionário (dono) divulga o seu código; o
    cliente ganha desconto e o dono ganha uma % do valor do evento, que só
    conta depois que o evento é concluído.
    """
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='cupons')
    codigo = models.CharField(max_length=30)
    dono_nome = models.CharField('Dono do cupom', max_length=100)
    dono_telefone = models.CharField('WhatsApp do dono', max_length=20, blank=True)
    tipo_desconto = models.CharField(max_length=12, choices=TIPOS_DESCONTO_CUPOM, default='percentual')
    valor_desconto = models.DecimalField(max_digits=10, decimal_places=2)  # % ou R$, conforme o tipo
    comissao_percentual = models.DecimalField('Comissão do dono (%)', max_digits=5, decimal_places=2, default=Decimal('5'))
    validade_ate = models.DateField('Válido até', null=True, blank=True)
    limite_usos = models.PositiveIntegerField('Limite de usos', null=True, blank=True)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    # Código do link privado em que o dono acompanha usos e comissões (sem login)
    token_painel = models.CharField(max_length=32, unique=True, default=gerar_token_catalogo)

    @property
    def descricao_desconto(self):
        if self.tipo_desconto == 'percentual':
            return f"{self.valor_desconto.normalize():f}% de desconto"
        return f"R$ {self.valor_desconto:.2f} de desconto".replace('.', ',')

    def usos(self):
        """Orçamentos (não cancelados) que usam o cupom."""
        return self.orcamentos.exclude(status='cancelado').count()

    def motivo_indisponivel(self, ignorar_orcamento=None):
        """'' se o cupom pode ser usado agora; senão, o motivo (para mostrar ao cliente)."""
        if not self.ativo:
            return 'Este cupom não está mais ativo.'
        if self.validade_ate and timezone.localdate() > self.validade_ate:
            return 'Este cupom está vencido.'
        if self.limite_usos:
            usos = self.orcamentos.exclude(status='cancelado')
            if ignorar_orcamento is not None:
                usos = usos.exclude(pk=ignorar_orcamento.pk)
            if usos.count() >= self.limite_usos:
                return 'Este cupom já atingiu o limite de usos.'
        return ''

    def __str__(self):
        return f"{self.codigo} ({self.dono_nome})"

    class Meta:
        verbose_name = "Cupom"
        verbose_name_plural = "Cupons"
        ordering = ['dono_nome', 'codigo']
        constraints = [models.UniqueConstraint(fields=['empresa', 'codigo'], name='cupom_codigo_unico_por_empresa')]


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
    # Cupom de indicação — as regras ficam copiadas aqui no momento em que é aplicado,
    # para mudanças no cupom não alterarem orçamentos já feitos
    cupom = models.ForeignKey(Cupom, on_delete=models.SET_NULL, null=True, blank=True, related_name='orcamentos')
    cupom_codigo = models.CharField(max_length=30, blank=True, default='')
    cupom_tipo = models.CharField(max_length=12, blank=True, default='')
    cupom_valor = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cupom_comissao = models.DecimalField(max_digits=5, decimal_places=2, default=0)  # % do total para o dono
    comissao_paga_em = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Orçamento #{self.id} - {self.cliente.nome}"

    def aplicar_cupom(self, cupom):
        """Copia as regras atuais do cupom para o orçamento (não salva)."""
        self.cupom = cupom
        self.cupom_codigo = cupom.codigo
        self.cupom_tipo = cupom.tipo_desconto
        self.cupom_valor = cupom.valor_desconto
        self.cupom_comissao = cupom.comissao_percentual

    def remover_cupom(self):
        self.cupom = None
        self.cupom_codigo = self.cupom_tipo = ''
        self.cupom_valor = self.cupom_comissao = Decimal('0')
        self.comissao_paga_em = None

    def detalhar_total(self):
        return detalhar_total(
            ((item.valor, item.quantidade, item.desconto) for item in self.itens.all()),
            self.desconto_geral, self.valor_adicional, self.cupom_tipo, self.cupom_valor,
        )

    @property
    def desconto_cupom(self):
        """Desconto em R$ do cupom neste orçamento."""
        return self.detalhar_total()['desconto_cupom'] if self.cupom_tipo else Decimal('0')

    @property
    def valor_comissao(self):
        """Comissão do dono do cupom: % do total do evento."""
        if not self.cupom_codigo or not self.cupom_comissao:
            return Decimal('0')
        return (self.total * self.cupom_comissao / Decimal('100')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

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
            self.cupom_tipo,
            self.cupom_valor,
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
    # Cupom informado pelo cliente no catálogo (regras copiadas no momento do pedido)
    cupom = models.ForeignKey(Cupom, on_delete=models.SET_NULL, null=True, blank=True, related_name='pre_orcamentos')
    cupom_codigo = models.CharField(max_length=30, blank=True, default='')
    cupom_tipo = models.CharField(max_length=12, blank=True, default='')
    cupom_valor = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cupom_comissao = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    @property
    def vencido(self):
        return self.status == 'novo' and timezone.now() > self.validade_ate

    @property
    def total(self):
        """Total com os descontos dos itens (valor no PIX à vista)."""
        return calcular_total(((i.valor_unitario, i.quantidade, i.desconto) for i in self.itens.all()), 0, 0,
                              self.cupom_tipo, self.cupom_valor)

    @property
    def total_sem_desconto(self):
        return calcular_total(((i.valor_unitario, i.quantidade, 0) for i in self.itens.all()), 0, 0,
                              self.cupom_tipo, self.cupom_valor)

    @property
    def desconto_cupom(self):
        """Desconto do cupom em R$ (sobre o valor cheio, sem o desconto do PIX)."""
        return detalhar_total(((i.valor_unitario, i.quantidade, 0) for i in self.itens.all()), 0, 0,
                              self.cupom_tipo, self.cupom_valor)['desconto_cupom']

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


class LeadCatalogo(models.Model):
    """
    Interessado do catálogo online: para ver os valores, o cliente informa
    nome, WhatsApp, data e local da festa. Fica registrado mesmo que ele não
    envie o pedido (com o que chegou a colocar no carrinho), para a equipe
    poder chamar. Não vira cliente nem entra na agenda — só se fizer o pedido.
    """
    STATUS_CHOICES = [
        ('novo', 'Novo'),
        ('contatado', 'Contatado'),
        ('convertido', 'Fez pedido'),
        ('descartado', 'Descartado'),
    ]
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='leads_catalogo')
    link = models.ForeignKey(LinkCatalogo, on_delete=models.SET_NULL, null=True, blank=True, related_name='leads')
    tipo_evento = models.CharField(max_length=100)
    nome = models.CharField(max_length=100)
    telefone = models.CharField(max_length=20)
    data_evento = models.DateField()
    local = models.CharField(max_length=150)  # bairro / cidade da festa
    interesse = models.TextField(blank=True, default='')  # carrinho {item_id: quantidade} em JSON
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='novo')
    visitas = models.PositiveIntegerField(default=1)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    pre_orcamento = models.ForeignKey(PreOrcamento, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')

    def quantidades_interesse(self):
        """{item_id: quantidade} do último carrinho visto."""
        import json
        try:
            dados = json.loads(self.interesse or '{}')
            return {int(k): int(v) for k, v in dados.items()}
        except (ValueError, TypeError, AttributeError):
            return {}

    def __str__(self):
        return f"Interessado {self.nome} ({self.data_evento:%d/%m/%Y})"

    class Meta:
        verbose_name = "Interessado do catálogo"
        verbose_name_plural = "Interessados do catálogo"
        ordering = ['-atualizado_em']


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
