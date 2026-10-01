def _hex_para_rgb(cor, padrao):
    """'#2463EB' -> '36, 99, 235' (para usar em rgba(var(--primary-rgb), .1))."""
    cor = (cor or padrao).lstrip('#')
    if len(cor) == 3:
        cor = ''.join(c * 2 for c in cor)
    try:
        return ', '.join(str(int(cor[i:i + 2], 16)) for i in (0, 2, 4))
    except ValueError:
        return _hex_para_rgb(padrao, padrao)


def empresa_theme(request):
    primary, secondary, accent, dark_mode = '#2463EB', '#4ECDC4', '#FF6B6B', False
    if hasattr(request, 'user') and request.user.is_authenticated:
        if hasattr(request.user, 'empresa') and request.user.empresa:
            empresa = request.user.empresa
            primary = empresa.cor_principal or primary
            secondary = empresa.cor_secundaria or secondary
            accent = empresa.cor_acento or accent
            dark_mode = empresa.tema_escuro or False

    return {
        'empresa_theme': {
            'primary': primary,
            'secondary': secondary,
            'accent': accent,
            'primary_rgb': _hex_para_rgb(primary, '#2463EB'),
            'secondary_rgb': _hex_para_rgb(secondary, '#4ECDC4'),
            'accent_rgb': _hex_para_rgb(accent, '#FF6B6B'),
            'dark_mode': dark_mode,
        }
    }
