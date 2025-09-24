from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError
from .models import Usuario, Empresa
from django.contrib.auth.forms import PasswordChangeForm
from django.core.files.images import get_image_dimensions

class EmpresaForm(forms.ModelForm):
    termos = forms.BooleanField(
        required=False,
        error_messages={'required': 'Você deve aceitar os termos de uso.'}
    )
    
    class Meta:
        model = Empresa
        fields = ['nome', 'cnpj', 'telefone', 'email', 'endereco', 'logo', 
                 'cor_principal', 'cor_secundaria', 'cor_acento', 'tema_escuro', 'cidade', 'instagram', 'whatsapp']
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-control'}),
            'cnpj': forms.TextInput(attrs={'class': 'form-control'}),
            'telefone': forms.TextInput(attrs={'class': 'form-control'}),
            'cidade': forms.TextInput(attrs={'class': 'form-control'}),
            'instagram': forms.TextInput(attrs={'class': 'form-control'}),
            'whatsapp': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'endereco': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'logo': forms.FileInput(attrs={'class': 'form-control'}),
            'cor_principal': forms.TextInput(attrs={
                'class': 'form-control', 
                'type': 'color',
                'style': 'height: 40px;'
            }),
            'cor_secundaria': forms.TextInput(attrs={
                'class': 'form-control', 
                'type': 'color',
                'style': 'height: 40px;'
            }),
            'cor_acento': forms.TextInput(attrs={
                'class': 'form-control', 
                'type': 'color',
                'style': 'height: 40px;'
            }),
            'tema_escuro': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def clean_logo(self):
        logo = self.cleaned_data.get('logo')
        if logo:
            try:
                # Verificar se é uma imagem válida
                w, h = get_image_dimensions(logo)
                if w > 500 or h > 500:
                    raise forms.ValidationError("A logo deve ter no máximo 500x500 pixels.")
            except (AttributeError, TypeError):
                pass
        return logo

class CustomPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            self.fields[field].widget.attrs.update({'class': 'form-control'})

class UsuarioRegistrationForm(UserCreationForm):
    email = forms.EmailField(
        max_length=254,
        help_text='Obrigatório. Informe um email válido.',
        widget=forms.EmailInput(attrs={'placeholder': 'seu@email.com'})
    )
    
    class Meta:
        model = Usuario
        fields = ('first_name', 'last_name', 'email', 'password1', 'password2')
        widgets = {
            'first_name': forms.TextInput(attrs={'placeholder': 'Seu nome'}),
            'last_name': forms.TextInput(attrs={'placeholder': 'Seu sobrenome'}),
        }
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if Usuario.objects.filter(email=email).exists():
            raise ValidationError("Este email já está em uso.")
        return email

class CadastroCompletoForm(forms.Form):
    # Campos da empresa
    empresa_nome = forms.CharField(max_length=100, widget=forms.TextInput(attrs={'placeholder': 'Nome da empresa'}))
    empresa_cnpj = forms.CharField(max_length=18, required=False, widget=forms.TextInput(attrs={'placeholder': 'CNPJ (opcional)'}))
    empresa_telefone = forms.CharField(max_length=15, widget=forms.TextInput(attrs={'placeholder': 'Telefone da empresa'}))
    
    # Campos do usuário
    first_name = forms.CharField(max_length=30, widget=forms.TextInput(attrs={'placeholder': 'Seu nome'}))
    last_name = forms.CharField(max_length=30, widget=forms.TextInput(attrs={'placeholder': 'Seu sobrenome'}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={'placeholder': 'Seu email'}))
    password1 = forms.CharField(widget=forms.PasswordInput(attrs={'placeholder': 'Crie uma senha'}))
    password2 = forms.CharField(widget=forms.PasswordInput(attrs={'placeholder': 'Confirme sua senha'}))
    
    # Termos
    termos = forms.BooleanField(required=True)