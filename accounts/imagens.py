"""
Imagens guardadas no banco (ImagemArmazenada): preparar no upload, entregar
ao navegador e disponibilizar como arquivo temporário para os PDFs.
"""
import hashlib
import io
import os
import tempfile

from django.http import HttpResponse
from PIL import Image, ImageOps

from .models import ImagemArmazenada

# Tamanho máximo (maior lado, em pixels) e formato de cada uso
FOTO_ITEM = {'max_lado': 1000, 'formato': 'JPEG'}   # fotos: JPEG leve
LOGO = {'max_lado': 800, 'formato': 'PNG'}          # PNG mantém o fundo transparente
ASSINATURA = {'max_lado': 1200, 'formato': 'PNG'}


def salvar_imagem(arquivo, max_lado, formato, anterior=None):
    """
    Reduz a imagem enviada (gira conforme a câmera do celular, limita o
    tamanho), salva no banco e apaga a imagem anterior, se houver.
    Retorna a ImagemArmazenada nova.
    """
    imagem = ImageOps.exif_transpose(Image.open(arquivo))
    imagem.thumbnail((max_lado, max_lado))

    saida = io.BytesIO()
    if formato == 'JPEG':
        if imagem.mode in ('RGBA', 'LA', 'P'):
            # JPEG não tem transparência: coloca fundo branco
            imagem = imagem.convert('RGBA')
            fundo = Image.new('RGB', imagem.size, 'white')
            fundo.paste(imagem, mask=imagem.split()[-1])
            imagem = fundo
        imagem.convert('RGB').save(saida, 'JPEG', quality=82, optimize=True, progressive=True)
        tipo = 'image/jpeg'
    else:
        imagem.save(saida, 'PNG', optimize=True)
        tipo = 'image/png'

    nova = ImagemArmazenada.objects.create(dados=saida.getvalue(), tipo=tipo)
    if anterior is not None:
        anterior.delete()
    return nova


def responder_imagem(imagem):
    """
    Resposta HTTP com a imagem. Cada upload gera um id novo, e as URLs levam
    esse id (?v=<id>), então o navegador pode guardar a imagem em cache por
    bastante tempo sem risco de mostrar uma versão antiga.
    """
    resposta = HttpResponse(bytes(imagem.dados), content_type=imagem.tipo)
    resposta['Cache-Control'] = 'public, max-age=2592000'  # 30 dias
    return resposta


def caminho_temporario(imagem):
    """
    Grava a imagem numa pasta temporária (permitida inclusive no Vercel) e
    devolve o caminho, para o código dos PDFs que trabalha com arquivos.
    O nome leva um hash do conteúdo: o arquivo só é reaproveitado se for
    exatamente a mesma imagem (só o id não basta — outro banco, como um de
    teste ou um backup restaurado, pode ter uma imagem diferente com o mesmo id).
    """
    if imagem is None:
        return None
    dados = bytes(imagem.dados)
    impressao = hashlib.sha1(dados).hexdigest()[:16]
    caminho = os.path.join(tempfile.gettempdir(), f"mundokids_img_{impressao}.{imagem.extensao}")
    if not os.path.exists(caminho):
        with open(caminho, 'wb') as arquivo:
            arquivo.write(dados)
    return caminho
