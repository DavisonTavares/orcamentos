import os
from datetime import datetime, time
from typing import Dict, Any, Tuple, List

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib.colors import HexColor
from django.conf import settings
from decimal import Decimal
from pdf2image import convert_from_path
import img2pdf
from PIL import Image, ImageDraw, ImageFont 
import tempfile 





BRAND = {
    "empresa": "Mundo Kids",
    "slogan": "Diversão para sua festa!",
    "segmento": "Locação de brinquedos para festas e eventos",
    "cidade": "Cajazeiras-PB e região",
    "instagram": "@mundokidscz",
    "whatsapp": "+55 83 9 8149-3235",
}

COLORS = {
    "primary": "#2463EB",
    "secondary": "#4ECDC4",
    "accent": "#FF6B6B",
    "light": "#F8FAFC",
    "dark": "#1E293B",
    "muted": "#64748B",
    "success": "#10B981",
    "gradient_start": "#667EEA",
    "gradient_end": "#764BA2"
}

LOGO_PATH = os.environ.get("MUNDOKIDS_LOGO", "MUNDOKIDS_LOGO.png")
SAIDAS_DIR = os.path.join(os.getcwd(), "saidas")

def brl(value: float) -> str:
    value = round(value, 2)
    return f"R$ {value:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

def calcular_totais(itens: list, desconto_geral: float = 0.0) -> Dict[str, float]:
    subtotal = 0.0
    total_descontos_itens = 0.0
    
    for item in itens:
        qty = float(item.get("quantidade", 1))
        vu = float(item.get("valor_unitario", 0))
        desc_pct = float(item.get("desconto", 0))
        valor_bruto = qty * vu
        desc_val = valor_bruto * (desc_pct / 100.0)
        total_descontos_itens += desc_val
        subtotal += (valor_bruto - desc_val)
    
    desconto_geral_val = subtotal * (desconto_geral / 100.0)
    total = subtotal - desconto_geral_val
    
    return {
        "subtotal": subtotal,
        "descontos_itens": total_descontos_itens,
        "desconto_geral_val": desconto_geral_val,
        "total": total,
    }

def wrap_text(text: str, max_width: float, font: str, font_size: int, canvas) -> List[str]:
    """Quebra texto em múltiplas linhas baseado na largura máxima"""
    lines = []
    words = text.split()
    current_line = []
    
    for word in words:
        test_line = ' '.join(current_line + [word])
        width = canvas.stringWidth(test_line, font, font_size)
        if width <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(' '.join(current_line))
            current_line = [word]
    
    if current_line:
        lines.append(' '.join(current_line))
    
    return lines

