import os
from datetime import datetime, time
from typing import Dict, Any, Tuple, List
import math

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib.colors import HexColor
from django.conf import settings
from decimal import Decimal
from pdf2image import convert_from_path
from .models import arredondar_total
from accounts.imagens import caminho_temporario
import img2pdf
from PIL import Image, ImageDraw, ImageFont 
import tempfile
import uuid





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

LOGO_PATH = os.environ.get("MUNDOKIDS_LOGO", "LOGO_NEW.png")
ASSINATURA_PATH = None  # sem valor padrão — só existe quando a empresa cadastra a própria assinatura
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

def gerar_pdf(dados: Dict[str, Any], saida_pdf: str, recibo_orcamento=None) -> str:
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

    # Logo — contida dentro da faixa do cabeçalho (altura 70pt) para não
    # cortar no topo da página quando a logo é mais alta que larga.
    if LOGO_PATH and os.path.exists(LOGO_PATH):
        try:
            img = ImageReader(LOGO_PATH)
            iw, ih = img.getSize()
            aspect = ih / float(iw)
            header_h = 70
            max_logo_h = header_h - 10
            max_logo_w = 60 * mm
            logo_h = max_logo_h
            logo_w = logo_h / aspect
            if logo_w > max_logo_w:
                logo_w = max_logo_w
                logo_h = logo_w * aspect
            logo_x = (W - logo_w) / 2
            logo_y = H - header_h + (header_h - logo_h) / 2
            c.drawImage(img, logo_x, logo_y, width=logo_w, height=logo_h, mask='auto')
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
    totais = calcular_totais(itens, dados.get("desconto_geral", 0), dados.get("valor_adicional", 0))

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
    c.drawRightString(margin_left + content_width - 5 * mm, y_position - 70, brl(totais["total_final"]))

    # Se há desconto (de item ou geral), deixa explícito que ele só vale
    # para pagamento à vista via PIX.
    tem_desconto = totais["descontos_itens"] > 0 or totais["desconto_geral_val"] > 0
    if tem_desconto:
        c.setFont("Helvetica-Oblique", 7)
        c.setFillColor(HexColor(COLORS["muted"]))
        c.drawString(
            margin_left + content_width * 0.5 + 5 * mm,
            y_position - 80,
            "* Desconto válido para pagamento à vista via PIX."
        )

    # Observações
    obs_y = y_position
    obs = dados.get("observacoes") or "• Tempo padrão de operação: 3 horas com monitor incluso\n• Valores sujeitos a disponibilidade\n• Montagem e desmontagem inclusas"
    
    c.setFillColor(HexColor(COLORS["muted"]))
    c.setFont("Helvetica-Bold", 9)
    c.drawString(margin_left, obs_y, "OBSERVAÇÕES:")
    obs_y -= 15
    
    c.setFillColor(HexColor(COLORS["dark"]))
    c.setFont("Helvetica", 8)

    max_obs_width = content_width - 10 * mm
    for line in obs.split('\n'):
        sub_lines = wrap_text(line, max_obs_width, "Helvetica", 8, c) if line.strip() else ['']
        for sub_line in sub_lines:
            if obs_y < 30:  # Nova página se necessário
                c.showPage()
                obs_y = H - 40
            c.drawString(margin_left + 5 * mm, obs_y, sub_line)
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

    if recibo_orcamento is not None:
        c.showPage()
        desenhar_recibo(c, recibo_orcamento)

    c.save()
    return saida_pdf

def gerar_catalogo_pdf(itens: List[Dict[str, Any]], saida_pdf: str, titulo: str = "CATÁLOGO DE BRINQUEDOS") -> str:
    """
    Gera um PDF com visual de catálogo (cores/logo da empresa, mas em cards
    por item em vez de tabela) apenas com a lista de itens selecionados e
    seus preços — sem dados de cliente/evento.
    """
    c = canvas.Canvas(saida_pdf, pagesize=A4)
    W, H = A4

    margin_left = 15 * mm
    margin_right = 15 * mm
    content_width = W - margin_left - margin_right

    # --- Cabeçalho ---
    # A faixa colorida e a logo ficam contidas dentro do próprio cabeçalho;
    # a caixa do título fica inteiramente abaixo dela, sem se sobrepor.
    header_h = 34 * mm
    c.setFillColor(HexColor(COLORS["primary"]))
    c.rect(0, H - header_h, W, header_h, stroke=0, fill=1)

    if LOGO_PATH and os.path.exists(LOGO_PATH):
        try:
            img = ImageReader(LOGO_PATH)
            iw, ih = img.getSize()
            logo_h = 20 * mm
            logo_w = logo_h * (iw / float(ih))
            max_logo_w = 60 * mm
            if logo_w > max_logo_w:
                logo_w = max_logo_w
                logo_h = logo_w * (ih / float(iw))
            logo_x = (W - logo_w) / 2
            logo_y = H - header_h + (header_h - logo_h) / 2
            c.drawImage(img, logo_x, logo_y, width=logo_w, height=logo_h, mask='auto', preserveAspectRatio=True)
        except Exception:
            pass

    # Caixa de título, abaixo do cabeçalho colorido
    titulo_box_h = 18 * mm
    titulo_box_y = H - header_h - 6 * mm - titulo_box_h
    c.setFillColor(HexColor(COLORS["light"]))
    c.roundRect(margin_left, titulo_box_y, content_width, titulo_box_h, 4 * mm, stroke=0, fill=1)

    c.setFillColor(HexColor(COLORS["primary"]))
    c.setFont("Helvetica-Bold", 15)
    c.drawString(margin_left + 5 * mm, titulo_box_y + titulo_box_h - 10 * mm, titulo)

    hoje = datetime.now().strftime("%d/%m/%Y")
    c.setFont("Helvetica", 8)
    c.setFillColor(HexColor(COLORS["muted"]))
    c.drawRightString(W - margin_right - 5 * mm, titulo_box_y + titulo_box_h - 6 * mm, f"Data: {hoje}")
    c.drawRightString(W - margin_right - 5 * mm, titulo_box_y + titulo_box_h - 14 * mm, "Valores sujeitos a alteração")

    y_position = titulo_box_y - 10 * mm

    # --- Cards dos itens (2 colunas) ---
    colunas = 2
    card_gap = 6 * mm
    card_w = (content_width - card_gap * (colunas - 1)) / colunas
    card_h = 34 * mm
    limite_inferior = 30 * mm  # espaço reservado para o rodapé

    def desenhar_card(x, y_top, item):
        y_bottom = y_top - card_h

        # Corpo do card
        c.setFillColor(HexColor("#FFFFFF"))
        c.setStrokeColor(HexColor("#E2E8F0"))
        c.setLineWidth(0.7)
        c.roundRect(x, y_bottom, card_w, card_h, 3 * mm, stroke=1, fill=1)

        # Faixa de destaque na lateral esquerda (estilo "borda colorida")
        accent_w = 3 * mm
        c.setFillColor(HexColor(COLORS["primary"]))
        c.roundRect(x, y_bottom, accent_w * 2, card_h, 3 * mm, stroke=0, fill=1)
        c.setFillColor(HexColor("#FFFFFF"))
        c.rect(x + accent_w, y_bottom, accent_w * 2, card_h, stroke=0, fill=1)

        pad = 5 * mm
        text_x = x + accent_w + pad
        text_w = card_w - accent_w - pad * 1.6

        descricao = str(item.get("descricao", "-"))
        quantidade = float(item.get("quantidade", 1) or 1)
        valor_unitario = float(item.get("valor_unitario", 0) or 0)

        # Nome do item (até 2 linhas)
        c.setFillColor(HexColor(COLORS["dark"]))
        c.setFont("Helvetica-Bold", 10)
        nome_lines = wrap_text(descricao, text_w, "Helvetica-Bold", 10, c)[:2]
        nome_y = y_top - pad - 3 * mm
        for linha in nome_lines:
            c.drawString(text_x, nome_y, linha)
            nome_y -= 4 * mm

        # Quantidade selecionada
        qtd_texto = f"Quantidade: {int(quantidade) if quantidade.is_integer() else quantidade}"
        c.setFont("Helvetica", 8)
        c.setFillColor(HexColor(COLORS["muted"]))
        c.drawString(text_x, y_bottom + pad, qtd_texto)

        # Só o valor unitário, em destaque — sem subtotal nem soma geral
        c.setFont("Helvetica-Bold", 13)
        c.setFillColor(HexColor(COLORS["success"]))
        c.drawRightString(x + card_w - pad, y_bottom + pad, brl(valor_unitario))

    for i, item in enumerate(itens):
        col = i % colunas
        if col == 0 and (y_position - card_h) < limite_inferior:
            c.showPage()
            y_position = H - 30 * mm

        x = margin_left + col * (card_w + card_gap)
        desenhar_card(x, y_position, item)

        if col == colunas - 1 or i == len(itens) - 1:
            y_position -= card_h + card_gap

    # --- Rodapé ---
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

    marca_texto = BRAND.get('empresa') or "Mundo Kids"
    if BRAND.get('cidade'):
        marca_texto += f" • {BRAND['cidade']}"
    c.drawCentredString(W / 2, 5, marca_texto)

    c.save()
    return saida_pdf


