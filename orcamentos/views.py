from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, JsonResponse, FileResponse, Http404
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Count, Max, F
from django.utils import timezone
from django.conf import settings
from datetime import timedelta, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from django.utils.http import url_has_allowed_host_and_scheme
import os
import json
import mimetypes
import unicodedata

from .models import (
    Cliente, Item, Orcamento, OrcamentoItem, ChecklistItem, LinkCatalogo, TIPOS_EVENTO,
    arredondar_total, calcular_total,
)
from accounts.models import Empresa, Usuario
from .forms import OrcamentoForm, ClienteForm, ItemForm, OrcamentoSearchForm
from .utils import gerar_arquivos, gerar_catalogo, gerar_checklist_conferencia, gerar_recibo, gerar_resumo_festas
from whatsapp.views import (
    AVISO_NOTA_FISCAL, INTERVALO_ENVIO_EVENTOS, enviar_em_segundo_plano, eventos_em_aberto,
    formatar_reais, mensagem_pagamento_recebido, status_envio_eventos,
)

# Decorator personalizado para verificar se o usuário tem acesso à empresa
def acesso_empresa_required(view_func):
    def wrapper(request, *args, **kwargs):
        # Verifica se o usuário está autenticado e tem uma empresa
        if not request.user.is_authenticated or not hasattr(request.user, 'empresa'):
            messages.error(request, 'Acesso não autorizado.')
            return redirect('accounts:login')
        
        # Para views que recebem IDs de objetos, verifica se pertencem à empresa do usuário
        if 'cliente_id' in kwargs:
            cliente = get_object_or_404(Cliente, id=kwargs['cliente_id'])
            if cliente.empresa != request.user.empresa:
                messages.error(request, 'Acesso não autorizado.')
                return redirect('orcamentos:lista_orcamentos')
        
        if 'orcamento_id' in kwargs:
            orcamento = get_object_or_404(Orcamento, id=kwargs['orcamento_id'])
            if orcamento.empresa != request.user.empresa:
                messages.error(request, 'Acesso não autorizado.')
                return redirect('orcamentos:lista_orcamentos')
        
        if 'item_id' in kwargs:
            item = get_object_or_404(Item, id=kwargs['item_id'])
            if item.empresa != request.user.empresa:
                messages.error(request, 'Acesso não autorizado.')
                return redirect('orcamentos:lista_itens')
        
        return view_func(request, *args, **kwargs)
    return wrapper

@login_required
@acesso_empresa_required
def lista_orcamentos(request):
    # Inicializar formulário de busca
    form = OrcamentoSearchForm(request.GET or None)
    
    # Obter parâmetros de filtro
    status_filter = request.GET.get('status', 'all')
    sort_by = request.GET.get('sort', 'recentes')
    search_query = request.GET.get('q', '').strip()
    page_number = request.GET.get('page', 1)
    por_pagina = request.GET.get('por_pagina', '10')
    if por_pagina not in OPCOES_POR_PAGINA:
        por_pagina = '10'

    # Base query - apenas orçamentos da empresa do usuário
    orcamentos = Orcamento.objects.filter(empresa=request.user.empresa)

    # Aplicar filtro de status
    if status_filter != 'all':
        orcamentos = orcamentos.filter(status=status_filter)

    # Aplicar busca (cliente, telefone, observações, item ou número do orçamento)
    if search_query:
        busca = (
            Q(cliente__nome__icontains=search_query) |
            Q(cliente__telefone__icontains=search_query) |
            Q(observacoes__icontains=search_query) |
            Q(itens__item__descricao__icontains=search_query) |
            Q(itens__item__nome__icontains=search_query)
        )
        numero = search_query.lstrip('#')
        if numero.isdigit():
            busca |= Q(id=int(numero))
        orcamentos = orcamentos.filter(busca).distinct()

    ordem = '-data_criacao' if sort_by != 'antigos' else 'data_criacao'

    # Uma consulta leve (sem montar objetos) com o necessário de TODOS os
    # orçamentos filtrados: serve para as estatísticas, o valor total e a
    # ordenação por valor. Os objetos completos só são carregados para a
    # página atual, lá embaixo.
    cabecalhos = list(
        orcamentos.order_by(ordem, '-id')
        .values_list('id', 'status', 'desconto_geral', 'valor_adicional')
    )
    totais = _totais_por_orcamento(cabecalhos)

    ids = [id_ for id_, *_ in cabecalhos]
    if sort_by in ('valor-maior', 'valor-menor'):
        ids.sort(key=lambda id_: totais[id_], reverse=(sort_by == 'valor-maior'))

    # Paginação sobre a lista de ids; só a página atual vem do banco completa
    paginator = Paginator(ids, int(por_pagina))
    page_obj = paginator.get_page(page_number)
    pagina = Orcamento.objects.filter(id__in=page_obj.object_list) \
        .select_related('cliente').prefetch_related('itens__item')
    por_id = {o.id: o for o in pagina}
    page_obj.object_list = [por_id[id_] for id_ in page_obj.object_list if id_ in por_id]

    # Estatísticas (sobre todos os orçamentos filtrados, não só a página)
    valor_total = sum(totais.values(), Decimal('0'))
    valor_total = "{:,.2f}".format(valor_total).replace(",", "X").replace(".", ",").replace("X", ".")

    # Parâmetros atuais sem o "page", para os links da paginação manterem os filtros
    parametros = request.GET.copy()
    parametros.pop('page', None)

    context = {
        'orcamentos': page_obj,
        'page_obj': page_obj,
        'paginas': paginator.get_elided_page_range(page_obj.number, on_each_side=2, on_ends=1),
        'parametros_paginacao': parametros.urlencode(),
        'por_pagina': por_pagina,
        'opcoes_por_pagina': OPCOES_POR_PAGINA,
        'form': form,
        'status_filter': status_filter,
        'sort_by': sort_by,
        'search_query': search_query,
        'stats': {
            'total': len(cabecalhos),
            'confirmados': sum(1 for _, status, *_ in cabecalhos if status == 'confirmado'),
            'pendentes': sum(1 for _, status, *_ in cabecalhos if status == 'pendente'),
            'valor_total': valor_total,
        }
    }

    return render(request, "orcamentos/lista.html", context)


OPCOES_POR_PAGINA = ['10', '20', '50']


def _totais_por_orcamento(cabecalhos):
    """
    Total de cada orçamento em uma única consulta aos itens, usando a mesma
    fórmula do Orcamento.total (models.calcular_total).
    cabecalhos: [(id, status, desconto_geral, valor_adicional), ...]
    """
    itens_por_orcamento = {}
    ids = [id_ for id_, *_ in cabecalhos]
    for orcamento_id, valor, quantidade, desconto in (
        OrcamentoItem.objects.filter(orcamento_id__in=ids)
        .values_list('orcamento_id', 'valor', 'quantidade', 'desconto')
    ):
        itens_por_orcamento.setdefault(orcamento_id, []).append((valor, quantidade, desconto))

    return {
        id_: calcular_total(itens_por_orcamento.get(id_, []), desconto_geral, valor_adicional)
        for id_, _, desconto_geral, valor_adicional in cabecalhos
    }

@login_required
@acesso_empresa_required
def detalhes_orcamento(request, orcamento_id):
    # Filtra apenas orçamentos da empresa do usuário
    orcamento = get_object_or_404(
        Orcamento.objects.filter(empresa=request.user.empresa)
        .select_related('cliente')
        .prefetch_related('itens__item'), 
        id=orcamento_id
    )
    
    # Calcular totais
    itens_com_totais = []
    subtotal = 0
    
    for orcamento_item in orcamento.itens.all():
        valor_item = orcamento_item.quantidade * orcamento_item.valor
        desconto_item = valor_item * (orcamento_item.desconto / 100) if orcamento_item.desconto else 0
        total_item = valor_item - desconto_item
        
        itens_com_totais.append({
            'item': orcamento_item.item,
            'quantidade': orcamento_item.quantidade,
            'valor_item': valor_item,
            'desconto_item': desconto_item,
            'subtotal': total_item,
        })
        
        subtotal += total_item
    
    desconto_geral = subtotal * (orcamento.desconto_geral / 100) if orcamento.desconto_geral else 0
    total = subtotal - desconto_geral + (orcamento.valor_adicional or 0)
    total = float(f"{total:.2f}")
    desconto_geral = float(f"{desconto_geral:.2f}")
    saldo_devedor = total - float(f"{orcamento.valor_pago:.2f}")
    
    context = {
        'orcamento': orcamento,
        'itens_com_totais': itens_com_totais,
        'subtotal': subtotal,
        'desconto_geral': orcamento.desconto_geral if orcamento.desconto_geral else 0,
        'valor_desconto': desconto_geral,
        'saldo_devedor': float(f"{saldo_devedor:.2f}"),
        'total': total,
    }
    
    return render(request, "orcamentos/detalhes_orcamento.html", context)

