from .models import LeadCatalogo, PreOrcamento


def pedidos_catalogo(request):
    """Pedidos e interessados novos do catálogo, para o contador no menu."""
    usuario = getattr(request, 'user', None)
    if not usuario or not usuario.is_authenticated or not getattr(usuario, 'empresa_id', None):
        return {}
    return {
        'pedidos_catalogo_novos': (
            PreOrcamento.objects.filter(empresa_id=usuario.empresa_id, status='novo').count()
            + LeadCatalogo.objects.filter(empresa_id=usuario.empresa_id, status='novo').count()
        )
    }
