from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, JsonResponse, FileResponse
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Count, Max
from django.utils import timezone
from django.conf import settings
from datetime import timedelta, datetime
import os
import json

from .models import Cliente, Item, Orcamento, OrcamentoItem
from accounts.models import Empresa, Usuario
from .forms import OrcamentoForm, ClienteForm, ItemForm, OrcamentoSearchForm
from .utils import gerar_arquivos

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
    search_query = request.GET.get('q', '')
    page_number = request.GET.get('page', 1)
    
    # Base query - apenas orçamentos da empresa do usuário
    orcamentos = Orcamento.objects.filter(empresa=request.user.empresa).select_related("cliente").prefetch_related("itens")
    
    # Aplicar filtro de status
    if status_filter != 'all':
        orcamentos = orcamentos.filter(status=status_filter)
    
    # Aplicar busca
    if search_query:
        orcamentos = orcamentos.filter(
            Q(cliente__nome__icontains=search_query) |
            Q(cliente__telefone__icontains=search_query) |
            Q(observacoes__icontains=search_query) |
            Q(itens__item__descricao__icontains=search_query)
        ).distinct()
    
    # Aplicar ordenação
    if sort_by == 'recentes':
        orcamentos = orcamentos.order_by('-data_criacao')
    elif sort_by == 'antigos':
        orcamentos = orcamentos.order_by('data_criacao')
    elif sort_by == 'valor-maior':
        orcamentos = orcamentos.annotate(
            total_calculado=Sum('itens__quantidade') * Sum('itens__item__valor_unitario')
        ).order_by('-total_calculado')
    elif sort_by == 'valor-menor':
        orcamentos = orcamentos.annotate(
            total_calculado=Sum('itens__quantidade') * Sum('itens__item__valor_unitario')
        ).order_by('total_calculado')
    
    # Paginação
    paginator = Paginator(orcamentos, 10)
    page_obj = paginator.get_page(page_number)
    
    # Calcular estatísticas apenas para a empresa do usuário
    total_orcamentos = orcamentos.count()
    orcamentos_confirmados = orcamentos.filter(status='confirmado').count()
    orcamentos_pendentes = orcamentos.filter(status='pendente').count()
    
    # Calcular valor total
    valor_total = 0
    for orcamento in orcamentos:
        valor_total += orcamento.total
        
    valor_total = float(f"{valor_total:.2f}")
    valor_total = "{:,.2f}".format(valor_total).replace(",", "X").replace(".", ",").replace("X", ".")
    
    context = {
        'orcamentos': page_obj,
        'page_obj': page_obj,
        'form': form,
        'status_filter': status_filter,
        'sort_by': sort_by,
        'search_query': search_query,
        'stats': {
            'total': total_orcamentos,
            'confirmados': orcamentos_confirmados,
            'pendentes': orcamentos_pendentes,
            'valor_total': valor_total,
        }
    }
    
    return render(request, "orcamentos/lista.html", context)

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
        valor_item = orcamento_item.quantidade * orcamento_item.item.valor_unitario
        desconto_item = valor_item * (orcamento_item.item.desconto / 100) if orcamento_item.item.desconto else 0
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
                            valor=item.valor_unitario,
                            desconto=item.desconto                                      
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
    
    return render(request, "orcamentos/novo.html", {
        "clientes": clientes,
        "itens": itens,
        "itens_json": itens_json,
        "clientes_json": clientes_json,
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
                        valor=item.valor_unitario,
                        desconto=item.desconto
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
    
    # Preparar dados dos itens atuais
    itens_selecionados = {str(item.item.id): item.quantidade for item in orcamento.itens.all()}
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
                            valor=item.valor_unitario,
                            desconto=item.desconto
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
            filename = f'Orcamento_{orcamento.cliente.nome}.pdf'
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
        
        # Atualiza o orçamento com os novos arquivos
        orcamento.pdf = pdf
        orcamento.png = png
        orcamento.save()
        
        # Serve o arquivo recém-criado
        file_path = orcamento.pdf.path
        filename = f'Orcamento_{orcamento.cliente.nome}.pdf'
        
        response = FileResponse(open(file_path, 'rb'), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
        
    except Exception as e:
        #print(f"Erro ao gerar PDF: {str(e)}")
        messages.error(request, 'Erro ao gerar o arquivo PDF.')
        return redirect("orcamentos:detalhes_orcamento", orcamento_id=orcamento.id)
    
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
        item.faturamento = (item.uso_count * item.valor_unitario) - ((item.uso_count * item.valor_unitario) * (35 / 100) if item.desconto else 0)
    
    return render(request, "orcamentos/itensLista.html", {"itens": itens})

@login_required
def novo_item(request):
    if request.method == "POST":
        form = ItemForm(request.POST)
        if form.is_valid():
            item = form.save(commit=False)
            item.empresa = request.user.empresa  # Associa à empresa do usuário
            item.save()
            messages.success(request, 'Item cadastrado com sucesso!')
            return redirect("orcamentos:lista_itens")
    else:
        form = ItemForm()
    
    return render(request, "orcamentos/itens.html", {"form": form})

@login_required
def editar_item(request, item_id):
    item = get_object_or_404(Item.objects.filter(empresa=request.user.empresa), id=item_id)
    
    if request.method == "POST":
        form = ItemForm(request.POST, instance=item)
        if form.is_valid():
            form.save()
            messages.success(request, 'Item atualizado com sucesso!')
            return redirect("orcamentos:lista_itens")
    else:
        form = ItemForm(instance=item)
    
    return render(request, "orcamentos/itens.html", {"form": form, "item": item})

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
    else:
        mes_atual = hoje.replace(day=1)
    
    # Calcular mês anterior e próximo para navegação
    mes_anterior = (mes_atual - timedelta(days=1)).replace(day=1)
    mes_proximo = (mes_atual + timedelta(days=32)).replace(day=1)
    
    # Apenas orçamentos da empresa do usuário
    orcamentos = Orcamento.objects.filter(
        empresa=request.user.empresa, 
        status__in=['confirmado', 'concluido', 'reagendado']  # Excluir pendentes e cancelados
    )
    
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
    ).order_by('-data_evento')
    
    # Gerar calendário para o mês atual
    primeiro_dia_semana = (mes_atual - timedelta(days=mes_atual.weekday()))
    
    dias_calendario = []
    for i in range(42):  # 6 semanas
        dia = primeiro_dia_semana + timedelta(days=i)
        tem_eventos = Orcamento.objects.filter(
            empresa=request.user.empresa,
            data_evento=dia,
            status__in=['confirmado', 'pendente']
        ).exists()
        
        dias_calendario.append({
            'dia': dia.day,
            'data': dia.strftime('%Y-%m-%d'),
            'hoje': dia == hoje,
            'eventos': tem_eventos,
            'mes_atual': dia.month == mes_atual.month
        })
    
    context = {
        'orcamentos_para_concluir': orcamentos_para_concluir,
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