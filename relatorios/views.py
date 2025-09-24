# relatorios/views.py
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q, F
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal
from orcamentos.models import Orcamento, OrcamentoItem, Cliente

@login_required
# comentario de varias linhas
def dashboard_relatorios(request):
    # Verificar se o usuário tem empresa
    if not hasattr(request.user, 'empresa') or not request.user.empresa:
        return render(request, 'relatorios/dashboard.html', {
            'error': 'Você não tem uma empresa associada. Não é possível gerar relatórios.'
        })
    
    # Obter o mês selecionado (se houver parâmetro na URL)
    mes_selecionado = request.GET.get('mes')
    if mes_selecionado:
        try:
            data_selecionada = datetime.strptime(mes_selecionado, '%Y-%m')
            primeiro_dia_mes = data_selecionada.replace(day=1)
            ultimo_dia_mes = (primeiro_dia_mes + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        except ValueError:
            primeiro_dia_mes = timezone.now().date().replace(day=1)
            ultimo_dia_mes = (primeiro_dia_mes + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    else:
        primeiro_dia_mes = timezone.now().date().replace(day=1)
        ultimo_dia_mes = (primeiro_dia_mes + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    
    # Calcular mês anterior e próximo para navegação
    mes_anterior = primeiro_dia_mes - timedelta(days=1)
    mes_proximo = ultimo_dia_mes + timedelta(days=1)
    
    # Filtra apenas orçamentos da empresa do usuário
    orcamentos = Orcamento.objects.filter(empresa=request.user.empresa)
    
    # Eventos que ocorreram no mês selecionado
    eventos_mes = orcamentos.filter(
        data_evento__gte=primeiro_dia_mes, 
        data_evento__lte=ultimo_dia_mes
    )
    
    # Inicializar totais
    total_mes = Decimal('0.00')
    total_pago = Decimal('0.00')
    total_confirmado = Decimal('0.00')
    total_concluido = Decimal('0.00')
    total_reagendado = Decimal('0.00')
    custo_operacional_total = Decimal('0.00')
    
    # Contadores de status
    orcamentos_confirmados = 0
    orcamentos_concluidos = 0
    orcamentos_pendentes = 0
    orcamentos_cancelados = 0
    orcamentos_reagendados = 0
    
    # Calcular totais manualmente iterando pelos orçamentos
    for orcamento in eventos_mes:
        #print(orcamento.status, orcamento.total, orcamento.valor_pago, orcamento.id)
        total_mes += orcamento.total
        if orcamento.status in ['confirmado', 'concluido', 'reagendar']:
            total_pago += orcamento.valor_pago
            custo_operacional_total += orcamento.custo_operacional
        
        #print("Total pago parcial:", total_pago, "após orcamento", orcamento.id)
        
        if orcamento.status == 'confirmado':
            orcamentos_confirmados += 1
            total_confirmado += orcamento.total
        elif orcamento.status == 'concluido':
            orcamentos_concluidos += 1
            total_concluido += orcamento.total
        elif orcamento.status == 'pendente':
            orcamentos_pendentes += 1
        elif orcamento.status == 'cancelado':
            orcamentos_cancelados += 1
        elif orcamento.status == 'reagendar':
            total_reagendado += orcamento.total
            orcamentos_reagendados += 1
    #print("Total mês:", total_mes)
    #print("Total pago:", total_pago)
    #print("Total confirmado:", total_confirmado)
    #print("Total concluído:", total_concluido)
    #print("Total reagendado:", total_reagendado)
    
    total_orcamentos = eventos_mes.count()
    
    # Calcular valores do mês anterior para comparação
    mes_anterior_inicio = (primeiro_dia_mes - timedelta(days=1)).replace(day=1)
    mes_anterior_fim = primeiro_dia_mes - timedelta(days=1)
    
    eventos_mes_anterior = orcamentos.filter(
        data_evento__gte=mes_anterior_inicio,
        data_evento__lte=mes_anterior_fim
    )
    
    # Calcular totais do mês anterior manualmente
    total_mes_anterior = Decimal('0.00')
    total_pago_anterior = Decimal('0.00')
    total_confirmado_anterior = Decimal('0.00')
    total_orcamentos_anterior = eventos_mes_anterior.count()
    custo_operacional_total_anterior = Decimal('0.00')
    
    for orcamento in eventos_mes_anterior:
        if orcamento.status in ['confirmado', 'concluido', 'reagendar']:
            total_mes_anterior += orcamento.total
            custo_operacional_total_anterior += orcamento.custo_operacional
        
        total_pago_anterior += orcamento.valor_pago
        
        if orcamento.status == 'confirmado':
            total_confirmado_anterior += orcamento.total
    
    # Calcular comparações percentuais
    def calcular_comparacao(atual, anterior):
        if anterior == 0:
            return 100 if atual > 0 else 0
        return ((atual - anterior) / anterior) * 100
    
    comparacao_receita = calcular_comparacao(float(total_mes), float(total_mes_anterior))
    comparacao_pago = calcular_comparacao(float(total_pago), float(total_pago_anterior))
    comparacao_confirmado = calcular_comparacao(float(total_confirmado + total_concluido), float(total_confirmado_anterior))
    comparacao_orcamentos = calcular_comparacao(total_orcamentos, total_orcamentos_anterior)
    comparacao_custo_operacional = calcular_comparacao(float(custo_operacional_total), float(custo_operacional_total_anterior))
    
    lucro_estimado_anterior = total_confirmado_anterior - custo_operacional_total_anterior
    lucro_estimado_atual = (total_confirmado + total_concluido + total_reagendado) - custo_operacional_total
    comparacao_lucro_estimado = calcular_comparacao(float(lucro_estimado_atual), float(lucro_estimado_anterior))
    # Calcular evolução mensal (últimos 6 meses)
    meses = []
    valores_mensais = []
    
    for i in range(5, -1, -1):  # Últimos 6 meses (do mais antigo ao mais recente)
        mes_data = primeiro_dia_mes - timedelta(days=30*i)
        mes_primeiro_dia = mes_data.replace(day=1)
        mes_ultimo_dia = (mes_primeiro_dia + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        
        eventos_mes_historico = orcamentos.filter(
            data_evento__gte=mes_primeiro_dia,
            data_evento__lte=mes_ultimo_dia
        )
        
        # Calcular total do mês histórico manualmente
        total_mes_historico = Decimal('0.00')
        for orcamento in eventos_mes_historico:
            if orcamento.status in ['confirmado', 'concluido', 'reagendar']:
                total_mes_historico += orcamento.total
        
        meses.append(mes_data.strftime('%b/%Y'))
        valores_mensais.append(float(total_mes_historico))
    
    # Novos clientes (últimos 30 dias)
    novos_clientes = Cliente.objects.filter(
        empresa=request.user.empresa,
        data_cadastro__gte=timezone.now() - timedelta(days=30)
    ).count()
    
    # Taxa de conversão (confirmados + concluídos / total)
    if total_orcamentos > 0:
        taxa_conversao = ((orcamentos_confirmados + orcamentos_concluidos) / total_orcamentos) * 100
    else:
        taxa_conversao = 0
    
    context = {
        # Métricas principais
        'total_mes': total_mes,
        'total_orcamentos': total_orcamentos,
        'total_pago': total_pago,
        'total_confirmado': total_confirmado + total_concluido + total_reagendado,
        'custo_operacional_total': custo_operacional_total,
        'lucro_estimado': lucro_estimado_atual,
        
        # Comparações
        'comparacao_receita': comparacao_receita,
        'comparacao_pago': comparacao_pago,
        'comparacao_confirmado': comparacao_confirmado,
        'comparacao_orcamentos': comparacao_orcamentos,
        'comparacao_custo': comparacao_custo_operacional,
        'comparacao_lucro': comparacao_lucro_estimado,
        
        # Contagens por status
        'orcamentos_confirmados': orcamentos_confirmados,
        'orcamentos_concluidos': orcamentos_concluidos,
        'orcamentos_pendentes': orcamentos_pendentes,
        'orcamentos_cancelados': orcamentos_cancelados,
        'reagendados': orcamentos_reagendados,
        
        # Métricas secundárias
        'taxa_conversao': round(taxa_conversao, 1),
        'novos_clientes': novos_clientes,
        
        # Gráficos
        'meses': meses,
        'valores_mensais': valores_mensais,
        
        # Navegação de meses
        'mes_atual': primeiro_dia_mes,
        'mes_anterior': mes_anterior,
        'mes_proximo': mes_proximo,
        
        # Tema da empresa
        'empresa_theme': {
            'primary': getattr(request.user.empresa, 'cor_principal', '#2563EB'),
            'secondary': getattr(request.user.empresa, 'cor_secundaria', '#64748B'),
            'accent': getattr(request.user.empresa, 'cor_destaque', '#10B981')
        }
    }
    
    return render(request, 'relatorios/dashboard.html', context)