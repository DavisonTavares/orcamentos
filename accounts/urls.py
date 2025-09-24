# accounts/urls.py
from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

app_name = 'accounts'

urlpatterns = [
    path('', views.home, name='home'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('cadastro/', views.CadastroEmpresaUsuarioView.as_view(), name='cadastro_empresa'),
    path('usuarios/novo/', views.CriarUsuarioEmpresaView.as_view(), name='criar_usuario_empresa'),
    path('usuarios/', views.lista_usuarios, name='lista_usuarios'),
    path('perfil/', views.perfil_usuario, name='perfil'),
    path('perfil/alterar-senha/', views.alterar_senha, name='alterar_senha'),
    path('configuracoes/empresa/', views.configuracoes_empresa, name='configuracoes_empresa'),
]