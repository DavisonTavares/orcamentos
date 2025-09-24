def empresa_theme(request):
    if hasattr(request, 'user') and request.user.is_authenticated:
        if hasattr(request.user, 'empresa') and request.user.empresa:
            empresa = request.user.empresa
            return {
                'empresa_theme': {
                    'primary': empresa.cor_principal or '#2463EB',
                    'secondary': empresa.cor_secundaria or '#4ECDC4',
                    'accent': empresa.cor_acento or '#FF6B6B',
                    'dark_mode': empresa.tema_escuro or False,
                }
            }
    
    # Valores padrão
    return {
        'empresa_theme': {
            'primary': '#2463EB',
            'secondary': '#4ECDC4',
            'accent': '#FF6B6B',
            'dark_mode': False,
        }
    }