def gerar_pdf(dados: Dict[str, Any], saida_pdf: str) -> str:
    c = canvas.Canvas(saida_pdf, pagesize=A4)
    W, H = A4
    
    # Configurar margens
    margin_left = 15 * mm
    margin_right = 15 * mm
    content_width = W - margin_left - margin_right

    # Header com gradiente
    c.setFillColor(HexColor(COLORS["primary"]))
    c.rect(0, H - 70, W, 70, stroke=0, fill=1)
    
    
    # Informações da empresa
    #c.setFillColor(HexColor("#E00E0E"))
    #c.setFont("Helvetica-Bold", 18)
    #c.drawString(margin_left + 30 * mm, H - 45, BRAND["empresa"])
    #c.setFont("Helvetica", 9)
    #c.drawString(margin_left + 30 * mm, H - 58, BRAND["segmento"])
    #c.drawString(margin_left + 30 * mm, H - 68, BRAND["cidade"])

    # Caixa de título
    c.setFillColor(HexColor(COLORS["light"]))
    c.roundRect(margin_left, H - 90, content_width, 20 * mm, 4 * mm, stroke=0, fill=1)
    
    c.setFillColor(HexColor(COLORS["primary"]))
    c.setFont("Helvetica-Bold", 16)
    c.drawString(margin_left + 5 * mm, H - 75, "ORÇAMENTO")
    
    hoje = datetime.now().strftime("%d/%m/%Y")
    c.setFont("Helvetica", 8)
    c.setFillColor(HexColor(COLORS["muted"]))
    c.drawRightString(W - margin_right - 5 * mm, H - 75, f"Data: {hoje}")
    c.drawRightString(W - margin_right - 5 * mm, H - 85, "Validade: 7 dias")

    # Logo
    if LOGO_PATH and os.path.exists(LOGO_PATH):
        try:
            img = ImageReader(LOGO_PATH)
            logo_size = 40 * mm
            # Manter proporção e no meio da pagina
            iw, ih = img.getSize()
            aspect = ih / float(iw)
            c.drawImage(img, (W/2) - (logo_size / 2), H - 70, width=logo_size, height=logo_size * aspect, mask='auto') 
        except Exception:
            pass


    # Dados do cliente
    y_position = H - 105
    cliente = dados.get("cliente", {})
    evento = dados.get("evento", {})
    endereco = evento.get("endereco", "-")
    partes = [p.strip() for p in endereco.split(",")]
    c.setFillColor(HexColor(COLORS["dark"]))
    c.setFont("Helvetica-Bold", 10)
    c.drawString(margin_left, y_position, "CLIENTE")
    #do outro lado a informação do endereço
    c.drawString(W - margin_right - 60 * mm, y_position, "ENDEREÇO")
    y_position -= 12
    
    c.setFont("Helvetica", 9)
    c.drawString(margin_left, y_position, f"Nome: {cliente.get('nome', '-')} - {cliente.get('telefone', '-')}")
    #endereço com quebra rua, número, bairro, cidade - estado, cep
    #quebrar linha se for preciso
    # More readable variable names and structure
    endereco = partes[0] if len(partes) > 0 else '-'
    max_width = 60 * mm
    x_position = W - margin_right - max_width
    font_name = "Helvetica"
    font_size = 9
    line_height = 10

    if len(endereco) > 40:
        endereco_lines = wrap_text(endereco, max_width, font_name, font_size, c)
        for line in endereco_lines:
            c.drawString(x_position, y_position, f" {line}")
            y_position -= line_height
    else:
        c.drawString(x_position, y_position, f" {endereco}")
        y_position -= line_height
    if len(partes) > 1:
        c.drawString(W - margin_right - 60 * mm, y_position, f" {partes[1]}, {partes[2] if len(partes) > 2 else '-'}")
        y_position -= 10
    if len(partes) > 3:
        c.drawString(W - margin_right - 60 * mm, y_position, f"{partes[3]}, {partes[4] if len(partes) > 4 else '-'}")
        y_position -= 10

    c.drawString(W - margin_right - 60 * mm, y_position, f"data do evento: {evento.get('data', '-')} às {evento.get('hora_inicio', '-')}")
    y_position -= 25
    
    

    # Cabeçalho da tabela
    col_widths = [content_width * 0.60, content_width * 0.10, content_width * 0.15, content_width * 0.15]
    col_positions = [margin_left]
    for i in range(1, 5):
        col_positions.append(col_positions[i-1] + col_widths[i-1])
    
    c.setFillColor(HexColor(COLORS["primary"]))
    c.roundRect(margin_left, y_position - 8, content_width, 10 * mm, 3 * mm, stroke=0, fill=1)
    
    c.setFillColor(HexColor("#FFFFFF"))
    c.setFont("Helvetica-Bold", 8)
    headers = ["DESCRIÇÃO", "QTD", "VALOR UNIT.", "TOTAL"]
    for i, header in enumerate(headers):
        if i == 0:  # Descrição alinhada à esquerda
            c.drawString(col_positions[i] + 3 * mm, y_position + 3, header)
        else:  # Demais colunas alinhadas ao centro
            text_width = c.stringWidth(header, "Helvetica-Bold", 8)
            c.drawString(col_positions[i] + (col_widths[i] - text_width) / 2, y_position + 3, header)
    
    y_position -= 20

    # Itens do orçamento
    itens = dados.get("brinquedos", [])
    line_height = 7 * mm
    
    for i, item in enumerate(itens):
        if y_position < 100:  # Nova página se necessário
            c.showPage()
            y_position = H - 40
            # Recriar cabeçalho da tabela na nova página
            c.setFillColor(HexColor(COLORS["primary"]))
            c.roundRect(margin_left, y_position - 8, content_width, 10 * mm, 3 * mm, stroke=0, fill=1)
            c.setFillColor(HexColor("#FFFFFF"))
            for j, header in enumerate(headers):
                if j == 0:
                    c.drawString(col_positions[j] + 3 * mm, y_position - 4, header)
                else:
                    text_width = c.stringWidth(header, "Helvetica-Bold", 8)
                    c.drawString(col_positions[j] + (col_widths[j] - text_width) / 2, y_position - 4, header)
            y_position -= 12
        
        # Fundo alternado para linhas
        if i % 2 == 0:
            c.setFillColor(HexColor(COLORS["light"]))
            c.roundRect(margin_left, y_position - line_height + 2, content_width, line_height, 2 * mm, stroke=0, fill=1)
        
        c.setFillColor(HexColor(COLORS["dark"]))
        c.setFont("Helvetica", 8)
        
        descricao = str(item.get("descricao", "-"))
        quantidade = float(item.get("quantidade", 1))
        valor_unitario = float(item.get("valor_unitario", 0))
        desconto = float(item.get("desconto", 0))
        total_item = quantidade * valor_unitario * (1 - desconto / 100.0)
        
        # Descrição com quebra de linha se necessário
        desc_lines = wrap_text(descricao, col_widths[0] - 6 * mm, "Helvetica", 8, c)
        
        # Calcular a altura total desta linha (máximo entre altura padrão e altura da descrição)
        altura_linha = max(line_height, len(desc_lines) * 3 * mm)
        
        # Calcular a posição Y centralizada para esta linha
        y_centro = y_position - (altura_linha / 2) + (3 * mm)  # Ajuste para centralizar verticalmente
        
        # Desenhar descrição (pode ter múltiplas linhas)
        for j, line in enumerate(desc_lines):
            c.drawString(col_positions[0] + 3 * mm, y_centro - (j * 3 * mm), line)
        
        # Demais colunas - centralizadas verticalmente
        c.drawCentredString(col_positions[1] + col_widths[1] / 2, y_centro, f"{int(quantidade) if quantidade.is_integer() else quantidade}")
        c.drawCentredString(col_positions[2] + col_widths[2] / 2, y_centro, brl(valor_unitario))
        #c.drawCentredString(col_positions[3] + col_widths[3] / 2, y_centro, f"{desconto:.0f}%")
        c.drawCentredString(col_positions[3] + col_widths[3] / 2, y_centro, brl(total_item))
        
        y_position -= altura_linha
        
    # Totais
    y_position -= 10
    totais = calcular_totais(itens, dados.get("desconto_geral", 0))
    
    c.setFillColor(HexColor(COLORS["light"]))
    c.roundRect(margin_left + content_width * 0.5, y_position - 60, content_width * 0.5, 55, 4 * mm, stroke=0, fill=1)
    
    c.setFillColor(HexColor(COLORS["dark"]))
    c.setFont("Helvetica", 9)
    
    # Subtotal
    c.drawString(margin_left + content_width * 0.5 + 5 * mm, y_position - 15, "Subtotal:")
    c.drawRightString(margin_left + content_width - 5 * mm, y_position - 15, brl(totais["subtotal"]))
    
    # Desconto itens
    c.drawString(margin_left + content_width * 0.5 + 5 * mm, y_position - 25, "Desc. itens:")
    c.drawRightString(margin_left + content_width - 5 * mm, y_position - 25, f"- {brl(totais['descontos_itens'])}")
    
    # Valor adicional
    valor_adicional = round(float(dados.get("valor_adicional", 0)), 2)
    c.drawString(margin_left + content_width * 0.5 + 5 * mm, y_position - 35, f"Valor adicional:")
    c.drawRightString(margin_left + content_width - 5 * mm, y_position - 35, f"+ {brl(valor_adicional)}")
    
    # Desconto geral
    desconto_geral = round(float(dados.get("desconto_geral", 0)), 0)
    c.drawString(margin_left + content_width * 0.5 + 5 * mm, y_position - 45, f"Desc. geral ({desconto_geral}%):")
    c.drawRightString(margin_left + content_width - 5 * mm, y_position - 45, f"- {brl(totais['desconto_geral_val'])}")
    
    # Linha separadora
    c.setStrokeColor(HexColor(COLORS["muted"]))
    c.setLineWidth(0.5)
    c.line(margin_left + content_width * 0.5 + 5 * mm, y_position - 50, margin_left + content_width - 5 * mm, y_position - 50)
    
    # Total
    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(HexColor(COLORS["success"]))
    c.drawString(margin_left + content_width * 0.5 + 5 * mm, y_position - 70, "TOTAL:")
    c.drawRightString(margin_left + content_width - 5 * mm, y_position - 70, brl(totais["total"] + valor_adicional))

    # Observações
    obs_y = y_position
    obs = dados.get("observacoes") or "• Tempo padrão de operação: 3 horas com monitor incluso\n• Valores sujeitos a disponibilidade\n• Montagem e desmontagem inclusas"
    
    c.setFillColor(HexColor(COLORS["muted"]))
    c.setFont("Helvetica-Bold", 9)
    c.drawString(margin_left, obs_y, "OBSERVAÇÕES:")
    obs_y -= 15
    
    c.setFillColor(HexColor(COLORS["dark"]))
    c.setFont("Helvetica", 8)
    
    for line in obs.split('\n'):
        if obs_y < 30:  # Nova página se necessário
            c.showPage()
            obs_y = H - 40
        c.drawString(margin_left + 5 * mm, obs_y, line)
        obs_y -= 4 * mm

    # Rodapé
    c.setFillColor(HexColor(COLORS["muted"]))
    c.setFont("Helvetica", 7)
    
    rodape_lines = []
    if BRAND.get("instagram"):
        rodape_lines.append(f"📷 {BRAND['instagram']}")
    if BRAND.get("whatsapp"):
        rodape_lines.append(f"💬 {BRAND['whatsapp']}")
    
    footer_text = "   |   ".join(rodape_lines)
    footer_width = c.stringWidth(footer_text, "Helvetica", 7)
    c.drawString((W - footer_width) / 2, 15, footer_text)
    
    c.drawCentredString(W / 2, 5, f"{BRAND['empresa']} • {BRAND['cidade']}")

    c.save()
    return saida_pdf