@login_required
def novo_orcamento(request):
    # Filtra clientes e itens apenas da empresa do usuário
    clientes = Cliente.objects.filter(empresa=request.user.empresa)
    itens = Item.objects.filter(empresa=request.user.empresa)
     
    itens_json = json.dumps([{
        "id": item.id,
        "nome": item.nome or item.descricao,
        "descricao": item.descricao,
        "preco": float(item.valor_unitario),
        "desconto": float(item.desconto or 0),
        "categoria": item.categoria,
        "disponivel": True
    } for item in itens])
    
    if request.method == "POST":
        # veifica se existe alguma locação com status 'agendado' para a mesma data
        orcamento_data = request.POST.get("data_evento")
        if Orcamento.objects.filter(
            empresa=request.user.empresa,
            data_evento=orcamento_data,
            status='agendado'
        ).exists():
            messages.error(request, f'Já existe um orçamento agendado para a data {orcamento_data}.')
            return render(request, "orcamentos/novo.html", {
                "clientes": clientes,
                "itens": itens,
                "itens_json": itens_json,
                "clientes_json": json.dumps([{
                    "id": c.id,
                    "nome": c.nome,
                    "telefone": c.telefone,
                } for c in clientes])
            })
        
        telefone = request.POST.get("telefone", "").strip()        
        if len(telefone) < 10:
            messages.error(request, "Telefone inválido")
            return render(request, "orcamentos/novo.html", {
                "clientes": clientes,
                "itens": itens,
                "itens_json": itens_json,
                "clientes_json": json.dumps([{
                    "id": c.id,
                    "nome": c.nome,
                    "telefone": c.telefone,
                } for c in clientes])
            })
    
        try:
            # Busca cliente apenas na empresa do usuário
            cliente = Cliente.objects.get(empresa=request.user.empresa, telefone=telefone)
        except Cliente.DoesNotExist:
            # Cadastrar novo cliente na empresa do usuário
            nome = request.POST.get("nome", "").strip()
            if not nome:
                messages.error(request, "Nome é obrigatório para novo cliente")
                return render(request, "orcamentos/novo.html", {
                    "clientes": clientes,
                    "itens": itens,
                    "itens_json": itens_json,
                    "clientes_json": json.dumps([{
                        "id": c.id,
                        "nome": c.nome,
                        "telefone": c.telefone,
                    } for c in clientes])
                })
            
            cliente = Cliente.objects.create(
                nome=nome, 
                telefone=telefone,
                empresa=request.user.empresa
            )

        desconto = float(request.POST.get("desconto", 0) or 0)
        obs = request.POST.get("observacoes", "")
        data_evento = request.POST.get("data_evento")
        hora_evento = request.POST.get("hora_evento", "16:00")
        periodo_evento = request.POST.get("periodo_evento", "3")
        tipo_evento = request.POST.get("tipo_evento", "Aniversário")
        valor_adicional = float(request.POST.get("valor_adicional", 0) or 0)
        endereco = request.POST.get("endereco", "")
        valor_pago = float(request.POST.get("valor_pago", 0) or 0)
        
        # Validação básica da data do evento
        if not data_evento:
            messages.error(request, "Data do evento é obrigatória")
            return redirect("orcamentos:novo_orcamento")
        
        # Cria o orçamento na empresa do usuário
        orcamento = Orcamento.objects.create(
            cliente=cliente,
            empresa=request.user.empresa,
            criado_por=request.user,
            desconto_geral=desconto,
            observacoes=obs,
            data_evento=data_evento,
            hora_evento=hora_evento,
            periodo_evento=periodo_evento,
            tipo_evento=tipo_evento,
            valor_adicional=valor_adicional,
            status='pendente',
            endereco=endereco,
            valor_pago=valor_pago,
        )

        # Adiciona os itens (já filtrados por empresa)
        itens_payload = []
        itens_adicionados = False
        
        for key, value in request.POST.items():
            if key.startswith("item_") and value:
                try:
                    quantidade = int(value)
                    if quantidade > 0:
                        item_id = key.replace("item_", "")
                        # Garante que o item pertence à empresa
                        item = Item.objects.get(id=item_id, empresa=request.user.empresa)

                        OrcamentoItem.objects.create(
                            orcamento=orcamento,
                            item=item,
                            quantidade=quantidade,
                            valor=valor_item_com_ajuste(item, tipo_evento),
                            desconto=desconto_efetivo_item(request, item)
                        )

                        itens_payload.append({
                            "descricao": item.descricao,
                            "quantidade": quantidade,
                            "valor_unitario": float(item.valor_unitario),
                            "desconto": float(item.desconto or 0),
                        })
                        
                        itens_adicionados = True
                        
                except (ValueError, Item.DoesNotExist) as e:
                    #print(f"Erro ao processar item {key}: {str(e)}")
                    continue

        # Verifica se pelo menos um item foi adicionado
        if not itens_adicionados:
            orcamento.delete()
            messages.error(request, "É necessário adicionar pelo menos um item ao orçamento")
            return redirect("orcamentos:novo_orcamento")
        
        try:
            messages.success(request, f'Orçamento #{orcamento.id} criado com sucesso!')
            return redirect("orcamentos:detalhes_orcamento", orcamento_id=orcamento.id)
            
        except Exception as e:
            #print("Erro ao processar orçamento:", str(e))
            messages.error(request, f'Erro ao processar orçamento: {str(e)}')
            return render(request, "orcamentos/novo.html", {
                "clientes": clientes,
                "itens": itens,
                "itens_json": itens_json,
                "clientes_json": json.dumps([{
                    "id": c.id,
                    "nome": c.nome,
                    "telefone": c.telefone,
                } for c in clientes])
            })

    clientes_json = json.dumps([{
        "id": cliente.id,
        "nome": cliente.nome,
        "telefone": cliente.telefone,
    } for cliente in clientes])

    # Veio da área de clientes com um cliente já escolhido (?cliente_id=...)
    # — pré-preenche nome/telefone no formulário.
    cliente_selecionado = None
    cliente_id = request.GET.get("cliente_id")
    if cliente_id:
        cliente_selecionado = clientes.filter(id=cliente_id).first()

    return render(request, "orcamentos/novo.html", {
        "clientes": clientes,
        "itens": itens,
        "itens_json": itens_json,
        "clientes_json": clientes_json,
        "cliente": cliente_selecionado,
    })

@login_required
def confirmar_conflito(request):
    """Página dedicada para confirmar conflitos de agendamento"""
    if 'orcamento_temp_data' not in request.session:
        messages.error(request, 'Dados do orçamento não encontrados.')
        return redirect('orcamentos:novo_orcamento')
    
    temp_data = request.session['orcamento_temp_data']
    
    # Recupera os orçamentos conflitantes
    orcamentos_conflitantes = Orcamento.objects.filter(
        empresa=request.user.empresa,
        data_evento=temp_data['data_conflito'],
        status='agendado'
    )
    
    # Filtra clientes e itens
    clientes = Cliente.objects.filter(empresa=request.user.empresa)
    itens = Item.objects.filter(empresa=request.user.empresa)
    
    itens_json = json.dumps([{
        "id": item.id,
        "nome": item.nome or item.descricao,
        "descricao": item.descricao,
        "preco": float(item.valor_unitario),
        "desconto": float(item.desconto or 0),
        "categoria": item.categoria,
        "disponivel": True
    } for item in itens])
    
    context = {
        "clientes": clientes,
        "itens": itens,
        "itens_json": itens_json,
        "clientes_json": json.dumps([{
            "id": c.id,
            "nome": c.nome,
            "telefone": c.telefone,
        } for c in clientes]),
        "data_conflito": temp_data['data_conflito'],
        "orcamentos_conflitantes": orcamentos_conflitantes,
        "post_data": temp_data['post_data']
    }
    
    return render(request, "orcamentos/confirmar_conflito.html", context)

# Eventos públicos têm custo/risco operacional maior (fluxo de pessoas não
# convidadas, desgaste extra dos brinquedos, etc.), por isso o valor de cada
# item é automaticamente ajustado pra cima nesses casos. Sem estimativa de
# público o risco é maior (não dá pra dimensionar equipe/material), por
# isso o ajuste é maior.
AJUSTE_VALOR_EVENTO_PUBLICO = {
    "Evento Público (com estimativa de público)": Decimal('1.15'),
    "Evento Público (sem estimativa de público)": Decimal('1.20'),
}

# Em "Frente de Loja", as máquinas de buffet têm desgaste/operação maior,
# então recebem um acréscimo próprio de 35% (só nelas, não no resto do
# orçamento), arredondado pro inteiro mais próximo (sem centavos).
AJUSTE_BUFFET_FRENTE_DE_LOJA = Decimal('1.35')

