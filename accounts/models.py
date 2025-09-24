from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _

class Empresa(models.Model):
    nome = models.CharField(_('Nome da Empresa'), max_length=100)
    cnpj = models.CharField(_('CNPJ'), max_length=18, unique=True, blank=True, null=True)
    telefone = models.CharField(_('Telefone'), max_length=15, blank=True, null=True)
    cidade = models.CharField(_('Cidade'), max_length=100, blank=True, null=True)
    instagram = models.CharField(_('Instagram'), max_length=100, blank=True, null=True)
    whatsapp = models.CharField(_('WhatsApp'), max_length=15, blank=True, null=True)
    email = models.EmailField(_('E-mail'), blank=True, null=True)
    endereco = models.TextField(_('Endereço'), blank=True, null=True)
    data_criacao = models.DateTimeField(_('Data de Criação'), auto_now_add=True)
    ativa = models.BooleanField(_('Ativa'), default=True)
    logo = models.ImageField(upload_to='empresas/logos/', blank=True, null=True, verbose_name='Logo')
    cor_principal = models.CharField(max_length=7, default='#2463EB', verbose_name='Cor Principal')
    cor_secundaria = models.CharField(max_length=7, default='#4ECDC4', verbose_name='Cor Secundária')
    cor_acento = models.CharField(max_length=7, default='#FF6B6B', verbose_name='Cor de Acento')
    plano = models.CharField(_('Plano'), max_length=20, choices=[
        ('free', 'Free'),
        ('basic', 'Basic'),
        ('pro', 'Pro'),
        ('enterprise', 'Enterprise')
    ], default='free')
    
    # Configurações de tema
    tema_escuro = models.BooleanField(default=False, verbose_name='Tema Escuro')
    
    class Meta:
        verbose_name = _('Empresa')
        verbose_name_plural = _('Empresas')
        
    def save(self, *args, **kwargs):
        # Garantir que as cores tenham o formato correto
        for field in ['cor_principal', 'cor_secundaria', 'cor_acento']:
            color = getattr(self, field)
            if color and not color.startswith('#'):
                setattr(self, field, f'#{color}')
        super().save(*args, **kwargs)
    
    def __str__(self):
        return self.nome

class Usuario(AbstractUser):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='usuarios', verbose_name=_('Empresa'))
    telefone = models.CharField(_('Telefone'), max_length=15, blank=True, null=True)
    avatar = models.ImageField(_('Avatar'), upload_to='avatars/', blank=True, null=True)
    cargo = models.CharField(_('Cargo'), max_length=50, blank=True, null=True)
    data_nascimento = models.DateField(_('Data de Nascimento'), blank=True, null=True)
    email_confirmado = models.BooleanField(_('E-mail Confirmado'), default=False)
    
    class Meta:
        verbose_name = _('Usuário')
        verbose_name_plural = _('Usuários')
    
    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.empresa.nome})"