def gerar_confirmacao_agendamento(dados: Dict[str, Any], saida_pdf: str) -> str:
    """
    Gera PDF de confirmação de agendamento com layout similar ao orçamento
    """
    c = canvas.Canvas(saida_pdf, pagesize=A4)
    W, H = A4
    
    # Configurar margens
    margin_left = 15 * mm
    margin_right = 15 * mm
    content_width = W - margin_left - margin_right

    # Header com gradiente
    c.setFillColor(HexColor(COLORS["primary"]))
    c.rect(0, H - 70, W, 70, stroke=0, fill=1)

    # Caixa de título
    c.setFillColor(HexColor(COLORS["light"]))
    c.roundRect(margin_left, H - 100, content_width, 20 * mm, 4 * mm, stroke=0, fill=1)
    
    c.setFillColor(HexColor(COLORS["primary"]))
    c.setFont("Helvetica-Bold", 14)
    c.drawString(margin_left + 5 * mm, H - 85, "CONFIRMAÇÃO DE AGENDAMENTO")
    
    hoje = datetime.now().strftime("%d/%m/%Y")
    c.setFont("Helvetica", 8)
    c.setFillColor(HexColor(COLORS["muted"]))
    c.drawRightString(W - margin_right - 5 * mm, H - 85, f"Data de emissão: {dados.get('data_criacao', hoje)}")
    c.drawRightString(W - margin_right - 5 * mm, H - 95, "Documento de confirmação")

    # Logo
    if LOGO_PATH and os.path.exists(LOGO_PATH):
        try:
            img = ImageReader(LOGO_PATH)
            logo_size = 40 * mm
            iw, ih = img.getSize()
            aspect = ih / float(iw)
            c.drawImage(img, (W/2) - (logo_size / 2), H - 70, width=logo_size, height=logo_size * aspect, mask='auto') 
        except Exception:
            pass

    # Dados do cliente
    y_position = H - 115
    cliente = dados.get("cliente", {})
    evento = dados.get("evento", {})
    
    c.setFillColor(HexColor(COLORS["dark"]))
    c.setFont("Helvetica-Bold", 10)
    c.drawString(margin_left, y_position, "DADOS DO CLIENTE")
    y_position -= 12
    
    c.setFont("Helvetica", 9)
    c.drawString(margin_left, y_position, f"👤 Nome: {cliente.get('nome', '-')}")
    y_position -= 10
    c.drawString(margin_left, y_position, f"📞 Telefone: {cliente.get('telefone', '-')}")
    y_position -= 20

    # Dados do evento
    c.setFillColor(HexColor(COLORS["dark"]))
    c.setFont("Helvetica-Bold", 10)
    c.drawString(margin_left, y_position, "DADOS DO EVENTO")
    y_position -= 12
    
    c.setFont("Helvetica", 9)
    c.drawString(margin_left, y_position, f"🎉 Tipo: {evento.get('tipo', 'Festa')}")
    y_position -= 10
    c.drawString(margin_left, y_position, f"🏠 Endereço: {evento.get('endereco', '-')}")
    y_position -= 10
    c.drawString(margin_left, y_position, f"📅 Data: {evento.get('data', '-')}")
    y_position -= 10
    
    # Horários
    hora_inicio = evento.get('hora_inicio', '--:--')
    hora_montagem = evento.get('hora_montagem', '--:--')
    hora_desmontagem = evento.get('hora_desmontagem', '--:--')
    
    c.drawString(margin_left, y_position, f"⏰ Horário do evento: {hora_inicio}")
    y_position -= 10
    c.drawString(margin_left, y_position, f"🛠️  Montagem prevista: {hora_montagem} (1h antes do início)")
    y_position -= 10
    c.drawString(margin_left, y_position, f"📦 Desmontagem prevista: {hora_desmontagem}")
    y_position -= 20

    # Brinquedos contratados
    c.setFillColor(HexColor(COLORS["dark"]))
    c.setFont("Helvetica-Bold", 10)
    c.drawString(margin_left, y_position, "BRINQUEDOS CONTRATADOS")
    y_position -= 12

    # Cabeçalho da tabela de brinquedos
    col_widths = [content_width * 0.70, content_width * 0.15, content_width * 0.15]
    col_positions = [margin_left]
    for i in range(1, 4):
        col_positions.append(col_positions[i-1] + col_widths[i-1])
    
    c.setFillColor(HexColor(COLORS["primary"]))
    c.roundRect(margin_left, y_position - 8, content_width, 10 * mm, 3 * mm, stroke=0, fill=1)
    
    c.setFillColor(HexColor("#FFFFFF"))
    c.setFont("Helvetica-Bold", 8)
    headers = ["BRINQUEDO", "QTD", "PERÍODO"]
    for i, header in enumerate(headers):
        if i == 0:  # Descrição alinhada à esquerda
            c.drawString(col_positions[i] + 3 * mm, y_position + 3, header)
        else:  # Demais colunas alinhadas ao centro
            text_width = c.stringWidth(header, "Helvetica-Bold", 8)
            c.drawString(col_positions[i] + (col_widths[i] - text_width) / 2, y_position + 3, header)
    
    y_position -= 20

    # Itens do agendamento
    brinquedos = dados.get("brinquedos", [])
    line_height = 7 * mm
    
    for i, brinquedo in enumerate(brinquedos):
        if y_position < 100:  # Nova página se necessário
            c.showPage()
            y_position = H - 40
            # Recriar cabeçalho da tabela na nova página
            c.setFillColor(HexColor(COLORS["primary"]))
            c.roundRect(margin_left, y_position - 8, content_width, 10 * mm, 3 * mm, stroke=0, fill=1)
            c.setFillColor(HexColor("#FFFFFF"))
            for j, header in enumerate(headers):
                if j == 0:
                    c.drawString(col_positions[j] + 3 * mm, y_position - 4, header)
                else:
                    text_width = c.stringWidth(header, "Helvetica-Bold", 8)
                    c.drawString(col_positions[j] + (col_widths[j] - text_width) / 2, y_position - 4, header)
            y_position -= 12
        
        # Fundo alternado para linhas
        if i % 2 == 0:
            c.setFillColor(HexColor(COLORS["light"]))
            c.roundRect(margin_left, y_position - line_height + 2, content_width, line_height, 2 * mm, stroke=0, fill=1)
        
        c.setFillColor(HexColor(COLORS["dark"]))
        c.setFont("Helvetica", 8)
        
        descricao = str(brinquedo.get("descricao", "-"))
        quantidade = brinquedo.get("quantidade", 1)
        periodo = brinquedo.get("periodo", "3 horas")
        
        # Descrição com quebra de linha se necessário
        desc_lines = wrap_text(descricao, col_widths[0] - 6 * mm, "Helvetica", 8, c)
        
        # Calcular a altura total desta linha
        altura_linha = max(line_height, len(desc_lines) * 3 * mm)
        y_centro = y_position - (altura_linha / 2) + (3 * mm)
        
        # Desenhar descrição
        for j, line in enumerate(desc_lines):
            c.drawString(col_positions[0] + 3 * mm, y_centro - (j * 3 * mm), line)
        
        # Demais colunas
        c.drawCentredString(col_positions[1] + col_widths[1] / 2, y_centro, f"{quantidade}")
        c.drawCentredString(col_positions[2] + col_widths[2] / 2, y_centro, periodo)
        
        y_position -= altura_linha

    # Informações importantes
    y_position -= 15
    c.setFillColor(HexColor(COLORS["primary"]))
    c.setFont("Helvetica-Bold", 10)
    c.drawString(margin_left, y_position, "INFORMAÇÕES IMPORTANTES")
    y_position -= 12
    
    c.setFillColor(HexColor(COLORS["dark"]))
    c.setFont("Helvetica", 8)
    
    informacoes = [
        "✓ Espaço necessário: área plana e limpa com a dimensão dos brinquedos",
        "✓ Acesso para veículos: caso for necessário, informe previamente",                
        "✓ Em caso de chuva durante o evento, os brinquedos infláveis e eletrônicos deverão ser realocados para área coberta ou, se não for possível, serão desinflados/desmontados para evitar danos",
        "✓ Pagamento: 50% no agendamento, 50% na entrega dos brinquedos",
        "✓ Cancelamentos: não há reembolso, apenas remarcação conforme disponibilidade de agenda.",
        "✓ Horário de montagem: 1 hora antes do início do evento",
        "✓ Nossos brinquedos incluem extensão de 10m. Para distâncias maiores, favor informar antecipadamente para nos organizarmos."        
    ]
    
    for info in informacoes:
        if y_position < 50:  # Nova página se necessário
            c.showPage()
            y_position = H - 40
        c.drawString(margin_left + 5 * mm, y_position, info)
        y_position -= 12
        
    # Informações do pagamento
    y_position -= 10
    c.setFillColor(HexColor(COLORS["primary"]))
    c.setFont("Helvetica-Bold", 10)
    c.drawString(margin_left, y_position, "INFORMAÇÕES DE PAGAMENTO")
    y_position -= 12
    c.setFillColor(HexColor(COLORS["dark"]))
    c.setFont("Helvetica", 9)
    c.drawString(margin_left, y_position, f"Valor total: {dados.get('valor_total', 'Valor não informado')}")
    y_position -= 10
    c.drawString(margin_left, y_position, f"Valor pago (sinal): {dados.get('valor_pago', 'Valor não informado')}")
    y_position -= 10

    # Contato de emergência
    y_position -= 10
    c.setFillColor(HexColor(COLORS["primary"]))
    c.setFont("Helvetica-Bold", 10)
    c.drawString(margin_left, y_position, "CONTATO EM CASO DE DÚVIDAS")
    y_position -= 12
    
    c.setFillColor(HexColor(COLORS["dark"]))
    c.setFont("Helvetica", 9)
    c.drawString(margin_left, y_position, f"📞 {BRAND.get('whatsapp', 'Contato não informado')}")
    y_position -= 10
    if BRAND.get("instagram"):
        c.drawString(margin_left, y_position, f"📷 {BRAND['instagram']}")

    # Rodapé
    c.setFillColor(HexColor(COLORS["muted"]))
    c.setFont("Helvetica", 7)
    
    rodape_lines = []
    if BRAND.get("instagram"):
        rodape_lines.append(f"📷 {BRAND['instagram']}")
    if BRAND.get("whatsapp"):
        rodape_lines.append(f"💬 {BRAND['whatsapp']}")
    
    footer_text = "   |   ".join(rodape_lines)
    footer_width = c.stringWidth(footer_text, "Helvetica", 7)
    c.drawString((W - footer_width) / 2, 15, footer_text)
    
    c.drawCentredString(W / 2, 5, f"{BRAND['empresa']} • {BRAND['cidade']} • Confirmação #{datetime.now().strftime('%Y%m%d')}")

    c.save()
    return saida_pdf