def gerar_catalogo(itens: List[Dict[str, Any]], empresa=None, titulo: str = "CATÁLOGO DE BRINQUEDOS"):
    """
    Prepara a marca/cores da empresa (mesmo mecanismo usado em gerar_arquivos)
    e gera o PDF de catálogo a partir de uma lista de itens já selecionados.
    Retorna o caminho do PDF gerado, ou None em caso de erro.
    """
    try:
        _configurar_branding(empresa)

        diretorio_pdf = pasta_gerados()
        stamp = carimbo_arquivo()
        pdf_path = os.path.join(diretorio_pdf, f"catalogo_{stamp}.pdf")

        gerar_catalogo_pdf(itens, pdf_path, titulo=titulo)
        return pdf_path
    except Exception as e:
        print("Erro ao gerar catálogo:", e)
        return None


def carimbo_arquivo():
    """Data/hora + código aleatório: dois arquivos gerados no mesmo segundo
    nunca têm o mesmo nome (um download não apaga o arquivo do outro)."""
    return f"{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}_{uuid.uuid4().hex[:8]}"


def pasta_gerados():
    """
    Pasta onde os PDFs/imagens gerados são gravados antes de serem entregues.
    Usa a pasta temporária do sistema: em hospedagens como o Vercel só ela
    aceita gravação (media/ é somente leitura e daria "Read-only file system").
    Os arquivos são gerados na hora e enviados em seguida, então não precisam
    ficar guardados: arquivos com mais de 1 dia são apagados aqui mesmo.
    """
    pasta = os.path.join(tempfile.gettempdir(), "mundokids_gerados")
    os.makedirs(pasta, exist_ok=True)
    limite = datetime.now().timestamp() - 3600
    for nome in os.listdir(pasta):
        caminho = os.path.join(pasta, nome)
        try:
            if os.path.getmtime(caminho) < limite:
                os.remove(caminho)
        except OSError:
            pass  # em uso por outro processo/requisição: fica para a próxima limpeza
    return pasta


def _caminho_imagem_empresa(empresa, campo):
    """Caminho temporário da logo/assinatura (guardadas no banco), ou None."""
    try:
        return caminho_temporario(getattr(empresa, campo, None))
    except Exception as e:
        print(f"Erro ao preparar {campo} da empresa para o PDF:", e)
        return None


def _configurar_branding(empresa) -> None:
    """
    Atualiza os dicionários globais LOGO_PATH/COLORS/BRAND com os dados da
    empresa informada. getattr(...) só usa o valor padrão quando o atributo
    não existe; como campos como "cidade" podem existir e estar em branco
    (None) no banco, usamos "or" para não deixar "None" vazar pros PDFs.
    """
    global LOGO_PATH, ASSINATURA_PATH, COLORS, BRAND
    if empresa is None:
        return
    # Logo/assinatura ficam no banco; o PDF precisa de um arquivo, então
    # são gravadas numa pasta temporária (permitida também no Vercel)
    logo = _caminho_imagem_empresa(empresa, 'logo_img')
    if logo:
        LOGO_PATH = logo
    ASSINATURA_PATH = _caminho_imagem_empresa(empresa, 'assinatura_img')
    COLORS["primary"] = getattr(empresa, "cor_principal", None) or COLORS["primary"]
    COLORS["secondary"] = getattr(empresa, "cor_secundaria", None) or COLORS["secondary"]
    COLORS["accent"] = getattr(empresa, "cor_acento", None) or COLORS["accent"]
    BRAND["empresa"] = getattr(empresa, "nome", None) or BRAND["empresa"]
    BRAND["cidade"] = getattr(empresa, "cidade", None) or BRAND["cidade"]
    BRAND["instagram"] = getattr(empresa, "instagram", None) or BRAND["instagram"]
    BRAND["whatsapp"] = getattr(empresa, "whatsapp", None) or BRAND["whatsapp"]


