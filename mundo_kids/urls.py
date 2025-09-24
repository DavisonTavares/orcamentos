from django.urls import path, include
from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("", include("accounts.urls")),
    path("admin/", admin.site.urls),
    path("orcamentos/", include("orcamentos.urls")),
    path('accounts/', include('accounts.urls')),
    path('relatorios/', include('relatorios.urls')),
]

if settings.DEBUG:
    from django.conf import settings
    from django.conf.urls.static import static
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)