def brl(v):
    v = float(v or 0)
    s = f"{v:,.2f}"           # ex: 1,234.56
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")  # BR: 1.234,56
    return f"R$ {s}"

def load_font(preferred: List[str], size: int):
    for name in preferred:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()

def calcular_totais(itens, desconto_geral_percent):
    raw_total = 0.0
    descontos_itens = 0.0
    for it in itens:
        q = float(it.get("quantidade", 1) or 0)
        v = float(it.get("valor_unitario", 0) or 0)
        d = float(it.get("desconto", 0) or 0)
        raw = q * v
        desconto_item_val = raw * (d / 100.0)
        raw_total += raw
        descontos_itens += desconto_item_val
    subtotal = raw_total - descontos_itens
    desconto_geral_val = subtotal * (float(desconto_geral_percent or 0) / 100.0)
    total = subtotal - desconto_geral_val
    return {
        "raw_total": round(raw_total, 2),
        "descontos_itens": round(descontos_itens, 2),
        "subtotal": round(subtotal, 2),
        "desconto_geral_val": round(desconto_geral_val, 2),
        "total": round(total, 2)
    }

def gerar_imagem(dados: Dict[str, Any],
                           saida_img: str,
                           largura_px: int = 1080,
                           formato: str = "PNG",):
    global BRAND, COLORS, LOGO_PATH
    """
    Gera uma imagem (PNG/JPG) do orçamento no mesmo padrão visual do PDF.
    - dados: dicionário com estrutura semelhante à sua função gerar_pdf
    - saida_img: caminho final (ex: 'orcamento.png' ou 'orcamento.jpg')
    - largura_px: largura em pixels (1080 é bom para WhatsApp)
    - formato: 'PNG' ou 'JPEG'
    - logo_path: caminho opcional para logotipo
    - BRAND, COLORS: dicionários opcionais para customizar texto/cores
    """
    # Defaults (se não passar)
    if BRAND is None:
        BRAND = {"empresa": "Mundo Kids", "cidade": "Cajazeiras-PB", "instagram": "@mundokids", "whatsapp": "(83) 9xxxx-xxxx"}
    if COLORS is None:
        COLORS = {
            "primary": "#0D6EFD",   # azul padrão
            "light": "#F4F7FB",
            "muted": "#7A7A7A",
            "dark": "#222222",
            "success": "#28A745"
        }

    # Fontes (tenta algumas comuns, senão fallback)
    font_pref = ["DejaVuSans.ttf", "DejaVuSans-Bold.ttf", "Arial.ttf", "arial.ttf"]
    font_pref_bold = ["DejaVuSans-Bold.ttf", "Arial Bold.ttf", "arialbd.ttf", "Arial.ttf"]
    scale = largura_px / 1080.0
    title_font = load_font(font_pref_bold, max(20, int(36 * scale)))
    header_font = load_font(font_pref_bold, max(14, int(20 * scale)))
    regular_font = load_font(font_pref, max(12, int(16 * scale)))
    small_font = load_font(font_pref, max(10, int(12 * scale)))

    # Medidor temporário
    tmp_img = Image.new("RGB", (10,10))
    tmp_draw = ImageDraw.Draw(tmp_img)

    margin = int(40 * scale)
    content_w = largura_px - 2 * margin

    # Colunas (proporções iguais ao PDF)
    col_w = [0.60 * content_w, 0.10 * content_w, 0.15 * content_w, 0.15 * content_w]
    col_x = [margin]
    for i in range(1, len(col_w)):
        col_x.append(col_x[i-1] + int(col_w[i-1]))

    # Calcular altura dinâmica:
    top_header_h = int(140 * scale)   # header colorido e espaço
    cliente_h = int(80 * scale)
    tabela_header_h = int(50 * scale)
    linha_base_h = int(60 * scale)    # altura mínima por item
    itens = dados.get("brinquedos", [])
    itens_heights = []
    padding_desc = int(10 * scale)
    for it in itens:
        desc = str(it.get("descricao", "-"))
        max_w = int(col_w[0]) - padding_desc*2
        lines = wrap_text(desc, max_w, regular_font, tmp_draw)
        h = max(linha_base_h, int(len(lines) * (regular_font.size + 6)))
        itens_heights.append((lines, h))

    totais = calcular_totais(itens, dados.get("desconto_geral", 0))
    totals_block_h = int(180 * scale)
    obs_text = dados.get("observacoes") or "• Tempo padrão de operação: 3 horas com monitor incluso\n• Valores sujeitos a disponibilidade\n• Montagem e desmontagem inclusas"
    obs_lines = []
    for l in obs_text.split("\n"):
        obs_lines += wrap_text(l, content_w - 2*padding_desc, regular_font, tmp_draw)
    obs_h = max(int(60*scale), int(len(obs_lines) * (regular_font.size + 6)))

    footer_h = int(60 * scale)
    bottom_margin = int(30 * scale)

    altura_total = top_header_h + cliente_h + tabela_header_h + sum(h for _,h in itens_heights) + totals_block_h + obs_h + footer_h + bottom_margin + 90

    # Criar imagem final
    img = Image.new("RGB", (largura_px, altura_total), "white")
    draw = ImageDraw.Draw(img)

    y = 0
    # Header colorido
    draw.rectangle([0, y, largura_px, y + top_header_h], fill=COLORS["primary"])
    # Caixa título (light) sobrepondo
    box_h = int(60 * scale)
    box_y = y + top_header_h - int(30 * scale)
    draw.rounded_rectangle([margin, box_y, largura_px - margin, box_y + box_h], radius=int(8*scale), fill=COLORS["light"])
    # Texto ORÇAMENTO e data
    draw.text((margin + int(12*scale), box_y + int(8*scale)), "ORÇAMENTO", font=title_font, fill=COLORS["primary"])
    hoje = datetime.now().strftime("%d/%m/%Y")
    draw.text((largura_px - margin - 220, box_y + int(12*scale)), f"Data: {hoje}", font=small_font, fill=COLORS["muted"])
    draw.text((largura_px - margin - 220, box_y + int(12*scale) + small_font.size + 2), "Validade: 7 dias", font=small_font, fill=COLORS["muted"])

    y = top_header_h - 80
    # Logo (centralizado na faixa do header, se houver)
    if LOGO_PATH and os.path.exists(LOGO_PATH):
        try:
            logo = Image.open(LOGO_PATH).convert("RGBA")
            max_logo_w = int(200 * scale)
            w0,h0 = logo.size
            ratio = min(max_logo_w / w0, (box_h + int(10*scale)) / h0, 1.0)
            logo_resized = logo.resize((int(w0*ratio) + 50, int(h0*ratio)) +50, Image.LANCZOS)
            logo_x = (largura_px - logo_resized.width)//2
            logo_y = y + int(10*scale)
            img.paste(logo_resized, (logo_x, logo_y), logo_resized)
        except Exception:
            pass

    y = box_y + box_h + int(10*scale)

    # Dados do cliente e endereço (like PDF)
    cliente = dados.get("cliente", {})
    evento = dados.get("evento", {})
    endereco = evento.get("endereco", "-")
    partes = [p.strip() for p in endereco.split(",")]

    draw.text((margin, y), "CLIENTE", font=header_font, fill=COLORS["dark"])
    right_x = largura_px - margin - int(300*scale)
    draw.text((right_x, y), "ENDEREÇO", font=header_font, fill=COLORS["dark"])
    y += header_font.size + int(8*scale)

    # Nome + Telefone
    nome_tel = f"Nome: {cliente.get('nome','-')} - {cliente.get('telefone','-')}"
    draw.text((margin, y), nome_tel, font=regular_font, fill=COLORS["dark"])
    # Endereço (quebrado)
    addr_lines = []
    if len(partes) > 0:
        addr_lines.append(partes[0])
    if len(partes) > 1:
        addr_lines.append(", ".join(partes[1:3]) if len(partes)>=3 else partes[1])
    if len(partes) > 3:
        addr_lines.append(", ".join(partes[3:5]) if len(partes)>=5 else partes[3])

    # Se endereço muito longo, fazer wrap
    ax = right_x
    ay = y
    for ln in addr_lines:
        wrapped = wrap_text(ln, int(300*scale), regular_font, draw)
        for wln in wrapped:
            draw.text((ax, ay), wln, font=regular_font, fill=COLORS["dark"])
            ay += regular_font.size + int(4*scale)

    # Data do evento e hora
    evento_data = evento.get("data", "-")
    evento_hora = evento.get("hora_inicio", "-")
    draw.text((right_x, ay + int(4*scale)), f"data do evento: {evento_data} às {evento_hora}", font=regular_font, fill=COLORS["dark"])
    y = max(ay + regular_font.size + int(10*scale), y + cliente_h - int(20*scale))

    # Cabeçalho da tabela
    # Fundo do cabeçalho
    head_y = y + int(10*scale)
    draw.rounded_rectangle([margin, head_y, largura_px - margin, head_y + tabela_header_h], radius=int(6*scale), fill=COLORS["primary"])
    headers = ["DESCRIÇÃO", "QTD", "VALOR UNIT.", "TOTAL"]
    # Escrever headers (branco)
    for i, h in enumerate(headers):
        if i == 0:
            tx = col_x[i] + int(12*scale)
            ty = head_y + int((tabela_header_h - header_font.size)/2)
            draw.text((tx, ty), h, font=small_font, fill="white")
        else:
            text_w = draw.textbbox((0,0), h, font=small_font)[2]
            cx = col_x[i] + int(col_w[i]/2) - text_w/2
            ty = head_y + int((tabela_header_h - header_font.size)/2)
            draw.text((cx, ty), h, font=small_font, fill="white")

    y = head_y + tabela_header_h + int(8*scale)

    # Itens
    for idx, it in enumerate(itens):
        lines, h_item = itens_heights[idx]
        # Fundo alternado
        if idx % 2 == 0:
            draw.rounded_rectangle([margin, y, largura_px - margin, y + h_item], radius=int(4*scale), fill=COLORS["light"])
        # Descrição
        desc_x = col_x[0] + int(12*scale)
        desc_y = y + int((h_item - regular_font.size*len(lines))/2)
        for li, line in enumerate(lines):
            draw.text((desc_x, desc_y + li*(regular_font.size + 4)), line, font=regular_font, fill=COLORS["dark"])
        # Qtd
        qtd = float(it.get("quantidade", 1) or 0)
        qtd_text = f"{int(qtd) if qtd.is_integer() else qtd}"
        q_bbox = draw.textbbox((0,0), qtd_text, font=regular_font)
        qx = col_x[1] + int(col_w[1]/2) - (q_bbox[2]-q_bbox[0])/2
        qy = y + (h_item - regular_font.size)/2
        draw.text((qx, qy), qtd_text, font=regular_font, fill=COLORS["dark"])
        # Valor unitario
        vu = float(it.get("valor_unitario", 0) or 0)
        vu_text = brl(vu)
        vu_bbox = draw.textbbox((0,0), vu_text, font=regular_font)
        vx = col_x[2] + int(col_w[2]/2) - (vu_bbox[2]-vu_bbox[0])/2
        draw.text((vx, qy), vu_text, font=regular_font, fill=COLORS["dark"])
        # Total item (já com desconto individual)
        desconto = float(it.get("desconto", 0) or 0)
        total_item = qtd * vu * (1 - desconto/100.0)
        ti_text = brl(total_item)
        ti_bbox = draw.textbbox((0,0), ti_text, font=regular_font)
        tx = col_x[3] + int(col_w[3]/2) - (ti_bbox[2]-ti_bbox[0])/2
        draw.text((tx, qy), ti_text, font=regular_font, fill=COLORS["dark"])

        y += h_item

    # Totais (caixa à direita)
    y += int(12*scale)
    box_x0 = margin + int(content_w * 0.5)
    box_x1 = largura_px - margin
    box_h = totals_block_h
    draw.rounded_rectangle([box_x0, y, box_x1, y + box_h], radius=int(6*scale), fill=COLORS["light"])
    tx = box_x0 + int(12*scale)
    ty = y + int(12*scale)
    draw.text((tx, ty), "Subtotal:", font=regular_font, fill=COLORS["dark"])
    draw.text((box_x1 - int(12*scale) - draw.textbbox((0,0), brl(totais["subtotal"]), font=regular_font)[2], ty),
              brl(totais["subtotal"]), font=regular_font, fill=COLORS["dark"])

    ty += regular_font.size + int(6*scale)
    draw.text((tx, ty), "Desc. itens:", font=regular_font, fill=COLORS["dark"])
    draw.text((box_x1 - int(12*scale) - draw.textbbox((0,0), f"- {brl(totais['descontos_itens'])}", font=regular_font)[2], ty),
              f"- {brl(totais['descontos_itens'])}", font=regular_font, fill=COLORS["dark"])

    ty += regular_font.size + int(6*scale)
    valor_adicional = round(float(dados.get("valor_adicional", 0) or 0), 2)
    draw.text((tx, ty), "Valor adicional:", font=regular_font, fill=COLORS["dark"])
    draw.text((box_x1 - int(12*scale) - draw.textbbox((0,0), f"+ {brl(valor_adicional)}", font=regular_font)[2], ty),
              f"+ {brl(valor_adicional)}", font=regular_font, fill=COLORS["dark"])

    ty += regular_font.size + int(6*scale)
    desconto_geral = round(float(dados.get("desconto_geral", 0) or 0), 0)
    draw.text((tx, ty), f"Desc. geral ({desconto_geral}%):", font=regular_font, fill=COLORS["dark"])
    draw.text((box_x1 - int(12*scale) - draw.textbbox((0,0), f"- {brl(totais['desconto_geral_val'])}", font=regular_font)[2], ty),
              f"- {brl(totais['desconto_geral_val'])}", font=regular_font, fill=COLORS["dark"])

    # Linha separadora
    sep_y = ty + regular_font.size + int(8*scale)
    draw.line([tx, sep_y, box_x1 - int(12*scale), sep_y], fill=COLORS["muted"], width=1)

    # Total
    tot_y = sep_y + int(8*scale)
    draw.text((tx, tot_y), "TOTAL:", font=header_font, fill=COLORS["success"])
    total_final = totais["total"] + valor_adicional
    draw.text((box_x1 - int(12*scale) - draw.textbbox((0,0), brl(total_final), font=header_font)[2], tot_y),
              brl(total_final), font=header_font, fill=COLORS["success"])

    y = y + box_h + int(12*scale)

    # Observações
    draw.text((margin, y), "OBSERVAÇÕES:", font=header_font, fill=COLORS["muted"])
    oy = y + header_font.size + int(6*scale)
    for ln in obs_lines:
        draw.text((margin + int(8*scale), oy), ln, font=regular_font, fill=COLORS["dark"])
        oy += regular_font.size + int(6*scale)

    # Rodapé
    fy = altura_total - footer_h + int(6*scale)
    footer_lines = []
    if BRAND.get("instagram"):
        footer_lines.append(f"📷 {BRAND['instagram']}")
    if BRAND.get("whatsapp"):
        footer_lines.append(f"💬 {BRAND['whatsapp']}")
    footer_text = "   |   ".join(footer_lines)
    fw = draw.textbbox((0,0), footer_text, font=small_font)[2]
    draw.text(((largura_px - fw)/2, fy), footer_text, font=small_font, fill=COLORS["muted"])
    draw.text((largura_px/2, altura_total - int(12*scale)), f"{BRAND.get('empresa','')} • {BRAND.get('cidade','')}",
              font=small_font, fill=COLORS["muted"], anchor="mm")

    # Salvar
    if formato.upper() == "JPEG" or formato.upper() == "JPG":
        # converter para RGB se necessário e salvar com qualidade
        rgb = img.convert("RGB")
        rgb.save(saida_img, quality=90)
    else:
        img.save(saida_img)

    return saida_img