def gerar_checklist_conferencia_pdf(orcamento, saida_pdf: str) -> str:
    """
    Gera um PDF de conferência/carregamento: para cada item do orçamento,
    lista o checklist de acessórios cadastrado para aquele brinquedo
    (Item.checklist_itens), com caixinhas para marcar manualmente na hora de
    separar e carregar o material antes do evento.
    """
    c = canvas.Canvas(saida_pdf, pagesize=A4)
    W, H = A4

    margin_left = 15 * mm
    margin_right = 15 * mm
    content_width = W - margin_left - margin_right

    # --- Cabeçalho (mesmo estilo do catálogo) ---
    header_h = 34 * mm
    c.setFillColor(HexColor(COLORS["primary"]))
    c.rect(0, H - header_h, W, header_h, stroke=0, fill=1)

    if LOGO_PATH and os.path.exists(LOGO_PATH):
        try:
            img = ImageReader(LOGO_PATH)
            iw, ih = img.getSize()
            logo_h = 20 * mm
            logo_w = logo_h * (iw / float(ih))
            max_logo_w = 60 * mm
            if logo_w > max_logo_w:
                logo_w = max_logo_w
                logo_h = logo_w * (ih / float(iw))
            logo_x = (W - logo_w) / 2
            logo_y = H - header_h + (header_h - logo_h) / 2
            c.drawImage(img, logo_x, logo_y, width=logo_w, height=logo_h, mask='auto', preserveAspectRatio=True)
        except Exception:
            pass

    titulo_box_h = 24 * mm
    titulo_box_y = H - header_h - 6 * mm - titulo_box_h
    c.setFillColor(HexColor(COLORS["light"]))
    c.roundRect(margin_left, titulo_box_y, content_width, titulo_box_h, 4 * mm, stroke=0, fill=1)

    c.setFillColor(HexColor(COLORS["primary"]))
    c.setFont("Helvetica-Bold", 15)
    c.drawString(margin_left + 5 * mm, titulo_box_y + titulo_box_h - 8 * mm, "LISTA DE CONFERÊNCIA")

    cliente_nome = orcamento.cliente.nome if getattr(orcamento, 'cliente_id', None) else "-"
    data_evento = orcamento.data_evento.strftime("%d/%m/%Y") if orcamento.data_evento else "-"
    hora_evento = orcamento.hora_evento.strftime("%H:%M") if hasattr(orcamento.hora_evento, 'strftime') else str(orcamento.hora_evento or "-")

    c.setFont("Helvetica", 9)
    c.setFillColor(HexColor(COLORS["dark"]))
    c.drawString(margin_left + 5 * mm, titulo_box_y + titulo_box_h - 16 * mm, f"Cliente: {cliente_nome}")

    c.setFont("Helvetica", 8)
    c.setFillColor(HexColor(COLORS["muted"]))
    c.drawRightString(W - margin_right - 5 * mm, titulo_box_y + titulo_box_h - 8 * mm, f"Evento: {data_evento} às {hora_evento}")
    c.drawRightString(W - margin_right - 5 * mm, titulo_box_y + titulo_box_h - 16 * mm, f"Orçamento #{orcamento.id}")

    y_position = titulo_box_y - 10 * mm
    limite_inferior = 25 * mm

    def nova_pagina():
        nonlocal y_position
        c.showPage()
        y_position = H - 30 * mm

    def checar_espaco(altura_necessaria):
        if y_position - altura_necessaria < limite_inferior:
            nova_pagina()

    # --- Um bloco por item do orçamento, com seu checklist ---
    itens_orcamento = list(orcamento.itens.select_related('item').prefetch_related('item__checklist_itens').all())

    if not itens_orcamento:
        c.setFont("Helvetica", 10)
        c.setFillColor(HexColor(COLORS["muted"]))
        c.drawString(margin_left, y_position, "Este orçamento não possui itens.")

    for oi in itens_orcamento:
        item = oi.item
        # Kit dos infláveis (lona, extensão, soprador) + checklist próprio do item
        checklist = item.itens_conferencia()

        checar_espaco(20 * mm)

        # Cabeçalho do item (nome + quantidade)
        c.setFillColor(HexColor(COLORS["primary"]))
        c.roundRect(margin_left, y_position - 8 * mm, content_width, 8 * mm, 2 * mm, stroke=0, fill=1)
        c.setFillColor(HexColor("#FFFFFF"))
        c.setFont("Helvetica-Bold", 10)
        nome_item = item.nome or item.descricao
        c.drawString(margin_left + 4 * mm, y_position - 5.5 * mm, f"{nome_item}  (Qtd: {oi.quantidade})")
        y_position -= 8 * mm + 4 * mm

        if not checklist:
            c.setFont("Helvetica-Oblique", 8)
            c.setFillColor(HexColor(COLORS["muted"]))
            c.drawString(margin_left + 4 * mm, y_position, "Nenhum item de checklist cadastrado para este brinquedo.")
            y_position -= 8 * mm
        else:
            c.setFont("Helvetica", 9)
            for descricao in checklist:
                checar_espaco(7 * mm)
                box_size = 3.5 * mm
                box_y = y_position - box_size + 1
                c.setStrokeColor(HexColor(COLORS["dark"]))
                c.setLineWidth(0.8)
                c.rect(margin_left + 4 * mm, box_y, box_size, box_size, stroke=1, fill=0)
                c.setFillColor(HexColor(COLORS["dark"]))
                c.drawString(margin_left + 4 * mm + box_size + 3 * mm, y_position - box_size + 1.2 * mm, descricao)
                y_position -= 7 * mm

        y_position -= 4 * mm  # espaço entre itens

    # --- Rodapé ---
    c.setFillColor(HexColor(COLORS["muted"]))
    c.setFont("Helvetica", 7)
    c.drawCentredString(
        W / 2, 10,
        f"{BRAND.get('empresa') or 'Mundo Kids'} • Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    )

    c.save()
    return saida_pdf


def gerar_checklist_conferencia(orcamento, empresa=None):
    """
    Prepara a marca/cores da empresa e gera o PDF de checklist de
    conferência para o orçamento informado. Retorna o caminho do PDF
    gerado, ou None em caso de erro.
    """
    try:
        _configurar_branding(empresa)

        diretorio_pdf = pasta_gerados()
        stamp = carimbo_arquivo()
        pdf_path = os.path.join(diretorio_pdf, f"checklist_orcamento_{orcamento.id}_{stamp}.pdf")

        gerar_checklist_conferencia_pdf(orcamento, pdf_path)
        return pdf_path
    except Exception as e:
        print("Erro ao gerar checklist de conferência:", e)
        return None


DIAS_SEMANA = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]