def valor_item_com_ajuste(item, tipo_evento):
    """Aplica o acréscimo automático de evento público (15%/20%) sobre o
    valor de catálogo do item, se o tipo de evento for um dos públicos, e o
    acréscimo de 35% nas máquinas de buffet quando o evento for "Frente de
    Loja" (arredondado pro inteiro mais próximo)."""
    fator = AJUSTE_VALOR_EVENTO_PUBLICO.get(tipo_evento, Decimal('1'))
    valor = Decimal(item.valor_unitario) * fator

    if tipo_evento == "Frente de Loja" and item.categoria == "buffet":
        valor = (valor * AJUSTE_BUFFET_FRENTE_DE_LOJA).to_integral_value(rounding=ROUND_HALF_UP)

    return valor

def desconto_efetivo_item(request, item):
    """O desconto padrão do item só é aplicado ao orçamento se o usuário não
    tiver desmarcado a caixinha "Aplicar desconto padrão" desse item na tela
    de criar/editar orçamento (campo desconto_ativo_<id> no POST). Sem esse
    campo (ex.: item sem desconto, checkbox nem chega a existir), assume
    ativo por padrão."""
    ativo = request.POST.get(f'desconto_ativo_{item.id}', '1') == '1'
    return item.desconto if ativo else Decimal('0')

@login_required
def criar_orcamento(request, clientes, itens, itens_json, ignorar_conflito=False):
    """Função auxiliar para criar orçamento via requisição normal"""
    if request.method != "POST":
        return redirect("orcamentos:novo_orcamento")
    
    
    orcamento_data = request.POST.get("data_evento")
    
    if not ignorar_conflito:
        # Verifica novamente por conflitos
        orcamentos_conflitantes = Orcamento.objects.filter(
            empresa=request.user.empresa,
            data_evento=orcamento_data,
            status='confirmado'
        )
        
        if orcamentos_conflitantes.exists():
            messages.error(request, 'Conflito de agendamento detectado. Por favor, confirme o conflito.')
            return redirect('orcamentos:confirmar_conflito')
    
    
    #print("Criando orçamento com dados:", request.POST)
    # Cria o orçamento
    cliente_id = request.POST.get("cliente")
    desconto = float(request.POST.get("desconto", 0) or 0)
    obs = request.POST.get("observacoes", "")
    data_evento = request.POST.get("data_evento")
    valor_pago = float(request.POST.get("valor_pago", 0) or 0)
    hora_evento = request.POST.get("hora_evento", "16:00")
    periodo_evento = request.POST.get("periodo_evento", "3")
    tipo_evento = request.POST.get("tipo_evento", "Aniversário")
    valor_adicional = float(request.POST.get("valor_adicional", 0) or 0)
    endereco = request.POST.get("endereco", "")
    #print(f"Dados do orçamento: cliente_id={cliente_id}, desconto={desconto}, obs={obs}, data_evento={data_evento}, valor_pago={valor_pago}, hora_evento={hora_evento}, periodo_evento={periodo_evento}, tipo_evento={tipo_evento}, valor_adicional={valor_adicional}, endereco={endereco}")
    #verifica se o cliente existe na empresa do usuário
    try:
        cliente = Cliente.objects.get(id=cliente_id, empresa=request.user.empresa)
    except Cliente.DoesNotExist:
        # Se o cliente não existir, cria um novo cliente genérico
        orcamento = Orcamento.objects.create(
            empresa=request.user.empresa,
            cliente=cliente,
            desconto_geral=desconto,
            observacoes=obs,
            data_evento=data_evento,
            valor_pago=valor_pago,
            hora_evento=hora_evento,
            periodo_evento=periodo_evento,
            tipo_evento=tipo_evento,
            valor_adicional=valor_adicional,
            endereco=endereco,
            status='pendente' if valor_pago < 0.01 else 'confirmado'
        )
    #print(f"Orçamento criado com ID: {orcamento.id}")
    # Adiciona os itens
    for key, value in request.POST.items():
        if key.startswith("item_"):
            try:
                quantidade = int(value)
                if quantidade > 0:
                    item_id = key.replace("item_", "")
                    item = get_object_or_404(Item, id=item_id, empresa=request.user.empresa)
                    OrcamentoItem.objects.create(
                        orcamento=orcamento,
                        item=item,
                        quantidade=quantidade,
                        valor=valor_item_com_ajuste(item, tipo_evento),
                        desconto=desconto_efetivo_item(request, item)
                    )
            except ValueError:
                pass
    #print(f"Orçamento #{orcamento.id} criado com sucesso.")
    # Limpa os dados temporários da sessão
    if 'orcamento_temp_data' in request.session:
        del request.session['orcamento_temp_data']
    messages.success(request, f'Orçamento #{orcamento.id} criado com sucesso!')
    return redirect("orcamentos:detalhes_orcamento", orcamento_id=orcamento.id)

@login_required
@acesso_empresa_required
def editar_orcamento(request, orcamento_id):
    orcamento = get_object_or_404(
        Orcamento.objects.filter(empresa=request.user.empresa)
        .prefetch_related('itens__item'), 
        id=orcamento_id
    )
    
    # Filtra apenas clientes e itens da empresa
    clientes = Cliente.objects.filter(empresa=request.user.empresa)
    itens = Item.objects.filter(empresa=request.user.empresa)
    
    itens_json = json.dumps([{
        "id": item.id,
        "nome": item.nome or item.descricao,
        "descricao": item.descricao,
        "preco": float(item.valor_unitario),
        "desconto": float(item.desconto or 0),
        "categoria": item.categoria,
        "disponivel": True
    } for item in itens])
    
    # Preparar dados dos itens atuais (inclui se o desconto do item estava
    # ativo ou foi desligado manualmente neste orçamento: se o valor salvo
    # em OrcamentoItem.desconto for zero mas o item tiver desconto padrão no
    # catálogo, é porque foi desativado de propósito ao criar/editar).
    itens_selecionados = {
        str(oi.item.id): {
            "quantidade": oi.quantidade,
            "desconto_ativo": bool(oi.desconto and oi.desconto > 0),
        }
        for oi in orcamento.itens.all()
    }
    itens_selecionados = json.dumps(itens_selecionados)
    
    if request.method == "POST":
        desconto = float(request.POST.get("desconto", 0) or 0)
        obs = request.POST.get("observacoes", "")
        data_evento = request.POST.get("data_evento")
        valor_pago = float(request.POST.get("valor_pago", 0) or 0)
        hora_evento = request.POST.get("hora_evento", "16:00")
        periodo_evento = request.POST.get("periodo_evento", "3")
        tipo_evento = request.POST.get("tipo_evento", "Aniversário")
        valor_adicional = float(request.POST.get("valor_adicional", 0) or 0)
        endereco = request.POST.get("endereco", "")
        custo_operacional = float(request.POST.get("custo_operacional", 0) or 0)
        
        # Atualiza o orçamento
        orcamento.desconto_geral = desconto
        orcamento.observacoes = obs
        orcamento.data_evento = data_evento
        orcamento.valor_pago = valor_pago
        orcamento.hora_evento = hora_evento
        orcamento.periodo_evento = periodo_evento
        orcamento.tipo_evento = tipo_evento
        orcamento.valor_adicional = valor_adicional
        orcamento.endereco = endereco
        orcamento.custo_operacional = custo_operacional
        orcamento.save()
        
        # Remove todos os itens atuais
        orcamento.itens.all().delete()
        
        # Adiciona os novos itens (apenas da empresa)
        for key, value in request.POST.items():
            if key.startswith("item_"):
                try:
                    quantidade = int(value)
                    if quantidade > 0:
                        item_id = key.replace("item_", "")
                        item = get_object_or_404(Item, id=item_id, empresa=request.user.empresa)
                        OrcamentoItem.objects.create(
                            orcamento=orcamento,
                            item=item,
                            quantidade=quantidade,
                            valor=valor_item_com_ajuste(item, tipo_evento),
                            desconto=desconto_efetivo_item(request, item)
                        )
                except ValueError:
                    pass
        
        messages.success(request, f'Orçamento #{orcamento.id} atualizado com sucesso!')
        return redirect("orcamentos:detalhes_orcamento", orcamento_id=orcamento.id)
    
    context = {
        "orcamento": orcamento,
        "clientes": clientes,
        "itens": itens,
        "itens_selecionados": itens_selecionados,
        "itens_json": itens_json,
    }
    
    return render(request, "orcamentos/editar.html", context)

@login_required
@acesso_empresa_required
def excluir_orcamento(request, orcamento_id):
    orcamento = get_object_or_404(Orcamento.objects.filter(empresa=request.user.empresa), id=orcamento_id)
    
    if request.method == "POST":
        # Excluir arquivos PDF/PNG se existirem
        if orcamento.pdf and os.path.exists(orcamento.pdf.path):
            os.remove(orcamento.pdf.path)
        if orcamento.png and os.path.exists(orcamento.png.path):
            os.remove(orcamento.png.path)
        
        orcamento.delete()
        messages.success(request, f'Orçamento #{orcamento_id} excluído com sucesso!')
        return redirect("orcamentos:lista_orcamentos")
    
    return render(request, "orcamentos/confirmar_exclusao.html", {"orcamento": orcamento})

