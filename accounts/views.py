from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib.auth.views import LoginView as AuthLoginView
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.generic import CreateView, FormView
from django.urls import reverse_lazy
from .models import Empresa, Usuario
from .forms import CadastroCompletoForm, EmpresaForm, UsuarioRegistrationForm
from django.contrib.auth import update_session_auth_hash
from django.contrib import messages
from .forms import UsuarioRegistrationForm, EmpresaForm, CustomPasswordChangeForm

@login_required
def perfil_usuario(request):
    if request.method == 'POST':
        form = UsuarioRegistrationForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Perfil atualizado com sucesso!')
            return redirect('accounts:perfil')
    else:
        form = UsuarioRegistrationForm(instance=request.user)
    
    return render(request, 'accounts/perfil.html', {'form': form})

@login_required
def alterar_senha(request):
    if request.method == 'POST':
        form = CustomPasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, 'Senha alterada com sucesso!')
            return redirect('accounts:perfil')
    else:
        form = CustomPasswordChangeForm(request.user)
    
    return render(request, 'accounts/alterar_senha.html', {'form': form})

@login_required
def configuracoes_empresa(request):
    if not hasattr(request.user, 'empresa'):
        messages.error(request, 'Você não tem uma empresa associada.')
        return redirect('accounts:perfil')
    
    empresa = request.user.empresa
    
    if request.method == 'POST':
        form = EmpresaForm(request.POST, request.FILES, instance=empresa)
        
        if form.is_valid():
            try:
                form.save()
                messages.success(request, '✅ Configurações da empresa atualizadas com sucesso!')
                return redirect('accounts:configuracoes_empresa')
            except Exception as e:
                messages.error(request, f'❌ Erro ao salvar: {str(e)}')
        
        else:
            # Debug no console (opcional)
            #print(f"Formulário inválido. Erros: {form.errors}")
            
            # Mensagens detalhadas para o usuário
            messages.error(request, '❌ Por favor, corrija os erros abaixo:')
            
            for field_name, errors in form.errors.items():
                for error in errors:
                    field_label = form.fields[field_name].label if field_name in form.fields else field_name
                    messages.error(request, f"• {field_label}: {error}")
    
    else:
        form = EmpresaForm(instance=empresa)
    
    return render(request, 'accounts/configuracoes_empresa.html', {
        'form': form,
        'empresa': empresa
    })
    

class LoginView(AuthLoginView):
    template_name = 'accounts/login.html'
    redirect_authenticated_user = True
    
    def get_success_url(self):
        return reverse_lazy('orcamentos:lista_orcamentos')  # Ou a URL que você quiser

#@method_decorator(login_required, name='dispatch')
class CadastroEmpresaUsuarioView(FormView):
    template_name = 'accounts/cadastro.html'
    form_class = CadastroCompletoForm
    success_url = reverse_lazy('orcamentos:lista_orcamentos')
    
    def form_valid(self, form):
        # 1. Criar a empresa
        empresa = Empresa.objects.create(
            nome=form.cleaned_data['empresa_nome'],
            cnpj=form.cleaned_data['empresa_cnpj'],
            telefone=form.cleaned_data['empresa_telefone']
        )
        
        # 2. Criar o usuário
        usuario = Usuario.objects.create_user(
            first_name=form.cleaned_data['first_name'],
            last_name=form.cleaned_data['last_name'],
            email=form.cleaned_data['email'],
            password=form.cleaned_data['password1'],
            empresa=empresa,
            username=form.cleaned_data['email']  # Usar email como username
        )
        
        # 3. Fazer login automaticamente
        login(self.request, usuario)
        
        return redirect(self.success_url)

#@method_decorator(login_required, name='dispatch')
class CriarUsuarioEmpresaView(FormView):
    template_name = 'accounts/novo_usuario.html'
    form_class = UsuarioRegistrationForm
    success_url = reverse_lazy('accounts:lista_usuarios')
    
    def form_valid(self, form):
        # Associar automaticamente à empresa do usuário logado
        form.instance.empresa = self.request.user.empresa
        form.instance.username = form.cleaned_data['email']
        return super().form_valid(form)

# View para listar usuários da empresa
@login_required
def lista_usuarios(request):
    usuarios = Usuario.objects.filter(empresa=request.user.empresa)
    return render(request, 'accounts/lista_usuarios.html', {'usuarios': usuarios})

@login_required
def home(request):
    return redirect('orcamentos:lista_orcamentos')