def gerar_resumo_festas_pdf(festas: List[Dict[str, Any]], totais: List[Tuple[str, int]],
                            periodo: str, saida_pdf: str, para_monitores: bool = False) -> str:
    """
    Gera um PDF simplificado com as festas de um período: agrupa por dia e,
    para cada festa, mostra hora, tipo de evento, cliente e os brinquedos com
    a quantidade. No final, soma quantas unidades de cada brinquedo saem no
    período (útil para planejar a separação do material).

    Com para_monitores=True vira a "escala de monitores", para enviar aos
    monitores conferirem a disponibilidade: sem dados do cliente e sem
    brinquedos, só quantos monitores cada dia precisa e o horário de cada festa.

    festas: [{'data': date, 'hora': 'HH:MM', 'hora_fim': 'HH:MM' | None,
              'tipo_evento': str, 'cliente': str, 'monitores': int,
              'itens': [(nome, quantidade), ...]}, ...]
    totais: [(nome, quantidade_total), ...]
    """
    c = canvas.Canvas(saida_pdf, pagesize=A4)
    W, H = A4

    margin_left = 15 * mm
    margin_right = 15 * mm
    content_width = W - margin_left - margin_right

    # --- Cabeçalho (mesmo estilo do checklist) ---
    header_h = 34 * mm
    c.setFillColor(HexColor(COLORS["primary"]))
    c.rect(0, H - header_h, W, header_h, stroke=0, fill=1)

    if LOGO_PATH and os.path.exists(LOGO_PATH):
        try:
            img = ImageReader(LOGO_PATH)
            iw, ih = img.getSize()
            logo_h = 20 * mm
            logo_w = logo_h * (iw / float(ih))
            max_logo_w = 60 * mm
            if logo_w > max_logo_w:
                logo_w = max_logo_w
                logo_h = logo_w * (ih / float(iw))
            logo_x = (W - logo_w) / 2
            logo_y = H - header_h + (header_h - logo_h) / 2
            c.drawImage(img, logo_x, logo_y, width=logo_w, height=logo_h, mask='auto', preserveAspectRatio=True)
        except Exception:
            pass

    titulo_box_h = 18 * mm
    titulo_box_y = H - header_h - 6 * mm - titulo_box_h
    c.setFillColor(HexColor(COLORS["light"]))
    c.roundRect(margin_left, titulo_box_y, content_width, titulo_box_h, 4 * mm, stroke=0, fill=1)

    c.setFillColor(HexColor(COLORS["primary"]))
    c.setFont("Helvetica-Bold", 15)
    c.drawString(margin_left + 5 * mm, titulo_box_y + titulo_box_h - 8 * mm,
                 "ESCALA DE MONITORES" if para_monitores else "RESUMO DE FESTAS")

    c.setFont("Helvetica", 9)
    c.setFillColor(HexColor(COLORS["dark"]))
    c.drawString(margin_left + 5 * mm, titulo_box_y + titulo_box_h - 14 * mm, f"Período: {periodo}")

    c.setFont("Helvetica", 8)
    c.setFillColor(HexColor(COLORS["muted"]))
    c.drawRightString(W - margin_right - 5 * mm, titulo_box_y + titulo_box_h - 8 * mm,
                      f"{len(festas)} festa{'s' if len(festas) != 1 else ''}")

    y_position = titulo_box_y - 10 * mm
    limite_inferior = 20 * mm

    def rodape():
        c.setFillColor(HexColor(COLORS["muted"]))
        c.setFont("Helvetica", 7)
        c.drawCentredString(
            W / 2, 10,
            f"{BRAND.get('empresa') or 'Mundo Kids'} • Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        )

    def checar_espaco(altura_necessaria):
        nonlocal y_position
        if y_position - altura_necessaria < limite_inferior:
            rodape()
            c.showPage()
            y_position = H - 20 * mm

    if not festas:
        c.setFont("Helvetica", 10)
        c.setFillColor(HexColor(COLORS["muted"]))
        c.drawString(margin_left, y_position, "Nenhuma festa encontrada para o período selecionado.")

    if para_monitores:
        # Escala de monitores: sem dados do cliente e sem brinquedos — só,
        # por dia, quantos monitores são necessários e o horário de cada festa.
        dias = []
        for festa in festas:
            if not dias or dias[-1][0] != festa['data']:
                dias.append((festa['data'], []))
            dias[-1][1].append(festa)

        def plural_monitor(n):
            return f"{n} monitor{'es' if n != 1 else ''}"

        for dia, festas_dia in dias:
            checar_espaco(7 * mm + 4 * mm + len(festas_dia) * 6 * mm + 4 * mm)
            c.setFillColor(HexColor(COLORS["primary"]))
            c.roundRect(margin_left, y_position - 7 * mm, content_width, 7 * mm, 2 * mm, stroke=0, fill=1)
            c.setFillColor(HexColor("#FFFFFF"))
            c.setFont("Helvetica-Bold", 10)
            c.drawString(margin_left + 4 * mm, y_position - 5 * mm,
                         f"{dia.strftime('%d/%m/%Y')} - {DIAS_SEMANA[dia.weekday()]}")
            c.drawRightString(W - margin_right - 4 * mm, y_position - 5 * mm,
                              plural_monitor(sum(f['monitores'] for f in festas_dia)))
            y_position -= 7 * mm + 5 * mm

            for festa in festas_dia:
                horario = f"{festa['hora']} às {festa['hora_fim']}" if festa.get('hora_fim') else festa['hora']
                c.setFillColor(HexColor(COLORS["dark"]))
                c.setFont("Helvetica", 10)
                c.drawString(margin_left + 6 * mm, y_position, f"Festa das {horario}")
                c.setFont("Helvetica-Bold", 10)
                c.drawRightString(W - margin_right - 4 * mm, y_position, plural_monitor(festa['monitores']))
                y_position -= 6 * mm
            y_position -= 4 * mm

        rodape()
        c.save()
        return saida_pdf

    # Colunas da linha de cada festa
    col_hora = margin_left + 3 * mm
    col_tipo = margin_left + 18 * mm
    col_itens = margin_left + 80 * mm
    largura_itens = W - margin_right - col_itens - 3 * mm
    fonte_itens = 9
    linha_h = 4.5 * mm

    largura_meio = col_itens - col_tipo - 3 * mm

    def uma_linha(texto, fonte, tamanho):
        """Corta o texto com '...' se não couber na coluna do meio."""
        if c.stringWidth(texto, fonte, tamanho) <= largura_meio:
            return texto
        return wrap_text(texto, largura_meio - 3 * mm, fonte, tamanho, c)[0] + "..."

    data_atual = None
    for festa in festas:
        linhas_itens = []
        for nome, qtd in festa['itens']:
            linhas_itens.extend(wrap_text(f"{qtd}x {nome}", largura_itens, "Helvetica", fonte_itens, c))
        if not linhas_itens:
            linhas_itens = ["(sem itens)"]

        # Coluna do meio: tipo do evento, cliente e (para monitores) o local
        linhas_meio = [
            (uma_linha(festa['tipo_evento'] or "-", "Helvetica-Bold", 10), "Helvetica-Bold", 10, COLORS["dark"]),
            (uma_linha(festa['cliente'] or "-", "Helvetica", 8), "Helvetica", 8, COLORS["muted"]),
        ]
        altura_festa = max(len(linhas_meio), len(linhas_itens)) * linha_h + 4 * mm

        # Faixa com o dia (só quando muda de data)
        if festa['data'] != data_atual:
            checar_espaco(9 * mm + altura_festa)
            data_atual = festa['data']
            c.setFillColor(HexColor(COLORS["primary"]))
            c.roundRect(margin_left, y_position - 7 * mm, content_width, 7 * mm, 2 * mm, stroke=0, fill=1)
            c.setFillColor(HexColor("#FFFFFF"))
            c.setFont("Helvetica-Bold", 10)
            dia_semana = DIAS_SEMANA[data_atual.weekday()]
            c.drawString(margin_left + 4 * mm, y_position - 5 * mm,
                         f"{data_atual.strftime('%d/%m/%Y')} - {dia_semana}")
            y_position -= 7 * mm + 4 * mm
        else:
            checar_espaco(altura_festa)

        topo = y_position
        c.setFillColor(HexColor(COLORS["dark"]))
        c.setFont("Helvetica-Bold", 10)
        c.drawString(col_hora, topo - 3 * mm, festa['hora'])

        y_meio = topo - 3 * mm
        for texto, fonte, tamanho, cor in linhas_meio:
            c.setFont(fonte, tamanho)
            c.setFillColor(HexColor(cor))
            c.drawString(col_tipo, y_meio, texto)
            y_meio -= linha_h

        c.setFont("Helvetica", fonte_itens)
        c.setFillColor(HexColor(COLORS["dark"]))
        y_item = topo - 3 * mm
        for linha in linhas_itens:
            c.drawString(col_itens, y_item, linha)
            y_item -= linha_h

        y_position -= altura_festa
        c.setStrokeColor(HexColor("#E2E8F0"))
        c.setLineWidth(0.5)
        c.line(margin_left, y_position + 2 * mm, W - margin_right, y_position + 2 * mm)

    # --- Total de brinquedos no período ---
    if totais:
        y_position -= 4 * mm
        checar_espaco(16 * mm)
        c.setFillColor(HexColor(COLORS["light"]))
        c.roundRect(margin_left, y_position - 8 * mm, content_width, 8 * mm, 2 * mm, stroke=0, fill=1)
        c.setFillColor(HexColor(COLORS["primary"]))
        c.setFont("Helvetica-Bold", 10)
        c.drawString(margin_left + 4 * mm, y_position - 5.5 * mm, "TOTAL DE ITENS NO PERÍODO")
        total_geral = sum(qtd for _, qtd in totais)
        c.drawRightString(W - margin_right - 4 * mm, y_position - 5.5 * mm, f"{total_geral} unidade{'s' if total_geral != 1 else ''}")
        y_position -= 8 * mm + 5 * mm

        c.setFont("Helvetica", 9)
        for nome, qtd in totais:
            checar_espaco(6 * mm)
            c.setFillColor(HexColor(COLORS["dark"]))
            c.drawString(margin_left + 4 * mm, y_position, nome)
            c.setFont("Helvetica-Bold", 9)
            c.drawRightString(W - margin_right - 4 * mm, y_position, str(qtd))
            c.setFont("Helvetica", 9)
            y_position -= 5.5 * mm

    rodape()
    c.save()
    return saida_pdf


def gerar_resumo_festas(festas, totais, periodo, empresa=None, para_monitores=False):
    """
    Prepara a marca/cores da empresa e gera o PDF de resumo de festas (ou a
    escala de monitores, com para_monitores=True). Retorna o caminho do PDF
    gerado, ou None em caso de erro.
    """
    try:
        _configurar_branding(empresa)

        diretorio_pdf = pasta_gerados()
        stamp = carimbo_arquivo()
        pdf_path = os.path.join(diretorio_pdf, f"resumo_festas_{stamp}.pdf")

        gerar_resumo_festas_pdf(festas, totais, periodo, pdf_path, para_monitores)
        return pdf_path
    except Exception as e:
        print("Erro ao gerar resumo de festas:", e)
        return None


def gerar_recibo_pdf(orcamento, saida_pdf: str) -> str:
    """
    Gera um recibo simples referente ao valor já pago do orçamento — para
    o cliente que faz um pagamento (sinal ou quitação) ter um comprovante.
    """
    c = canvas.Canvas(saida_pdf, pagesize=A4)
    desenhar_recibo(c, orcamento)
    c.save()
    return saida_pdf


def desenhar_recibo(c, orcamento) -> None:
    """
    Desenha o recibo na página atual do canvas. Separado de gerar_recibo_pdf
    para o recibo também poder ir embutido como página extra em outros PDFs
    (ex.: na confirmação do agendamento).
    """
    W, H = A4

    margin_left = 15 * mm
    margin_right = 15 * mm
    content_width = W - margin_left - margin_right

    # --- Cabeçalho (mesmo estilo do catálogo/checklist) ---
    header_h = 34 * mm
    c.setFillColor(HexColor(COLORS["primary"]))
    c.rect(0, H - header_h, W, header_h, stroke=0, fill=1)

    if LOGO_PATH and os.path.exists(LOGO_PATH):
        try:
            img = ImageReader(LOGO_PATH)
            iw, ih = img.getSize()
            logo_h = 20 * mm
            logo_w = logo_h * (iw / float(ih))
            max_logo_w = 60 * mm
            if logo_w > max_logo_w:
                logo_w = max_logo_w
                logo_h = logo_w * (ih / float(iw))
            logo_x = (W - logo_w) / 2
            logo_y = H - header_h + (header_h - logo_h) / 2
            c.drawImage(img, logo_x, logo_y, width=logo_w, height=logo_h, mask='auto', preserveAspectRatio=True)
        except Exception:
            pass

    titulo_box_h = 24 * mm
    titulo_box_y = H - header_h - 6 * mm - titulo_box_h
    c.setFillColor(HexColor(COLORS["light"]))
    c.roundRect(margin_left, titulo_box_y, content_width, titulo_box_h, 4 * mm, stroke=0, fill=1)

    c.setFillColor(HexColor(COLORS["primary"]))
    c.setFont("Helvetica-Bold", 15)
    c.drawString(margin_left + 5 * mm, titulo_box_y + titulo_box_h - 8 * mm, "RECIBO DE PAGAMENTO")

    hoje = datetime.now().strftime("%d/%m/%Y")
    c.setFont("Helvetica", 8)
    c.setFillColor(HexColor(COLORS["muted"]))
    c.drawRightString(W - margin_right - 5 * mm, titulo_box_y + titulo_box_h - 8 * mm, f"Emitido em: {hoje}")
    c.drawRightString(W - margin_right - 5 * mm, titulo_box_y + titulo_box_h - 16 * mm, f"Orçamento #{orcamento.id}")

    cliente_nome = orcamento.cliente.nome if getattr(orcamento, 'cliente_id', None) else "-"
    cliente_telefone = orcamento.cliente.telefone if getattr(orcamento, 'cliente_id', None) else "-"
    c.setFont("Helvetica", 9)
    c.setFillColor(HexColor(COLORS["dark"]))
    c.drawString(margin_left + 5 * mm, titulo_box_y + titulo_box_h - 16 * mm, f"Cliente: {cliente_nome} — {cliente_telefone}")

    y_position = titulo_box_y - 14 * mm

    # --- Valor recebido em destaque ---
    valor_pago = orcamento.valor_pago or Decimal('0')
    box_h = 26 * mm
    c.setFillColor(HexColor(COLORS["light"]))
    c.roundRect(margin_left, y_position - box_h, content_width, box_h, 4 * mm, stroke=0, fill=1)

    c.setFillColor(HexColor(COLORS["muted"]))
    c.setFont("Helvetica-Bold", 10)
    c.drawString(margin_left + 6 * mm, y_position - 9 * mm, "VALOR RECEBIDO")

    c.setFillColor(HexColor(COLORS["success"]))
    c.setFont("Helvetica-Bold", 22)
    c.drawString(margin_left + 6 * mm, y_position - 20 * mm, brl(float(valor_pago)))

    y_position -= box_h + 12 * mm

    # --- Texto do recibo ---
    tipo_evento = orcamento.tipo_evento or "evento"
    data_evento = orcamento.data_evento.strftime("%d/%m/%Y") if orcamento.data_evento else "a definir"

    texto = (
        f"Recebemos de {cliente_nome} a quantia de {brl(float(valor_pago))}, referente à locação de "
        f"brinquedos para o evento do tipo \"{tipo_evento}\", com data prevista para {data_evento}, "
        f"conforme orçamento #{orcamento.id}."
    )

    c.setFillColor(HexColor(COLORS["dark"]))
    c.setFont("Helvetica", 9)
    max_width = content_width - 10 * mm
    for linha in wrap_text(texto, max_width, "Helvetica", 9, c):
        c.drawString(margin_left + 5 * mm, y_position, linha)
        y_position -= 5 * mm

    y_position -= 8 * mm

    # --- Totais (valor total do orçamento e saldo restante) ---
    valor_total = orcamento.total
    saldo = orcamento.saldo

    c.setFont("Helvetica", 9)
    c.setFillColor(HexColor(COLORS["dark"]))
    c.drawString(margin_left + 5 * mm, y_position, f"Valor total do orçamento: {brl(float(valor_total))}")
    y_position -= 6 * mm
    if saldo > 0:
        c.setFillColor(HexColor(COLORS["accent"]))
        c.drawString(margin_left + 5 * mm, y_position, f"Saldo restante a pagar: {brl(float(saldo))}")
    else:
        c.setFillColor(HexColor(COLORS["success"]))
        c.drawString(margin_left + 5 * mm, y_position, "Orçamento quitado — sem saldo restante.")
    y_position -= 30 * mm

    # --- Assinatura ---
    # Se a empresa tiver uma imagem de assinatura cadastrada, ela é
    # carimbada em cima da linha (já "assinado" ao gerar o PDF); senão, a
    # linha fica em branco para assinatura física, como antes.
    linha_assinatura_w = 80 * mm
    linha_x = margin_left + (content_width - linha_assinatura_w) / 2
    tem_assinatura = ASSINATURA_PATH and os.path.exists(ASSINATURA_PATH)

    if tem_assinatura:
        try:
            img_assinatura = ImageReader(ASSINATURA_PATH)
            iw, ih = img_assinatura.getSize()
            assinatura_h = 24 * mm
            assinatura_w = assinatura_h * (iw / float(ih))
            max_w = linha_assinatura_w
            if assinatura_w > max_w:
                assinatura_w = max_w
                assinatura_h = assinatura_w * (ih / float(iw))
            assinatura_x = W / 2 - assinatura_w / 2
            # Desce um pouco abaixo da linha (em vez de apoiar exatamente em
            # cima dela) — a maioria das fotos de assinatura tem uma margem
            # em branco ao redor do traço, então "descer" a imagem ajuda o
            # traço a ficar mais perto da linha em vez de flutuar acima.
            assinatura_y = y_position - 6 * mm
            c.drawImage(img_assinatura, assinatura_x, assinatura_y, width=assinatura_w, height=assinatura_h, mask='auto', preserveAspectRatio=True)
        except Exception:
            tem_assinatura = False

    c.setStrokeColor(HexColor(COLORS["muted"]))
    c.setLineWidth(0.6)
    c.line(linha_x, y_position, linha_x + linha_assinatura_w, y_position)
    y_position -= 5 * mm
    c.setFont("Helvetica", 8)
    c.setFillColor(HexColor(COLORS["muted"]))
    c.drawCentredString(W / 2, y_position, BRAND.get('empresa') or 'Mundo Kids')

    if tem_assinatura:
        y_position -= 5 * mm
        c.setFont("Helvetica-Oblique", 6.5)
        c.drawCentredString(
            W / 2, y_position,
            f"Documento gerado e assinado eletronicamente em {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        )

    # --- Rodapé ---
    c.setFillColor(HexColor(COLORS["muted"]))
    c.setFont("Helvetica", 7)
    c.drawCentredString(
        W / 2, 10,
        f"{BRAND.get('empresa') or 'Mundo Kids'} • Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    )


def gerar_recibo(orcamento, empresa=None):
    """
    Prepara a marca/cores da empresa e gera o PDF de recibo de pagamento
    para o orçamento informado. Retorna o caminho do PDF gerado, ou None
    em caso de erro.
    """
    try:
        _configurar_branding(empresa)

        diretorio_pdf = pasta_gerados()
        stamp = carimbo_arquivo()
        pdf_path = os.path.join(diretorio_pdf, f"recibo_orcamento_{orcamento.id}_{stamp}.pdf")

        gerar_recibo_pdf(orcamento, pdf_path)
        return pdf_path
    except Exception as e:
        print("Erro ao gerar recibo:", e)
        return None


def gerar_confirmacao_agendamento(dados: Dict[str, Any], saida_pdf: str, recibo_orcamento=None) -> str:
    """
    Gera PDF de confirmação de agendamento com layout similar ao orçamento.
    Se recibo_orcamento for informado, o recibo do valor pago vai embutido
    como página extra no final.
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

    # Logo — contida dentro da faixa do cabeçalho (altura 70pt) para não
    # cortar no topo da página quando a logo é mais alta que larga.
    if LOGO_PATH and os.path.exists(LOGO_PATH):
        try:
            img = ImageReader(LOGO_PATH)
            iw, ih = img.getSize()
            aspect = ih / float(iw)
            header_h = 70
            max_logo_h = header_h - 10
            max_logo_w = 60 * mm
            logo_h = max_logo_h
            logo_w = logo_h / aspect
            if logo_w > max_logo_w:
                logo_w = max_logo_w
                logo_h = logo_w * aspect
            logo_x = (W - logo_w) / 2
            logo_y = H - header_h + (header_h - logo_h) / 2
            c.drawImage(img, logo_x, logo_y, width=logo_w, height=logo_h, mask='auto')
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
    valorTotal = dados.get('valor_total') + dados.get('valor_adicional', 0)
    c.drawString(margin_left, y_position, f"Valor total: {brl(valorTotal)}")
    y_position -= 10
    c.drawString(margin_left, y_position, f"Valor pago (sinal): {brl(dados.get('valor_pago', 0))}")
    y_position -= 10

    # Observações
    obs_text = (dados.get("observacoes") or "").strip()
    if obs_text:
        y_position -= 15
        if y_position < 60:
            c.showPage()
            y_position = H - 40
        c.setFillColor(HexColor(COLORS["primary"]))
        c.setFont("Helvetica-Bold", 10)
        c.drawString(margin_left, y_position, "OBSERVAÇÕES")
        y_position -= 12

        c.setFillColor(HexColor(COLORS["dark"]))
        c.setFont("Helvetica", 8)
        max_obs_width = content_width - 10 * mm
        for line in obs_text.split('\n'):
            sub_lines = wrap_text(line, max_obs_width, "Helvetica", 8, c) if line.strip() else ['']
            for sub_line in sub_lines:
                if y_position < 40:
                    c.showPage()
                    y_position = H - 40
                c.drawString(margin_left + 5 * mm, y_position, sub_line)
                y_position -= 4 * mm

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

    if recibo_orcamento is not None:
        c.showPage()
        desenhar_recibo(c, recibo_orcamento)

    c.save()
    return saida_pdf

def brl(v):
    v = float(v or 0)
    s = f"{v:,.2f}"           # ex: 1,234.56
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")  # BR: 1.234,56
    return f"R$ {s}"

PASTA_FONTES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
_FONTES_SISTEMA = {
    "regular": ["arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"],
    "negrito": ["arialbd.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"],
    "italico": ["ariali.ttf", "DejaVuSans-Oblique.ttf", "LiberationSans-Italic.ttf"],
}


def fonte(tamanho: int, estilo: str = "regular"):
    """
    Fonte para as imagens (PNG) em qualquer servidor: Arial (Windows) ->
    DejaVu/Liberation (Linux) -> Roboto incluída no projeto (orcamentos/fonts,
    garante funcionar onde não há fontes instaladas, como no Vercel) -> fonte
    padrão do Pillow em tamanho escalável.
    """
    for nome in _FONTES_SISTEMA.get(estilo, _FONTES_SISTEMA["regular"]):
        try:
            return ImageFont.truetype(nome, tamanho)
        except OSError:
            continue
    try:
        f = ImageFont.truetype(os.path.join(PASTA_FONTES, "Roboto.ttf"), tamanho)
        f.set_variation_by_name({"negrito": "Bold", "italico": "Regular"}.get(estilo, "Regular"))
        return f
    except Exception:
        return ImageFont.load_default(size=tamanho)


def load_font(preferred: List[str], size: int):
    for name in preferred:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    negrito = any("bold" in n.lower() or "bd." in n.lower() for n in preferred)
    return fonte(size, "negrito" if negrito else "regular")

def calcular_totais(itens, desconto_geral_percent, valor_adicional=0.0):
    """
    Totais do orçamento. "total_final" (total + valor adicional) é arredondado
    para reais inteiros, igual ao Orcamento.total; a diferença de centavos do
    arredondamento é absorvida no desconto geral, para a conta do quadro de
    totais continuar fechando (ex.: desconto de R$ 61,02 aparece como R$ 61,00).
    """
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

    valor_adicional = float(valor_adicional or 0)
    total_final = float(arredondar_total(total + valor_adicional))
    if desconto_geral_val > 0:
        desconto_geral_val -= total_final - (total + valor_adicional)
        total = total_final - valor_adicional

    return {
        "raw_total": round(raw_total, 2),
        "descontos_itens": round(descontos_itens, 2),
        "subtotal": round(subtotal, 2),
        "desconto_geral_val": round(desconto_geral_val, 2),
        "total": round(total, 2),
        "total_final": total_final,
    }

def gerar_imagem1(dados: Dict[str, Any],
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

    totais = calcular_totais(itens, dados.get("desconto_geral", 0), dados.get("valor_adicional", 0))
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
    img = Image.new("RGB", (largura_px, altura_total), COLORS["light"])
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
    total_final = totais["total_final"]
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

def gerar_arquivos(dados: Dict[str, Any], empresa: Dict[str, str] = BRAND, incluir_recibo: bool = False) -> str:
    """
    Gera o PDF + PNG do orçamento (ou da confirmação, se confirmado). Com
    incluir_recibo=True e havendo valor pago, o recibo vai embutido como
    página extra no PDF.
    """
    try:
        global LOGO_PATH, COLORS, BRAND
        orcamento = dados
        recibo_orcamento = orcamento if incluir_recibo and (orcamento.valor_pago or 0) > 0 else None
        if recibo_orcamento is not None:
            _configurar_branding(empresa)  # carrega a assinatura usada no recibo
                            
        # Logo guardada no banco (gravada num arquivo temporário para o PDF);
        # sem logo cadastrada, usa a padrão
        LOGO_PATH = (_caminho_imagem_empresa(empresa, 'logo_img')
                     or os.environ.get("MUNDOKIDS_LOGO", "MUNDOKIDS_LOGO.png"))
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
        stamp = carimbo_arquivo()
        diretorio_pdf = pasta_gerados()
        SAIDAS_DIR = diretorio_pdf
        dados = orcamento_para_dict(dados)
        if(dados.get('status') == 'confirmado'):
            base = os.path.join(SAIDAS_DIR, f"confirmacao_orcamento_{dados.get('cliente', {}).get('nome', 'cliente').replace(' ', '_')}_{stamp}")
        else:
            base = os.path.join(SAIDAS_DIR, f"orcamento_{dados.get('cliente', {}).get('nome', 'cliente').replace(' ', '_')}_{stamp}")
        pdf_path = f"{base}.pdf"
        png_path = f"{base}.png"
        #se o status for confirmado, gerar o PDF de confirmação
        #print("Dados para geração de arquivo:", dados)  # Linha de depuração
        if dados.get('status') == 'confirmado':
            gerar_confirmacao_agendamento(dados, pdf_path, recibo_orcamento)
            gerar_imagem_confirmacao(dados, png_path)
        else:
            gerar_pdf(dados, pdf_path, recibo_orcamento)
            gerar_imagem_orcamento(dados, png_path)
        return pdf_path, png_path
    except Exception as e:
        print("Erro ao gerar arquivos:", e)

WIDTH = 1080
HEIGHT = 1520

def formatar_hora(h):
    if hasattr(h, "strftime"):
        return h.strftime("%H:%M")
    return str(h)


def safe_filename(text):
    return "".join(c for c in text if c.isalnum() or c in "-_")


def wrap_text_pil(text: str, max_width: int, font, draw) -> List[str]:
    """Quebra texto em múltiplas linhas para caber em max_width, usando uma
    fonte/objeto de desenho do PIL (equivalente ao wrap_text, mas para as
    imagens PNG em vez dos PDFs do ReportLab)."""
    lines = []
    for paragrafo in text.split('\n'):
        if not paragrafo.strip():
            lines.append('')
            continue
        palavras = paragrafo.split()
        linha_atual = []
        for palavra in palavras:
            teste = ' '.join(linha_atual + [palavra])
            if draw.textlength(teste, font=font) <= max_width or not linha_atual:
                linha_atual.append(palavra)
            else:
                lines.append(' '.join(linha_atual))
                linha_atual = [palavra]
        if linha_atual:
            lines.append(' '.join(linha_atual))
    return lines


def gerar_imagem_orcamento(dados: Dict[str, Any], saida_png: str):
    W, H = 1080, 1920
    bg = "#FFFFFF"
    
    COLORS = {
        "primary": "#0A66C2",
        "light": "#F2F6FA",
        "dark": "#222222",
        "muted": "#666666",
        "success": "#16A34A"
    }

    img = Image.new("RGB", (W, H), bg)
    draw = ImageDraw.Draw(img)

    try:
        font_title = fonte(32, "negrito")
        font_sub = fonte(28, "regular")
        font_table_h = fonte(26, "negrito")
        font_table = fonte(26, "regular")
        font_total = fonte(24, "negrito")
        font_nota = fonte(18, "italico")
    except:
        font_title = font_sub = font_table_h = font_table = font_total = font_nota = ImageFont.load_default()

    # HEADER MEIA LUA
    draw.rectangle([0, 0, W, 160], fill=COLORS["primary"])

    # TITULO
    draw.rounded_rectangle([40, 80, W - 40, 200], 25, fill=COLORS["light"])
    titulo = "ORÇAMENTO"
    draw.text((70, 125), titulo, font=font_title, fill=COLORS["primary"])
    
    # LOGO LOGO_NEW.png
    def colar_logo(img, logo_path, y=40, size=160):
        if not logo_path or not os.path.exists(logo_path):
            return

        logo = Image.open(logo_path).convert("RGBA")
        w, h = logo.size
        aspect = h / w

        new_w = size
        new_h = int(size * aspect)

        logo = logo.resize((new_w, new_h), Image.LANCZOS)

        x = (img.width // 2) - (new_w // 2)

        img.paste(logo, (x, y), logo)

        hoje = datetime.now().strftime("%d/%m/%Y")
        draw.text((W - 300, 125), f"Data: {hoje}", font=font_sub, fill=COLORS["muted"])
        
    colar_logo(img, LOGO_PATH, y=35, size=170)

    y = 230

    cliente = dados.get("cliente", {})
    evento = dados.get("evento", {})

    draw.text((40, y), "CLIENTE", font=font_table_h, fill=COLORS["dark"])
    draw.text((40, y + 40), f"{cliente.get('nome','-')}  •  {cliente.get('telefone','-')}", font=font_table, fill=COLORS["dark"])

    draw.text((40, y + 85), "EVENTO", font=font_table_h, fill=COLORS["dark"])
    draw.text((40, y + 125), f"{evento.get('endereco','-')}", font=font_table, fill=COLORS["dark"])
    draw.text((40, y + 165), f"{evento.get('data','-')} às {evento.get('hora_inicio','-')}", font=font_table, fill=COLORS["dark"])

    y += 230

    # HEADER TABELA
    draw.rounded_rectangle([40, y, W - 40, y + 55], 15, fill=COLORS["primary"])
    headers = ["DESCRIÇÃO", "QTD", "VALOR", "TOTAL"]
    col_x = [50, 660, 780, 930]

    for i, h in enumerate(headers):
        draw.text((col_x[i], y + 14), h, font=font_table_h, fill="#FFFFFF")

    y += 75

    itens = dados.get("brinquedos", [])

    for idx, item in enumerate(itens):
        if idx % 2 == 0:
            draw.rounded_rectangle([40, y, W - 40, y + 70], 12, fill=COLORS["light"])

        descricao = str(item.get("descricao", "-"))
        qtd = item.get("quantidade", 1)
        valor = float(item.get("valor_unitario", 0))
        total = qtd * valor

        draw.text((50, y + 22), descricao, font=font_table, fill=COLORS["dark"])
        draw.text((685, y + 22), str(qtd), font=font_table, fill=COLORS["dark"])
        draw.text((785, y + 22), f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."), font=font_table, fill=COLORS["dark"])
        draw.text((915, y + 22), f"R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."), font=font_table, fill=COLORS["dark"])

        y += 75

    total_geral = sum(float(i.get("valor_unitario", 0)) * float(i.get("quantidade", 1)) for i in itens)
    valor_adicional = float(dados.get('valor_adicional', 0) or 0)
    # Mesmo cálculo do PDF (descontos por item + geral, total arredondado)
    total_final = calcular_totais(itens, dados.get('desconto_geral', 0), valor_adicional)["total_final"]
    descontos = total_geral + valor_adicional - total_final
    # BOX TOTAL
    y += 30
    draw.rounded_rectangle([W - 480, y, W - 40, y + 145], 15, fill=COLORS["light"])

    draw.text((W - 450, y + 25), "TOTAL:", font=font_total, fill=COLORS["success"])
    draw.text((W - 240, y + 25), f"R$ {total_geral:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
              font=font_total, fill=COLORS["success"])
    draw.text((W - 450, y + 55), f"Descontos:", font=font_table, fill=COLORS["dark"])
    draw.text((W - 240, y + 55), f"- {brl(descontos)}", font=font_total, fill=COLORS["success"])
    draw.text((W - 450, y + 80), f"Valor adicional: ", font=font_total, fill=COLORS["success"])
    draw.text((W - 240, y + 80), f"+ {brl(valor_adicional)}", font=font_total, fill=COLORS["success"])
    if dados.get('desconto_geral', 0):
        draw.text((W - 450, y + 130), "* Desconto válido p/ pagamento à vista via PIX",
                  font=font_nota, fill=COLORS["muted"])

    draw.text((W - 450, y + 105), f"TOTAL FINAL:", font=font_total, fill=COLORS["success"])
    draw.text((W - 240, y + 105), brl(total_final), font=font_total, fill=COLORS["success"])

    # OBSERVAÇÕES
    y += 175
    obs_text = dados.get("observacoes") or "• Tempo padrão de operação: 3 horas com monitor incluso\n• Valores sujeitos a disponibilidade\n• Montagem e desmontagem inclusas"
    obs_lines = wrap_text_pil(obs_text, W - 80, font_table, draw)
    obs_block_h = 40 + len(obs_lines) * 34 + 40

    # Se as observações forem longas (ex.: cláusula de evento sem monitoria),
    # a imagem cresce em vez de deixar o texto cortado ou sobreposto ao rodapé.
    footer_reservado = 200
    altura_necessaria = y + obs_block_h + footer_reservado
    if altura_necessaria > H:
        H = altura_necessaria
        nova_img = Image.new("RGB", (W, H), bg)
        nova_img.paste(img, (0, 0))
        img = nova_img
        draw = ImageDraw.Draw(img)

    draw.text((40, y), "OBSERVAÇÕES", font=font_table_h, fill=COLORS["dark"])
    y += 40
    for linha in obs_lines:
        draw.text((40, y), linha, font=font_table, fill=COLORS["dark"])
        y += 34

    y = H - 200
    rodape = "Estamos ansiosos para fazer parte do seu evento! 💙"
    rw = draw.textlength(rodape, font=font_sub)
    draw.text(((W - rw) // 2, y), rodape, fill=COLORS["primary"], font=font_sub)

    y += 38

    sub = "Mundo Kids — Diversão com segurança e qualidade"
    sw = draw.textlength(sub, font=font_sub)
    draw.text(((W - sw) // 2, y), sub, fill=COLORS["dark"], font=font_sub)

    img.save(saida_png, "PNG")
    return saida_png


def gerar_imagem_confirmacao(dados: Dict[str, Any], saida_png: str):
    """PNG de confirmação de agendamento, no mesmo estilo visual do PNG de
    orçamento (gerar_imagem_orcamento), mas com os dados do evento já
    fechado (endereço, horários de montagem/desmontagem) em vez de preços."""
    W, H = 1080, 1920
    bg = "#FFFFFF"

    COLORS = {
        "primary": "#0A66C2",
        "light": "#F2F6FA",
        "dark": "#222222",
        "muted": "#666666",
        "success": "#16A34A"
    }

    img = Image.new("RGB", (W, H), bg)
    draw = ImageDraw.Draw(img)

    try:
        font_title = fonte(32, "negrito")
        font_sub = fonte(28, "regular")
        font_table_h = fonte(26, "negrito")
        font_table = fonte(26, "regular")
        font_total = fonte(24, "negrito")
    except:
        font_title = font_sub = font_table_h = font_table = font_total = ImageFont.load_default()

    # HEADER
    draw.rectangle([0, 0, W, 160], fill=COLORS["primary"])
    draw.rounded_rectangle([40, 80, W - 40, 200], 25, fill=COLORS["light"])
    draw.text((70, 125), "CONFIRMAÇÃO", font=font_title, fill=COLORS["primary"])

    # LOGO
    if LOGO_PATH and os.path.exists(LOGO_PATH):
        try:
            logo = Image.open(LOGO_PATH).convert("RGBA")
            w, h = logo.size
            aspect = h / w
            new_w = 170
            new_h = int(new_w * aspect)
            logo = logo.resize((new_w, new_h), Image.LANCZOS)
            x = (W // 2) - (new_w // 2)
            img.paste(logo, (x, 35), logo)
        except Exception:
            pass

    hoje = datetime.now().strftime("%d/%m/%Y")
    draw.text((W - 300, 125), f"Data: {hoje}", font=font_sub, fill=COLORS["muted"])

    y = 230
    cliente = dados.get("cliente", {})
    evento = dados.get("evento", {})

    draw.text((40, y), "CLIENTE", font=font_table_h, fill=COLORS["dark"])
    draw.text((40, y + 40), f"{cliente.get('nome','-')}  •  {cliente.get('telefone','-')}", font=font_table, fill=COLORS["dark"])

    draw.text((40, y + 90), "EVENTO", font=font_table_h, fill=COLORS["dark"])
    draw.text((40, y + 130), f"{evento.get('tipo','-')}  •  {evento.get('data','-')} às {evento.get('hora_inicio','-')}", font=font_table, fill=COLORS["dark"])
    draw.text((40, y + 170), f"{evento.get('endereco','-')}", font=font_table, fill=COLORS["dark"])

    draw.text((40, y + 220), "MONTAGEM E DESMONTAGEM", font=font_table_h, fill=COLORS["dark"])
    draw.text((40, y + 260), f"Montagem prevista: {evento.get('hora_montagem','-')}   •   Desmontagem prevista: {evento.get('hora_desmontagem','-')}", font=font_table, fill=COLORS["dark"])

    y += 330

    # HEADER TABELA
    draw.rounded_rectangle([40, y, W - 40, y + 55], 15, fill=COLORS["primary"])
    headers = ["BRINQUEDO", "QTD", "PERÍODO"]
    col_x = [50, 700, 860]
    for i, h in enumerate(headers):
        draw.text((col_x[i], y + 14), h, font=font_table_h, fill="#FFFFFF")

    y += 75

    itens = dados.get("brinquedos", [])
    for idx, item in enumerate(itens):
        if idx % 2 == 0:
            draw.rounded_rectangle([40, y, W - 40, y + 70], 12, fill=COLORS["light"])
        descricao = str(item.get("descricao", "-"))
        qtd = item.get("quantidade", 1)
        periodo = item.get("periodo", "3 horas")
        draw.text((50, y + 22), descricao, font=font_table, fill=COLORS["dark"])
        draw.text((720, y + 22), str(qtd), font=font_table, fill=COLORS["dark"])
        draw.text((865, y + 22), str(periodo), font=font_table, fill=COLORS["dark"])
        y += 75

    # BOX PAGAMENTO
    y += 30
    draw.rounded_rectangle([W - 480, y, W - 40, y + 110], 15, fill=COLORS["light"])
    valor_total = float(dados.get('valor_total', 0)) + float(dados.get('valor_adicional', 0))
    draw.text((W - 450, y + 20), "VALOR TOTAL:", font=font_total, fill=COLORS["success"])
    draw.text((W - 240, y + 20), brl(valor_total), font=font_total, fill=COLORS["success"])
    draw.text((W - 450, y + 60), "SINAL PAGO:", font=font_total, fill=COLORS["dark"])
    draw.text((W - 240, y + 60), brl(dados.get('valor_pago', 0)), font=font_table, fill=COLORS["dark"])

    # OBSERVAÇÕES
    y += 150
    obs_text = dados.get("observacoes") or ""
    if obs_text.strip():
        obs_lines = wrap_text_pil(obs_text, W - 80, font_table, draw)
        obs_block_h = 40 + len(obs_lines) * 34 + 40

        # Se as observações forem longas (ex.: cláusula de evento sem
        # monitoria), a imagem cresce em vez de cortar/sobrepor o rodapé.
        footer_reservado = 100
        altura_necessaria = y + obs_block_h + footer_reservado
        if altura_necessaria > H:
            H = altura_necessaria
            nova_img = Image.new("RGB", (W, H), bg)
            nova_img.paste(img, (0, 0))
            img = nova_img
            draw = ImageDraw.Draw(img)

        draw.text((40, y), "OBSERVAÇÕES", font=font_table_h, fill=COLORS["dark"])
        y += 40
        for linha in obs_lines:
            draw.text((40, y), linha, font=font_table, fill=COLORS["dark"])
            y += 34
        y += 40

    rodape = "Confirmado! Estamos ansiosos para fazer parte do seu evento 💙"
    rw = draw.textlength(rodape, font=font_sub)
    draw.text(((W - rw) // 2, min(y, H - 100)), rodape, fill=COLORS["primary"], font=font_sub)

    img.save(saida_png, "PNG")
    return saida_png


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
    # Os PDFs somam "valor_total + valor_adicional"; ajusta para essa soma dar
    # o total arredondado em reais inteiros (mesmo valor do Orcamento.total)
    adicional = float(orcamento.valor_adicional or 0)
    total = float(arredondar_total(total + adicional)) - adicional

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