def gerar_confirmacao(dados: Dict[str, Any],
                           saida_img: str,
                           largura_px: int = 1080,
                           formato: str = "PNG",):
    try:
        global BRAND, COLORS, LOGO_PATH
        
        # ... (código anterior até a criação da imagem) ...

        y = 0
        # Header colorido
        img = Image.new("RGB", (largura_px, altura_total), "white")
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, y, largura_px, y + top_header_h], fill=COLORS["primary"])
        
        # Logo PRIMEIRO (antes da caixa do título)
        logo_y = y + int(20 * scale)
        if LOGO_PATH and os.path.exists(LOGO_PATH):
            try:
                logo = Image.open(LOGO_PATH).convert("RGBA")
                max_logo_w = int(120 * scale)  # Tamanho menor para caber melhor
                max_logo_h = int(80 * scale)
                
                w0, h0 = logo.size
                ratio = min(max_logo_w / w0, max_logo_h / h0, 1.0)
                new_w = int(w0 * ratio)
                new_h = int(h0 * ratio)
                
                logo_resized = logo.resize((new_w, new_h), Image.LANCZOS)
                logo_x = (largura_px - new_w) // 2
                img.paste(logo_resized, (logo_x, logo_y), logo_resized)
            except Exception as e:
                #print(f"Erro ao carregar logo: {e}")
                pass

        # Caixa título (light) sobrepondo - ajustar posição para não cobrir a logo
        box_h = int(50 * scale)
        box_y = y + top_header_h - int(40 * scale)  # Ajustado para dar espaço à logo
        draw.rounded_rectangle([margin, box_y, largura_px - margin, box_y + box_h], 
                              radius=int(8*scale), fill=COLORS["light"])
        
        # Texto ORÇAMENTO e data
        title_y = box_y + int((box_h - title_font.size) / 2)
        draw.text((margin + int(12*scale), title_y), "CONFIRMAÇÃO DE ORÇAMENTO", 
                 font=title_font, fill=COLORS["primary"])
        
        hoje = datetime.now().strftime("%d/%m/%Y")
        date_text = f"Data: {hoje}"
        date_width = draw.textbbox((0,0), date_text, font=small_font)[2]
        draw.text((largura_px - margin - date_width - int(12*scale), box_y + int(12*scale)), 
                 date_text, font=small_font, fill=COLORS["muted"])

        y = box_y + box_h + int(20*scale)

        # ... (restante do código para cliente, tabela, itens, totais) ...

        # Observações
        obs_title_y = y + int(20*scale)
        draw.text((margin, obs_title_y), "OBSERVAÇÕES:", font=header_font, fill=COLORS["muted"])
        
        oy = obs_title_y + header_font.size + int(8*scale)
        for ln in obs_lines:
            draw.text((margin + int(8*scale), oy), ln, font=regular_font, fill=COLORS["dark"])
            oy += regular_font.size + int(6*scale)

        # ATUALIZAR ALTURA TOTAL para incluir observações
        altura_utilizada = oy + int(40*scale)  # Espaço após observações

        # Rodapé - posicionar no final da imagem
        footer_y = altura_utilized if altura_utilized < altura_total - footer_h else altura_total - footer_h
        
        # Gradiente ou cor sólida para o footer
        draw.rectangle([0, footer_y, largura_px, footer_y + footer_h], fill=COLORS["primary"])
        
        # Texto do rodapé centralizado
        footer_text_y = footer_y + int((footer_h - small_font.size * 2) / 2)
        
        footer_lines = []
        if BRAND.get("instagram"):
            footer_lines.append(f"📷 {BRAND['instagram']}")
        if BRAND.get("whatsapp"):
            footer_lines.append(f"💬 {BRAND['whatsapp']}")
        
        if footer_lines:
            footer_text = "   |   ".join(footer_lines)
            fw = draw.textbbox((0,0), footer_text, font=small_font)[2]
            draw.text(((largura_px - fw)/2, footer_text_y), footer_text, 
                     font=small_font, fill="white")
        
        # Nome da empresa e cidade
        brand_text = f"{BRAND.get('empresa','')} • {BRAND.get('cidade','')}"
        brand_width = draw.textbbox((0,0), brand_text, font=small_font)[2]
        draw.text(((largura_px - brand_width)/2, footer_text_y + small_font.size + int(8*scale)), 
                 brand_text, font=small_font, fill="white")

        # Se necessário, recortar a imagem para a altura real usada
        altura_real = footer_y + footer_h + int(20*scale)
        if altura_real < altura_total:
            img = img.crop((0, 0, largura_px, altura_real))

        # Salvar
        if formato.upper() in ["JPEG", "JPG"]:
            rgb_img = img.convert("RGB")
            rgb_img.save(saida_img, quality=95, optimize=True)
        else:
            img.save(saida_img, optimize=True)

        return saida_img
        
    except Exception as e:
        #print("Erro ao gerar confirmação:", e)
        import traceback
        traceback.print_exc()
        return None