def prefixo_nome_documento(orcamento):
    """Quando o orçamento está confirmado, o documento gerado é uma
    confirmação de agendamento (ver gerar_arquivos), não mais um orçamento
    comum — o nome do arquivo baixado reflete isso."""
    return 'Confirmacao' if orcamento.status == 'confirmado' else 'Orcamento'

@login_required
@acesso_empresa_required
def baixar_pdf(request, orcamento_id):
    orcamento = get_object_or_404(Orcamento.objects.filter(empresa=request.user.empresa), id=orcamento_id)
    return gerar_e_baixar_pdf(request, orcamento)
    # Verifica se o campo pdf existe no banco de dados
    if orcamento.pdf:
        file_path = orcamento.pdf.path
        #print(f"Tentando baixar PDF do caminho: {file_path}")
        
        # Verifica se o arquivo existe fisicamente
        if not os.path.exists(file_path):
            #print("Arquivo PDF não encontrado no sistema de arquivos. Gerando novo PDF.")
            # Remove a referência ao arquivo que não existe mais
            orcamento.pdf.delete(save=False)
            orcamento.save()
            return gerar_e_baixar_pdf(request, orcamento)
        
        try:
            # Serve o arquivo diretamente
            filename = f'{prefixo_nome_documento(orcamento)}_{orcamento.cliente.nome}.pdf'
            response = FileResponse(open(file_path, 'rb'), content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
            
        except Exception as e:
            messages.error(request, f'Erro ao baixar o arquivo PDF: {str(e)}')
            return redirect("orcamentos:detalhes_orcamento", orcamento_id=orcamento_id)
    
    else:
        # Se o PDF não existe no campo, gera um novo
        return gerar_e_baixar_pdf(request, orcamento)
    
    
def gerar_e_baixar_pdf(request, orcamento):
    try:
        empresa = orcamento.empresa
        pdf, png = gerar_arquivos(orcamento, empresa)
        
        
        # Serve o arquivo recém-criado
        file_path = pdf 
        filename = f'{prefixo_nome_documento(orcamento)}_{orcamento.cliente.nome}.pdf'
        
        response = FileResponse(open(file_path, 'rb'), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
        
    except Exception as e:
        #print(f"Erro ao gerar PDF: {str(e)}")
        messages.error(request, 'Erro ao gerar o arquivo PDF.')
        print(f"Erro ao gerar PDF do orçamento #{orcamento.id}: {str(e)}")
        return redirect("orcamentos:detalhes_orcamento", orcamento_id=orcamento.id)

@login_required
@acesso_empresa_required
def baixar_png(request, orcamento_id):
    """
    Gera (sob demanda, igual ao PDF) e serve a versão em imagem do
    orçamento — orçamento normal ou confirmação de agendamento, dependendo
    do status atual — para facilitar o compartilhamento por WhatsApp.
    """
    orcamento = get_object_or_404(Orcamento.objects.filter(empresa=request.user.empresa), id=orcamento_id)
    try:
        empresa = orcamento.empresa
        pdf, png = gerar_arquivos(orcamento, empresa)

        if not png or not os.path.exists(png):
            messages.error(request, 'Erro ao gerar a imagem do orçamento.')
            return redirect("orcamentos:detalhes_orcamento", orcamento_id=orcamento.id)

        filename = f'{prefixo_nome_documento(orcamento)}_{orcamento.cliente.nome}.png'
        response = FileResponse(open(png, 'rb'), content_type='image/png')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    except Exception as e:
        messages.error(request, 'Erro ao gerar a imagem do orçamento.')
        print(f"Erro ao gerar imagem do orçamento #{orcamento.id}: {str(e)}")
        return redirect("orcamentos:detalhes_orcamento", orcamento_id=orcamento.id)

@login_required
@require_http_methods(["POST"])
def gerar_catalogo_pdf_view(request):
    """
    Gera um PDF só com os itens (e quantidades) selecionados na tela de novo
    orçamento, no mesmo estilo visual do orçamento, mas sem dados de
    cliente/evento — como um catálogo de preços para mostrar ao cliente antes
    de fechar o orçamento. Recebe os itens ainda não salvos (orçamento em
    edição), então busca preço/descrição atuais no banco pelo id do item,
    ignorando qualquer valor enviado pelo navegador.
    """
    if not hasattr(request.user, 'empresa') or not request.user.empresa:
        return JsonResponse({'erro': 'Usuário sem empresa associada.'}, status=403)

    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({'erro': 'Dados inválidos.'}, status=400)

    itens_selecionados = payload.get('itens', [])
    if not itens_selecionados:
        return JsonResponse({'erro': 'Selecione ao menos um item.'}, status=400)

    # Mesmo acréscimo de evento público (15%/20%) aplicado ao salvar o
    # orçamento, pra o catálogo já refletir o valor que vai ser cobrado.
    tipo_evento = payload.get('tipo_evento', '')

    ids = [i.get('id') for i in itens_selecionados if i.get('id')]
    itens_por_id = {
        item.id: item
        for item in Item.objects.filter(empresa=request.user.empresa, id__in=ids)
    }

    dados_catalogo = []
    for sel in itens_selecionados:
        item = itens_por_id.get(sel.get('id'))
        if not item:
            continue
        try:
            quantidade = int(sel.get('quantidade', 1) or 1)
        except (TypeError, ValueError):
            quantidade = 1
        if quantidade <= 0:
            continue
        dados_catalogo.append({
            "descricao": item.nome or item.descricao,
            "quantidade": quantidade,
            "valor_unitario": float(valor_item_com_ajuste(item, tipo_evento)),
            "desconto": float(item.desconto or 0),
        })

    if not dados_catalogo:
        return JsonResponse({'erro': 'Nenhum item válido encontrado.'}, status=400)

    pdf_path = gerar_catalogo(dados_catalogo, request.user.empresa)
    if not pdf_path or not os.path.exists(pdf_path):
        return JsonResponse({'erro': 'Não foi possível gerar o PDF.'}, status=500)

    response = FileResponse(open(pdf_path, 'rb'), content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="catalogo_mundo_kids.pdf"'
    return response

@login_required
@acesso_empresa_required
def gerar_checklist_pdf_view(request, orcamento_id):
    """
    Gera o PDF de conferência (checklist de acessórios por brinquedo) do
    orçamento, para usar na hora de separar/carregar o material do evento.
    """
    orcamento = get_object_or_404(Orcamento.objects.filter(empresa=request.user.empresa), id=orcamento_id)

    pdf_path = gerar_checklist_conferencia(orcamento, request.user.empresa)
    if not pdf_path or not os.path.exists(pdf_path):
        messages.error(request, 'Não foi possível gerar o checklist de conferência.')
        return redirect("orcamentos:detalhes_orcamento", orcamento_id=orcamento_id)

    filename = f'Checklist_{orcamento.cliente.nome}.pdf'
    response = FileResponse(open(pdf_path, 'rb'), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

@login_required
@acesso_empresa_required
def gerar_recibo_pdf_view(request, orcamento_id):
    """
    Gera um recibo em PDF referente ao valor já pago do orçamento — só faz
    sentido (e só fica visível na tela) quando há algum valor pago.
    """
    orcamento = get_object_or_404(Orcamento.objects.filter(empresa=request.user.empresa), id=orcamento_id)

    if not orcamento.valor_pago or orcamento.valor_pago <= 0:
        messages.error(request, 'Este orçamento ainda não possui valor pago para gerar recibo.')
        return redirect("orcamentos:detalhes_orcamento", orcamento_id=orcamento_id)

    pdf_path = gerar_recibo(orcamento, request.user.empresa)
    if not pdf_path or not os.path.exists(pdf_path):
        messages.error(request, 'Não foi possível gerar o recibo.')
        return redirect("orcamentos:detalhes_orcamento", orcamento_id=orcamento_id)

    filename = f'Recibo_{orcamento.cliente.nome}.pdf'
    response = FileResponse(open(pdf_path, 'rb'), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

@login_required
@acesso_empresa_required
def alterar_status(request, orcamento_id):
    try:
        # Filtra por empresa do usuário logado
        orcamento = get_object_or_404(
            Orcamento.objects.filter(empresa=request.user.empresa),  # Note: 'emrpesa' com r
            id=orcamento_id
        )
        
        novo_status = request.POST.get("status")
        
        # Verifica se o status é válido
        if novo_status not in dict(Orcamento.STATUS_CHOICES):
            messages.error(request, f'Status "{novo_status}" inválido.')
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': 'Status inválido'}, status=400)
            return redirect("orcamentos:detalhes_orcamento", orcamento_id=orcamento_id)
        #apaga o pdf e png se o status for alterado para pendente
        if orcamento.pdf and os.path.exists(orcamento.pdf.path):
            os.remove(orcamento.pdf.path)
            orcamento.pdf = None
        # Altera o status
        orcamento.status = novo_status
        print(f"Alterando status do orçamento #{orcamento_id} para {novo_status}")
        if novo_status == 'concluido':
            print("Orçamento concluído, marcando como pago.")
            orcamento.valor_pago = orcamento.total
        orcamento.save()
        enviar_notificacao_whatsapp(request, orcamento.id)
        # Mensagem de sucesso
        status_display = dict(Orcamento.STATUS_CHOICES).get(novo_status, novo_status)
        messages.success(request, f'Status do orçamento #{orcamento_id} alterado para {status_display}.')
        
        # Resposta para AJAX
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True, 
                'new_status': novo_status,
                'new_status_display': status_display
            })
        
    except Exception as e:
        # Log do erro (em produção, use logging)
        #print(f"Erro ao alterar status: {e}")
        messages.error(request, 'Erro ao alterar status do orçamento.')
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

    # Permite voltar para a tela de agendamentos quando a ação veio de lá
    if request.POST.get("next") == "agendamentos":
        return redirect("orcamentos:agendamentos")
    return redirect("orcamentos:detalhes_orcamento", orcamento_id=orcamento_id)


def mensagem_status_cliente(orcamento):
    """
    Mensagem de WhatsApp para o cliente conforme o status atual do orçamento.
    Retorna (mensagem, incluir_recibo) ou (None, False) se o status não avisa.
    """
    nome = orcamento.cliente.nome
    data = orcamento.data_evento.strftime('%d/%m/%Y') if orcamento.data_evento else None
    do_dia = f" do dia *{data}*" if data else ""
    status = orcamento.status

    if status == 'pendente':
        return (
            f"Da só uma olhadinha, {nome}!\n\n"
            f"Seu orçamento *#{orcamento.id}* está PRONTOO!! 🥳🎉\n\n"
            "Dá uma conferida nos detalhes e, se estiver tudo certo, é só confirmar com a gente! ✅\n\n"
            "Estamos super animados para fazer do seu evento um momento inesquecível! 🎪✨\n"
            "Qualquer dúvida, é só chamar! 😊\n\n"
        ), False
    if status == 'confirmado':
        return (
            f"🎉 Olá, {nome}!\n\n"
            f"Seu orçamento *#{orcamento.id}* foi *confirmado com sucesso* ✅\n\n"
            "Estamos cuidando de tudo para que seu evento seja incrível! 🎪✨\n"
            "Se tiver qualquer dúvida ou precisar ajustar algo, é só falar com a gente 😊\n\n"
            "— Mundo Kids 💙"
        ), False
    if status == 'concluido':
        # Ao concluir o evento o valor pago vira o total, então vai o recibo de quitação junto
        return (
            f"🎉 Olá, {nome}!\n\n"
            f"Seu evento{do_dia} (orçamento *#{orcamento.id}*) foi *concluído* com sucesso! ✅\n\n"
            "Muito obrigado por escolher a Mundo Kids para fazer parte desse momento! 💙✨\n\n"
            "🧾 No PDF também está o *recibo* de quitação.\n\n"
            f"{AVISO_NOTA_FISCAL}"
            "Se puder, conta pra gente como foi a festa! 😊\n\n"
            "— Mundo Kids 💙"
        ), True
    if status == 'reagendar':
        return (
            f"Olá, {nome}! 😊\n\n"
            f"Seu evento{do_dia} (orçamento *#{orcamento.id}*) foi marcado para *reagendamento* 📅\n\n"
            "Em breve entramos em contato para combinar a nova data. "
            "Se você já tiver uma data em mente, é só mandar por aqui!\n\n"
            "— Mundo Kids 💙"
        ), False
    if status == 'cancelado':
        return (
            f"Olá, {nome}.\n\n"
            f"Seu evento{do_dia} (orçamento *#{orcamento.id}*) foi *cancelado*.\n\n"
            "Se foi um engano ou se quiser remarcar para outra data, é só chamar a gente por aqui. "
            "Vamos adorar fazer parte da sua festa! 💙\n\n"
            "— Mundo Kids"
        ), False
    return None, False


@login_required
def enviar_notificacao_whatsapp(request, orcamento_id):
    """
    Avisa o cliente pelo WhatsApp (via n8n) da mudança de status, com o PDF
    do orçamento. O envio roda em segundo plano para a tela não travar.
    """
    try:
        orcamento = Orcamento.objects.select_related('cliente').get(id=orcamento_id, empresa=request.user.empresa)
        mensagem, incluir_recibo = mensagem_status_cliente(orcamento)
        if mensagem:
            enviar_em_segundo_plano(
                orcamento.cliente.telefone, mensagem, orcamento.id, incluir_recibo=incluir_recibo
            )
    except Exception as e:
        print(f"Erro ao enviar notificação via WhatsApp: {str(e)}")

    return redirect("orcamentos:detalhes_orcamento", orcamento_id=orcamento_id)
        

# Views para Clientes (filtrados por empresa)
@login_required
def lista_clientes(request):
    busca = request.GET.get('busca', '')
    ordenacao = request.GET.get('ordenacao', 'nome')
    page_number = request.GET.get('page', 1)
    
    # Apenas clientes da empresa do usuário
    clientes = Cliente.objects.filter(empresa=request.user.empresa)
    
    if busca:
        clientes = clientes.filter(
            Q(nome__icontains=busca) |
            Q(telefone__icontains=busca)
        )
    
    if ordenacao == 'nome':
        clientes = clientes.order_by('nome')
    elif ordenacao == 'data_cadastro':
        clientes = clientes.order_by('-data_cadastro')
    elif ordenacao == 'ultimo_orcamento':
        clientes = clientes.annotate(
            ultima_data=Max('orcamentos__data_criacao')
        ).order_by('-ultima_data')
    
    paginator = Paginator(clientes, 20)
    page_obj = paginator.get_page(page_number)
    
    total_clientes = clientes.count()
    clientes_com_orcamento = Orcamento.objects.filter(
        empresa=request.user.empresa
    ).values('cliente').distinct().count()
    
    context = {
        'clientes': page_obj,
        'page_obj': page_obj,
        'busca': busca,
        'ordenacao': ordenacao,
        'total_clientes': total_clientes,
        'clientes_com_orcamento': clientes_com_orcamento,
    }
    
    return render(request, 'orcamentos/lista_clientes.html', context)

@login_required
@acesso_empresa_required
def cliente_detalhes(request, cliente_id):
    cliente = get_object_or_404(Cliente.objects.filter(empresa=request.user.empresa), id=cliente_id)
    
    orcamentos = Orcamento.objects.filter(cliente=cliente, empresa=request.user.empresa).order_by('-data_criacao')
    
    total_orcamentos = orcamentos.count()
    orcamentos_confirmados = orcamentos.filter(status='confirmado').count()
    orcamentos_concluidos = orcamentos.filter(status='concluido').count()
    
    valor_total = 0
    for orcamento in orcamentos:
        valor_total += orcamento.total
    
    context = {
        'cliente': cliente,
        'orcamentos': orcamentos[:10],
        'total_orcamentos': total_orcamentos,
        'orcamentos_confirmados': orcamentos_confirmados,
        'orcamentos_concluidos': orcamentos_concluidos,
        'valor_total': valor_total,
    }
    
    return render(request, 'orcamentos/cliente_detalhes.html', context)

@login_required
@acesso_empresa_required
def excluir_cliente(request, cliente_id):
    cliente = get_object_or_404(Cliente.objects.filter(empresa=request.user.empresa), id=cliente_id)
    
    if request.method == 'POST':
        if Orcamento.objects.filter(cliente=cliente, empresa=request.user.empresa).exists():
            messages.error(request, 'Não é possível excluir um cliente que possui orçamentos associados.')
            return redirect('orcamentos:lista_clientes')
        
        cliente.delete()
        messages.success(request, f'Cliente {cliente.nome} excluído com sucesso!')
        return redirect('orcamentos:lista_clientes')
    
    return redirect('orcamentos:lista_clientes')

@login_required
def novo_cliente(request):
    if request.method == "POST":
        form = ClienteForm(request.POST, empresa=request.user.empresa)
        if form.is_valid():
            cliente = form.save(commit=False)
            cliente.empresa = request.user.empresa  # Associa à empresa do usuário
            cliente.save()
            
            messages.success(request, 'Cliente cadastrado com sucesso!')
            
            if request.GET.get('from_orcamento'):
                return redirect(f"{reverse('orcamentos:novo_orcamento')}?cliente_id={cliente.id}")
            
            return redirect("orcamentos:lista_clientes")
        else:
            messages.error(request, 'Por favor, corrija os erros abaixo.')
    else:
        form = ClienteForm()
                                      
    return render(request, "orcamentos/adicionar_cliente.html", {"form": form})

# Views para Itens (filtrados por empresa)
@login_required
def lista_itens(request):
    itens = Item.objects.filter(empresa=request.user.empresa)
    #buscando a quantidade de orçamentos confirmados ou concluídos que possuem cada item
    for item in itens:        
        item.uso_count = OrcamentoItem.objects.filter(
            item=item,
            orcamento__empresa=request.user.empresa,
            orcamento__status__in=['confirmado', 'concluido']
        ).count()  
        # (35/100) é int/int em Python 3, que dá float — e Decimal não pode
        # ser multiplicado por float diretamente. Por isso usamos Decimal('0.35').
        item.faturamento = (item.uso_count * item.valor_unitario) - ((item.uso_count * item.valor_unitario) * Decimal('0.35') if item.desconto else 0)
    
    return render(request, "orcamentos/itensLista.html", {"itens": itens})

def salvar_checklist_item(request, item):
    """
    Substitui os itens do checklist de conferência pelo que veio do
    formulário (campo repetido checklist_itens[]), na ordem em que foram
    enviados. Ignora entradas em branco.
    """
    textos = [t.strip() for t in request.POST.getlist('checklist_itens[]') if t.strip()]
    item.checklist_itens.all().delete()
    ChecklistItem.objects.bulk_create([
        ChecklistItem(item=item, descricao=texto, ordem=ordem)
        for ordem, texto in enumerate(textos)
    ])

@login_required
def novo_item(request):
    if request.method == "POST":
        form = ItemForm(request.POST, request.FILES)
        if form.is_valid():
            item = form.save(commit=False)
            item.empresa = request.user.empresa  # Associa à empresa do usuário
            item.save()
            salvar_checklist_item(request, item)
            messages.success(request, 'Item cadastrado com sucesso!')
            return redirect("orcamentos:lista_itens")
    else:
        form = ItemForm()

    return render(request, "orcamentos/itens.html", {"form": form})

@login_required
def editar_item(request, item_id):
    item = get_object_or_404(Item.objects.filter(empresa=request.user.empresa), id=item_id)

    if request.method == "POST":
        form = ItemForm(request.POST, request.FILES, instance=item)
        if form.is_valid():
            form.save()
            salvar_checklist_item(request, item)
            messages.success(request, 'Item atualizado com sucesso!')
            return redirect("orcamentos:lista_itens")
    else:
        form = ItemForm(instance=item)

    return render(request, "orcamentos/itens.html", {
        "form": form,
        "item": item,
        "checklist_itens": item.checklist_itens.all(),
    })

@login_required
def excluir_item(request, item_id):
    excluir = request.POST.get("confirmar", "não")
    item = get_object_or_404(Item.objects.filter(empresa=request.user.empresa), id=item_id)
    
    if excluir == "sim":
        if OrcamentoItem.objects.filter(item=item, orcamento__empresa=request.user.empresa).exists():
            messages.error(request, 'Não é possível excluir um item que está associado a orçamentos.')
            return redirect("orcamentos:lista_itens")
        
        item.delete()
        messages.success(request, 'Item excluído com sucesso!')
        return redirect("orcamentos:lista_itens")
    return render(request, "orcamentos/confirmar_exclusao_item.html", {"item": item})


# Views para Agendamentos (filtrados por empresa)
@login_required
def agendamentos(request):
    # Data atual
    hoje = timezone.now().date()
    
    # Obter filtros
    status_filter = request.GET.get('status', 'todos')
    data_filter = request.GET.get('data', '')
    periodo_filter = request.GET.get('periodo', '')
    mes_filter = request.GET.get('mes')  # Novo parâmetro para navegação do calendário
    
    # Determinar o mês a ser exibido no calendário
    if mes_filter:
        try:
            mes_atual = datetime.strptime(mes_filter, '%Y-%m').date().replace(day=1)
        except ValueError:
            mes_atual = hoje.replace(day=1)
    elif data_filter:
        # Se o usuário clicou em um dia do calendário (?data=...) sem informar
        # o mês, mantém o calendário no mês da data selecionada em vez de
        # voltar sempre para o mês atual.
        try:
            mes_atual = datetime.strptime(data_filter, '%Y-%m-%d').date().replace(day=1)
        except ValueError:
            mes_atual = hoje.replace(day=1)
    else:
        mes_atual = hoje.replace(day=1)
    
    # Calcular mês anterior e próximo para navegação
    mes_anterior = (mes_atual - timedelta(days=1)).replace(day=1)
    mes_proximo = (mes_atual + timedelta(days=32)).replace(day=1)
    
    # Apenas orçamentos da empresa do usuário. O cliente e os itens já vêm
    # junto (select/prefetch) porque cada card mostra o cliente e calcula
    # total/saldo várias vezes — sem isso era uma consulta por card/cálculo.
    orcamentos = Orcamento.objects.filter(
        empresa=request.user.empresa,
        status__in=['confirmado', 'concluido', 'reagendar']  # Excluir pendentes e cancelados
    ).select_related('cliente').prefetch_related('itens')
    
    # Orçamentos pendentes de conclusão (confirmados com data passada)
    orcamentos_para_concluir = orcamentos.filter(
        status='confirmado', 
        data_evento__lt=hoje
    ).order_by('data_evento', 'hora_evento')
    
    # Aplicar filtros de status
    if status_filter != 'todos':
        orcamentos = orcamentos.filter(status=status_filter)
    
    # Aplicar filtros de data
    if data_filter:
        try:
            data_filtro = datetime.strptime(data_filter, '%Y-%m-%d').date()
            orcamentos = orcamentos.filter(data_evento=data_filtro)
        except ValueError:
            pass
    elif periodo_filter:
        if periodo_filter == 'hoje':
            orcamentos = orcamentos.filter(data_evento=hoje)
        elif periodo_filter == 'semana':
            inicio_semana = hoje - timedelta(days=hoje.weekday())
            fim_semana = inicio_semana + timedelta(days=6)
            orcamentos = orcamentos.filter(data_evento__range=[inicio_semana, fim_semana])
        elif periodo_filter == 'mes':
            inicio_mes = hoje.replace(day=1)
            fim_mes = (inicio_mes + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            orcamentos = orcamentos.filter(data_evento__range=[inicio_mes, fim_mes])
        elif periodo_filter == 'proxima_semana':
            inicio_proxima = hoje + timedelta(days=(7 - hoje.weekday()))
            fim_proxima = inicio_proxima + timedelta(days=6)
            orcamentos = orcamentos.filter(data_evento__range=[inicio_proxima, fim_proxima])
    
    # ✅ FILTRO PADRÃO (se nenhum filtro específico)
    if not data_filter and not periodo_filter:
        orcamentos = orcamentos.filter(data_evento__gte=hoje)
    
    # Separar por categorias
    agendamentos_hoje = orcamentos.filter(data_evento=hoje).order_by('hora_evento')
    
    trinta_dias = hoje + timedelta(days=30)
    proximos_agendamentos = orcamentos.filter(
        data_evento__range=[hoje + timedelta(days=1), trinta_dias]
    ).order_by('data_evento', 'hora_evento')
    
    # Concluídos dos últimos 30 dias
    agendamentos_concluidos = Orcamento.objects.filter(
        empresa=request.user.empresa,
        status='concluido',
        data_evento__gte=hoje - timedelta(days=30)
    ).select_related('cliente').prefetch_related('itens').order_by('-data_evento')
    
    # Gerar calendário para o mês atual
    # O cabeçalho do calendário começa no domingo (Dom, Seg, Ter...), mas
    # date.weekday() considera segunda-feira = 0. Sem essa conversão, a
    # grade começava sempre na segunda-feira anterior e todos os dias
    # ficavam desalinhados uma coluna à frente do dia da semana correto.
    dias_ate_domingo_anterior = (mes_atual.weekday() + 1) % 7
    primeiro_dia_semana = mes_atual - timedelta(days=dias_ate_domingo_anterior)

    data_selecionada = None
    if data_filter:
        try:
            data_selecionada = datetime.strptime(data_filter, '%Y-%m-%d').date()
        except ValueError:
            data_selecionada = None

    # Dias da grade (6 semanas) que têm evento, numa única consulta
    ultimo_dia_grade = primeiro_dia_semana + timedelta(days=41)
    dias_com_evento = set(
        Orcamento.objects.filter(
            empresa=request.user.empresa,
            data_evento__range=[primeiro_dia_semana, ultimo_dia_grade],
            status__in=['confirmado', 'concluido', 'reagendar']  # mesmo critério usado para "agendamentos" nesta tela
        ).values_list('data_evento', flat=True).distinct()
    )

    dias_calendario = []
    for i in range(42):  # 6 semanas
        dia = primeiro_dia_semana + timedelta(days=i)
        tem_eventos = dia in dias_com_evento

        dias_calendario.append({
            'dia': dia.day,
            'data': dia.strftime('%Y-%m-%d'),
            'hoje': dia == hoje,
            'eventos': tem_eventos,
            'mes_atual': dia.month == mes_atual.month,
            'selecionado': data_selecionada is not None and dia == data_selecionada,
        })
    
    context = {
        'orcamentos_para_concluir': orcamentos_para_concluir,
        'eventos_em_aberto_count': eventos_em_aberto(request.user.empresa).count(),
        'envio_em_andamento': status_envio_eventos(),
        'intervalo_envio_eventos': INTERVALO_ENVIO_EVENTOS,
        'agendamentos_hoje': agendamentos_hoje,
        'proximos_agendamentos': proximos_agendamentos,
        'agendamentos_concluidos': agendamentos_concluidos,
        'hoje': hoje,
        'trinta_dias': trinta_dias,
        'status_filter': status_filter,
        'data_filter': data_filter,
        'periodo_filter': periodo_filter,
        
        # Variáveis para o calendário
        'dias_calendario': dias_calendario,
        'mes_atual': mes_atual,
        'mes_anterior': mes_anterior,
        'mes_proximo': mes_proximo,
        
        # Tema da empresa
        'empresa_theme': {
            'primary': getattr(request.user.empresa, 'cor_principal', '#2563EB'),
            'secondary': getattr(request.user.empresa, 'cor_secundaria', '#64748B'),
            'accent': getattr(request.user.empresa, 'cor_destaque', '#10B981')
        }
    }
    
    return render(request, 'orcamentos/agendamentos.html', context)

@login_required
@acesso_empresa_required
def concluir_agendamento(request, orcamento_id):
    orcamento = get_object_or_404(Orcamento.objects.filter(empresa=request.user.empresa), id=orcamento_id)
    
    if request.method == 'POST':
        orcamento.status = 'concluido'
        observacoes_conclusao = request.POST.get('observacoes_conclusao', '')
        if observacoes_conclusao:
            orcamento.observacoes += f"\n\n--- CONCLUSÃO ---\n{observacoes_conclusao}"
        
        orcamento.valor_pago = orcamento.total  # Marca como totalmente pago
        if orcamento.pdf and os.path.exists(orcamento.pdf.path):
            os.remove(orcamento.pdf.path)
            orcamento.pdf = None
        
        orcamento.save()
        enviar_notificacao_whatsapp(request, orcamento.id)

        messages.success(request, f'Agendamento #{orcamento.id} concluído com sucesso!')
        return redirect('orcamentos:agendamentos')

    return render(request, 'orcamentos/concluir_agendamento.html', {'orcamento': orcamento})

@login_required
@acesso_empresa_required
def reabrir_agendamento(request, orcamento_id):
    orcamento = get_object_or_404(Orcamento.objects.filter(empresa=request.user.empresa), id=orcamento_id)
    
    if request.method == 'POST':
        orcamento.status = 'confirmado'
        orcamento.save()
        
        messages.success(request, f'Agendamento #{orcamento.id} reaberto com sucesso!')
        return redirect('orcamentos:agendamentos')

    return redirect('orcamentos:agendamentos')


@login_required
@acesso_empresa_required
@require_http_methods(["POST"])
def registrar_pagamento(request, orcamento_id):
    """
    Modal "Registrar pagamento": soma o valor recebido ao valor pago do
    orçamento, sem precisar abrir a edição completa, e (se marcado) envia o
    recibo atualizado para o cliente pelo WhatsApp com o aviso de nota fiscal.
    """
    orcamento = get_object_or_404(
        Orcamento.objects.filter(empresa=request.user.empresa).select_related('cliente'),
        id=orcamento_id
    )

    # Volta para a tela de onde o modal foi aberto
    destino = request.POST.get('next', '')
    if not url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()}):
        destino = reverse('orcamentos:detalhes_orcamento', args=[orcamento.id])

    try:
        valor = Decimal(request.POST.get('valor', '').replace(',', '.')).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        valor = Decimal('0')
    if valor <= 0:
        messages.error(request, 'Informe um valor de pagamento maior que zero.')
        return redirect(destino)

    orcamento.valor_pago = (orcamento.valor_pago or Decimal('0')) + valor
    orcamento.save(update_fields=['valor_pago'])

    # O total pode ter mais de 2 casas decimais; arredonda para não sobrar "R$ 0,00"
    saldo = Decimal(orcamento.saldo).quantize(Decimal('0.01'))
    aviso = f'Pagamento de {formatar_reais(valor)} registrado no orçamento #{orcamento.id}. '
    if saldo > 0:
        aviso += f'Saldo restante: {formatar_reais(saldo)}.'
    elif saldo < 0:
        aviso += f'Atenção: o valor pago passou do total em {formatar_reais(-saldo)}.'
    else:
        aviso += 'Orçamento quitado!'

    if request.POST.get('enviar_recibo') == '1':
        enviar_em_segundo_plano(
            orcamento.cliente.telefone,
            mensagem_pagamento_recebido(orcamento, valor),
            orcamento.id,
            somente_recibo=True,
        )
        aviso += ' O recibo está sendo enviado ao cliente pelo WhatsApp.'

    messages.success(request, aviso)
    return redirect(destino)

# Categorias de itens que saem para a festa (brinquedos, máquinas de pipoca/
# algodão doce/crepe, gerador...). Ficam de fora itens personalizados/insumos.
CATEGORIAS_EQUIPAMENTO = ['brinquedo', 'buffet', 'outro']


# Para a escala de monitores: cada brinquedo/máquina pede 1 monitor, menos os
# que ficam sem ninguém tomando conta. Os nomes são comparados sem acento e
# sem diferenciar maiúsculas, e basta o nome do item conter um destes trechos.
CATEGORIAS_COM_MONITOR = ['brinquedo', 'buffet']
ITENS_SEM_MONITOR = [
    'piscina de bolinha',
    'chute ao gol', 'chute a gol',
    'fliperama',
    'pega toupeira', 'pega topeira',
]


def _normalizar(texto):
    sem_acento = unicodedata.normalize('NFKD', texto or '').encode('ascii', 'ignore').decode()
    return ' '.join(sem_acento.lower().split())


def _monitores_do_item(item):
    """
    Quantos monitores uma unidade do item precisa. Combos (ex.: "COMBO
    PROMOCIONAL - TOBOGÃ + ALGODÃO DOCE") contam cada parte separada por "+".
    """
    if item.categoria not in CATEGORIAS_COM_MONITOR:
        return 0
    nome = _normalizar(item.nome or item.descricao)
    partes = nome.rsplit(' - ', 1)[-1].split('+') if '+' in nome else [nome]
    return sum(
        1 for parte in partes
        if not any(sem_monitor in parte for sem_monitor in ITENS_SEM_MONITOR)
    )


def _hora_fim_evento(orcamento):
    """Horário de término (início + duração em horas), ou None se não der para calcular."""
    try:
        inicio = datetime.combine(orcamento.data_evento, orcamento.hora_evento)
        return (inicio + timedelta(hours=int(orcamento.periodo_evento))).strftime('%H:%M')
    except (TypeError, ValueError):
        return None


def _montar_resumo_festas(empresa, data_inicio, data_fim, incluir_concluidos, somente_brinquedos,
                          para_monitores=False):
    """
    Busca as festas (orçamentos confirmados/reagendados, e opcionalmente os
    concluídos) do período e devolve a lista de festas com seus itens e o
    total de cada brinquedo no período, já no formato usado pela tela e pelo PDF.
    Com para_monitores=True, deixa de fora os eventos sem monitoria e as
    festas que não precisam de nenhum monitor.
    """
    status_validos = ['confirmado', 'reagendar']
    if incluir_concluidos:
        status_validos.append('concluido')

    orcamentos = (
        Orcamento.objects
        .filter(empresa=empresa, status__in=status_validos,
                data_evento__range=[data_inicio, data_fim])
        .select_related('cliente')
        .prefetch_related('itens__item')
        .order_by('data_evento', 'hora_evento')
    )
    if para_monitores:
        orcamentos = orcamentos.exclude(tipo_evento='Evento Sem Monitoria')

    festas = []
    totais = {}
    for orcamento in orcamentos:
        # Monitores contam sobre todos os itens, independente do filtro de categoria
        monitores = sum(_monitores_do_item(oi.item) * oi.quantidade for oi in orcamento.itens.all())
        if para_monitores and monitores == 0:
            continue

        itens = []
        for oi in orcamento.itens.all():
            if somente_brinquedos and oi.item.categoria not in CATEGORIAS_EQUIPAMENTO:
                continue
            nome = oi.item.nome or oi.item.descricao
            itens.append((nome, oi.quantidade))
            totais[nome] = totais.get(nome, 0) + oi.quantidade

        festas.append({
            'id': orcamento.id,
            'data': orcamento.data_evento,
            'hora': orcamento.hora_evento.strftime('%H:%M') if hasattr(orcamento.hora_evento, 'strftime') else str(orcamento.hora_evento or '-'),
            'hora_fim': _hora_fim_evento(orcamento),
            'tipo_evento': orcamento.tipo_evento,
            'cliente': orcamento.cliente.nome,
            'monitores': monitores,
            'itens': itens,
        })

    totais_ordenados = sorted(totais.items(), key=lambda t: (-t[1], t[0]))
    return festas, totais_ordenados


def _agrupar_monitores_por_dia(festas):
    """Agrupa as festas por dia com o total de monitores de cada dia (prévia da escala)."""
    dias = []
    for festa in festas:
        if not dias or dias[-1]['data'] != festa['data']:
            dias.append({'data': festa['data'], 'total': 0, 'festas': []})
        dias[-1]['festas'].append(festa)
        dias[-1]['total'] += festa['monitores']
    return dias


@login_required
@acesso_empresa_required
def resumo_festas(request):
    """
    Área para gerar um PDF simplificado das festas de um período: dia, tipo
    de evento, brinquedos e quantidades. Mostra uma prévia na tela e, com
    ?formato=pdf, baixa o PDF com os mesmos filtros.
    """
    hoje = timezone.now().date()

    def ler_data(nome, padrao):
        try:
            return datetime.strptime(request.GET.get(nome, ''), '%Y-%m-%d').date()
        except ValueError:
            return padrao

    data_inicio = ler_data('data_inicio', hoje)
    data_fim = ler_data('data_fim', hoje + timedelta(days=6))
    if data_fim < data_inicio:
        data_inicio, data_fim = data_fim, data_inicio

    # Checkboxes: na primeira visita (sem filtros) "somente brinquedos" vem marcado
    filtrado = 'data_inicio' in request.GET
    incluir_concluidos = request.GET.get('concluidos') == '1'
    somente_brinquedos = request.GET.get('brinquedos') == '1' if filtrado else True
    para_monitores = request.GET.get('monitores') == '1'

    festas, totais = _montar_resumo_festas(
        request.user.empresa, data_inicio, data_fim, incluir_concluidos, somente_brinquedos,
        para_monitores
    )
    periodo = f"{data_inicio.strftime('%d/%m/%Y')} a {data_fim.strftime('%d/%m/%Y')}"

    if request.GET.get('formato') == 'pdf':
        pdf_path = gerar_resumo_festas(festas, totais, periodo, request.user.empresa, para_monitores)
        if not pdf_path or not os.path.exists(pdf_path):
            messages.error(request, 'Não foi possível gerar o resumo de festas.')
            return redirect('orcamentos:resumo_festas')
        prefixo = "Escala_Monitores" if para_monitores else "Resumo_Festas"
        filename = f"{prefixo}_{data_inicio.strftime('%d-%m')}_a_{data_fim.strftime('%d-%m-%Y')}.pdf"
        response = FileResponse(open(pdf_path, 'rb'), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    context = {
        'festas': festas,
        'totais': totais,
        'total_unidades': sum(qtd for _, qtd in totais),
        'periodo': periodo,
        'data_inicio': data_inicio.strftime('%Y-%m-%d'),
        'data_fim': data_fim.strftime('%Y-%m-%d'),
        'incluir_concluidos': incluir_concluidos,
        'somente_brinquedos': somente_brinquedos,
        'para_monitores': para_monitores,
        'dias_monitores': _agrupar_monitores_por_dia(festas) if para_monitores else [],
        'query_pdf': request.GET.urlencode(),
    }
    return render(request, 'orcamentos/resumo_festas.html', context)


# ========================== CATÁLOGO ONLINE ==========================

# Ordem e nomes das seções do catálogo público (combos ganham seção própria)
SECOES_CATALOGO = [
    ('combo', 'Combos e Promoções'),
    ('brinquedo', 'Brinquedos'),
    ('buffet', 'Buffet e Máquinas'),
    ('decoracao', 'Decoração'),
    ('comida', 'Comidas'),
    ('servico', 'Serviços'),
    ('personalizado', 'Personalizados'),
    ('buffet_personalizado', 'Buffet Personalizado'),
    ('outro', 'Outros'),
]


def _url_catalogo(request, link):
    """
    Endereço completo do link. Se CATALOGO_URL_BASE estiver definido no .env
    (ex.: o domínio público do sistema), usa ele; senão usa o endereço por onde
    o sistema está sendo acessado agora.
    """
    caminho = reverse('catalogo:publico', args=[link.token])
    base = getattr(settings, 'CATALOGO_URL_BASE', '') or ''
    return base.rstrip('/') + caminho if base else request.build_absolute_uri(caminho)


@login_required
@acesso_empresa_required
def links_catalogo(request):
    """
    Tela interna: um link de catálogo por tipo de evento (cada tipo tem seus
    preços). Permite gerar/trocar o link (o antigo para de funcionar) e desativar.
    """
    empresa = request.user.empresa

    if request.method == 'POST':
        acao = request.POST.get('acao')
        tipo = request.POST.get('tipo_evento')
        if tipo not in TIPOS_EVENTO:
            messages.error(request, 'Tipo de evento inválido.')
        elif acao == 'gerar':
            trocou = LinkCatalogo.objects.filter(empresa=empresa, tipo_evento=tipo, ativo=True).update(ativo=False)
            LinkCatalogo.objects.create(empresa=empresa, tipo_evento=tipo)
            messages.success(
                request,
                f'Novo link gerado para "{tipo}".' + (' O link anterior parou de funcionar.' if trocou else '')
            )
        elif acao == 'desativar':
            LinkCatalogo.objects.filter(empresa=empresa, tipo_evento=tipo, ativo=True).update(ativo=False)
            messages.warning(request, f'Link de "{tipo}" desativado. Quem tiver o link não consegue mais abrir.')
        return redirect('orcamentos:links_catalogo')

    ativos = {l.tipo_evento: l for l in LinkCatalogo.objects.filter(empresa=empresa, ativo=True)}
    linhas = []
    for tipo in TIPOS_EVENTO:
        link = ativos.get(tipo)
        linhas.append({
            'tipo': tipo,
            'link': link,
            'url': _url_catalogo(request, link) if link else '',
        })
    return render(request, 'orcamentos/catalogo_links.html', {
        'linhas': linhas,
        'itens_sem_foto': _itens_catalogo(empresa).filter(Q(imagem='') | Q(imagem__isnull=True)).count(),
    })


def _link_ativo_ou_404(token):
    return get_object_or_404(LinkCatalogo.objects.select_related('empresa'), token=token, ativo=True)


def _itens_catalogo(empresa):
    return Item.objects.filter(empresa=empresa, exibir_catalogo=True, disponivel=True)


def catalogo_publico(request, token):
    """
    Catálogo aberto (sem login) enviado ao cliente. Mostra os preços do tipo
    de evento do link — e só dele; o nome do tipo não aparece na página.
    """
    link = _link_ativo_ou_404(token)
    empresa = link.empresa
    LinkCatalogo.objects.filter(pk=link.pk).update(acessos=F('acessos') + 1)

    secoes = {chave: [] for chave, _ in SECOES_CATALOGO}
    for item in _itens_catalogo(empresa).order_by('nome', 'descricao'):
        # Mesmo preço que o orçamento usaria para esse tipo de evento,
        # arredondado em reais inteiros como o total dos orçamentos
        valor = arredondar_total(valor_item_com_ajuste(item, link.tipo_evento))
        desconto = item.desconto or Decimal('0')
        valor_pix = arredondar_total(valor * (Decimal('100') - desconto) / Decimal('100')) if desconto > 0 else None
        nome = item.nome or item.descricao
        chave = 'combo' if 'combo' in _normalizar(nome) else item.categoria
        secoes.setdefault(chave, []).append({
            'id': item.id,
            'nome': nome,
            'descricao': item.descricao if item.nome and item.descricao != item.nome else '',
            'tem_foto': bool(item.imagem),
            'valor': valor,
            'valor_pix': valor_pix,
        })

    whatsapp = ''.join(c for c in (empresa.whatsapp or '') if c.isdigit())
    if whatsapp and not whatsapp.startswith('55'):
        whatsapp = '55' + whatsapp

    return render(request, 'orcamentos/catalogo_publico.html', {
        'empresa': empresa,
        'token': token,
        'tem_logo': bool(empresa.logo),
        'secoes': [(titulo, secoes[chave]) for chave, titulo in SECOES_CATALOGO if secoes.get(chave)],
        'whatsapp': whatsapp,
        'cor': empresa.cor_principal or '#2463EB',
    })


def _servir_imagem(arquivo):
    try:
        resposta = FileResponse(arquivo.open('rb'), content_type=mimetypes.guess_type(arquivo.name)[0] or 'image/jpeg')
    except (FileNotFoundError, ValueError):
        raise Http404('Imagem não encontrada')
    resposta['Cache-Control'] = 'public, max-age=86400'
    return resposta


def catalogo_foto(request, token, item_id):
    """Foto de um item do catálogo — só para itens visíveis em um link ativo."""
    link = _link_ativo_ou_404(token)
    item = get_object_or_404(_itens_catalogo(link.empresa), id=item_id)
    if not item.imagem:
        raise Http404('Item sem foto')
    return _servir_imagem(item.imagem)


def catalogo_logo(request, token):
    link = _link_ativo_ou_404(token)
    if not link.empresa.logo:
        raise Http404('Empresa sem logo')
    return _servir_imagem(link.empresa.logo)


@login_required
def foto_item(request, item_id):
    """Foto do item para as telas internas (não depende da pasta media pública)."""
    item = get_object_or_404(Item.objects.filter(empresa=request.user.empresa), id=item_id)
    if not item.imagem:
        raise Http404('Item sem foto')
    return _servir_imagem(item.imagem)
