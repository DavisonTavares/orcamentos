import re

# Trechos em que espaços/quebras de linha importam e não podem ser mexidos
_TRECHOS_PROTEGIDOS = re.compile(r"(<(pre|textarea|script)\b.*?</\2\s*>)", re.IGNORECASE | re.DOTALL)
# Indentação no começo das linhas e espaços no fim delas
_INDENTACAO = re.compile(r"[ \t]*\n[ \t]+|[ \t]+\n")
# Três ou mais quebras de linha seguidas viram uma linha em branco só
_LINHAS_EM_BRANCO = re.compile(r"\n{3,}")


def compactar_html(html):
    """
    Remove a indentação dos templates (mais da metade do tamanho de páginas
    como a de agendamentos) sem mudar o que o navegador mostra: o HTML já
    trata "quebra de linha + espaços" como um espaço só. <pre>, <textarea>
    e <script> ficam intactos, porque neles os espaços fazem diferença.
    """
    partes = _TRECHOS_PROTEGIDOS.split(html)
    resultado = []
    # split com 2 grupos devolve: [texto, trecho_protegido, nome_da_tag, texto, ...]
    for i in range(0, len(partes), 3):
        texto = _INDENTACAO.sub("\n", partes[i])
        resultado.append(_LINHAS_EM_BRANCO.sub("\n\n", texto))
        if i + 1 < len(partes):
            resultado.append(partes[i + 1])
    return "".join(resultado)


class CompactarHTMLMiddleware:
    """Aplica compactar_html nas respostas HTML (antes do GZip comprimir)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if (
            not response.streaming
            and response.status_code == 200
            and "text/html" in response.get("Content-Type", "")
            and not response.has_header("Content-Encoding")
        ):
            charset = response.charset or "utf-8"
            html = response.content.decode(charset)
            response.content = compactar_html(html).encode(charset)
            if response.has_header("Content-Length"):
                response["Content-Length"] = str(len(response.content))
        return response