def gerar_arquivos(dados: Dict[str, Any], empresa: Dict[str, str] = BRAND) -> str:
    global LOGO_PATH, COLORS, BRAND
    # Obter o caminho REAL do arquivo de imagem
    if hasattr(empresa, 'logo') and empresa.logo:
        try:
            # Para ImageField, use .path para obter o caminho absoluto
            LOGO_PATH = empresa.logo.path
        except (ValueError, AttributeError):
            # Se não tiver arquivo ou der erro, mantém o padrão
            LOGO_PATH = os.environ.get("MUNDOKIDS_LOGO", "MUNDOKIDS_LOGO.png")
    else:
        # Se não tiver logo definido, usa o padrão
        LOGO_PATH = os.environ.get("MUNDOKIDS_LOGO", "MUNDOKIDS_LOGO.png")
    COLORS["primary"] = getattr(empresa, "cor_principal", COLORS["primary"])
    COLORS["secondary"] = getattr(empresa, "cor_secundaria", COLORS["secondary"])
    COLORS["accent"] = getattr(empresa, "cor_acento", COLORS["accent"])
    
    BRAND["empresa"] = getattr(empresa, "nome", BRAND["empresa"])
    BRAND["cidade"] = getattr(empresa, "cidade", BRAND["cidade"])
    BRAND["instagram"] = getattr(empresa, "instagram", BRAND["instagram"])
    BRAND["whatsapp"] = getattr(empresa, "whatsapp", BRAND["whatsapp"])
    
    
     # Verifique os nomes exatos dos campos no seu modelo Empresa
    #print(hasattr(empresa, 'cor_principal'))  # Deve retornar True
    #print(hasattr(empresa, 'cor_secundaria')) # Deve retornar True  
    #print(hasattr(empresa, 'cor_acento'))     # Deve retornar True
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    media_root = settings.MEDIA_ROOT
    diretorio_pdf = os.path.join(media_root, 'orcamentos', 'gerados')
    # Criar diretório se não existir
    os.makedirs(diretorio_pdf, exist_ok=True)
    SAIDAS_DIR = diretorio_pdf
    dados = orcamento_para_dict(dados)
    base = os.path.join(SAIDAS_DIR, f"orcamento_{dados.get('cliente', {}).get('nome', 'cliente').replace(' ', '_')}_{stamp}")
    pdf_path = f"{base}.pdf"
    png_path = f"{base}.png"
    #se o status for confirmado, gerar o PDF de confirmação
    #print("Dados para geração de arquivo:", dados)  # Linha de depuração
    if dados.get('status') == 'confirmado':
        #gerar_confirmacao(dados, png_path)
        gerar_confirmacao_agendamento(dados, pdf_path)
    else:
        gerar_pdf(dados, pdf_path)
        #gerar_imagem(dados, png_path)
    return pdf_path, ""

# No views.py ou utils.py
def orcamento_para_dict(orcamento):
    """Converte um objeto Orcamento para o formato esperado pelo template"""
    #diminuindo uma hora do horário do evento para a montagem
    hora_montagem = getattr(orcamento, 'hora_evento', None) or '16:00'
    if isinstance(hora_montagem, time):
        hora_montagem = hora_montagem.strftime("%H:%M")  # converte para string

    hora_montagem_parts = hora_montagem.split(':')
    if len(hora_montagem_parts) == 2:
        hora_montagem_hour = int(hora_montagem_parts[0]) - 1
        if hora_montagem_hour < 0:
            hora_montagem_hour = 0
        hora_montagem = f"{hora_montagem_hour:02}:{hora_montagem_parts[1]}"

    periodo_evento = getattr(orcamento, 'periodo_evento', 3)  # em horas
    periodo_evento = int(periodo_evento) if isinstance(periodo_evento, int) else 3

    hora_desmontagem_parts = hora_montagem.split(':')
    if len(hora_desmontagem_parts) == 2:
        hora_desmontagem_hour = int(hora_desmontagem_parts[0]) + periodo_evento + 1  # +1 hora para desmontagem
        if hora_desmontagem_hour > 23:
            hora_desmontagem_hour = 23
        hora_desmontagem = f"{hora_desmontagem_hour:02}:{hora_desmontagem_parts[1]}"
    # Obter dados do evento (você precisa adicionar esses campos ao modelo)
    evento_data = {
        "tipo": getattr(orcamento, 'tipo_evento', 'Aniversário Infantil'),
        "endereco": getattr(orcamento, 'endereco', 'Endereço não definido'),
        "data": orcamento.data_evento.strftime("%d/%m/%Y") if orcamento.data_evento else "Data não definida",
        "hora_inicio": getattr(orcamento, 'hora_evento', '16:00'),
        "hora_montagem": hora_montagem,
        "hora_desmontagem": hora_desmontagem,
    }
    
    # Converter itens para o formato esperado
    brinquedos = []
    total = Decimal('0.0')
    for item in orcamento.itens.all():
        valor_unitario = float(item.valor) if isinstance(item.valor, Decimal) else float(item.valor or 0)
        desconto = float(item.desconto) if isinstance(item.desconto, Decimal) else float(item.desconto or 0)
        
        valor_item = item.quantidade * valor_unitario * (1 - desconto / 100.0)
        total += Decimal(str(valor_item))
        brinquedos.append({
            "descricao": item.item.nome if item.item.nome else item.item.descricao,
            "quantidade": item.quantidade,
            "periodo": getattr(item.item, 'periodo', '3 horas'),  # Adicione campo periodo ao modelo Item
            "valor_unitario": float(item.valor),
            "desconto": float(item.desconto),
        })
    
    desconto_geral = float(orcamento.desconto_geral) if isinstance(orcamento.desconto_geral, Decimal) else float(orcamento.desconto_geral or 0)
    total = float(total - (total * Decimal(desconto_geral) / Decimal('100.0')))
        
    return {
        "cliente": {
            "nome": orcamento.cliente.nome,
            "telefone": orcamento.cliente.telefone,
        },
        "status": orcamento.status,
        'valor_adicional': float(orcamento.valor_adicional) if isinstance(orcamento.valor_adicional, Decimal) else float(orcamento.valor_adicional or 0),
        "valor_total": total,
        "valor_pago": float(orcamento.valor_pago) if isinstance(orcamento.valor_pago, Decimal) else float(orcamento.valor_pago or 0),
        "desconto_geral": desconto_geral,
        "observacoes": orcamento.observacoes or "",
        "data_criacao": orcamento.data_criacao.strftime("%d/%m/%Y"),
        "evento": evento_data,
        "brinquedos": brinquedos
    }