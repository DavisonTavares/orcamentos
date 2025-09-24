from django import forms
from .models import Cliente, Item, Orcamento, OrcamentoItem

class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ['nome', 'telefone']
        widgets = {
            'nome': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nome completo do cliente'
            }),
            'telefone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '(00) 00000-0000'
            }),
        }
        labels = {
            'nome': 'Nome',
            'telefone': 'Telefone',
        }
    
    def __init__(self, *args, **kwargs):
        self.empresa = kwargs.pop('empresa', None)
        
        super().__init__(*args, **kwargs)
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.empresa:
            instance.empresa = self.empresa
        if commit:
            instance.save()
        return instance

class ItemForm(forms.ModelForm):
    class Meta:
        model = Item
        fields = ['nome', 'descricao', 'valor_unitario', 'desconto', 'categoria', 'disponivel', 'investimento', 'custo_fixo', 'percentual_lucro']
        widgets = {
            'nome': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nome do item (opcional)'
            }),
            'descricao': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Descrição do item'
            }),
            'valor_unitario': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '0.00',
                'step': '0.01',
                'min': '0'
            }),
            'desconto': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '0',
                'step': '1',
                'min': '0',
                'max': '100'
            }),
            'categoria': forms.Select(attrs={
                'class': 'form-control'
            }),
            'disponivel': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'investimento': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '0.00',
                'step': '0.01',
                'min': '0'
            }),
            'custo_fixo': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '0.00',
                'step': '0.01',
                'min': '0'
            }),
            'percentual_lucro': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '0',
                'step': '0.01',
                'min': '0',
                'max': '100'
            }),
        }
        labels = {
            'nome': 'Nome (opcional)',
            'descricao': 'Descrição',
            'valor_unitario': 'Valor Unitário',
            'desconto': 'Desconto (%)',
            'categoria': 'Categoria',
            'disponivel': 'Disponível',
            'investimento': 'Investimento (custo do item)',
            'custo_fixo': 'Custo Fixo',
            'percentual_lucro': 'Percentual de Lucro (%)',
        }
    
    def __init__(self, *args, **kwargs):
        self.empresa = kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.empresa:
            instance.empresa = self.empresa
        if commit:
            instance.save()
        return instance

class OrcamentoForm(forms.ModelForm):
    class Meta:
        model = Orcamento
        fields = ['cliente', 'desconto_geral', 'observacoes', 'data_evento',
                  'hora_evento', 'periodo_evento', 'tipo_evento', 'valor_adicional',
                  'endereco', 'valor_pago', 'custo_operacional']
        widgets = {
            'cliente': forms.Select(attrs={
                'class': 'form-control'
            }),
            'desconto_geral': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '0',
                'step': '1',
                'min': '0',
                'max': '100'
            }),
            'observacoes': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Observações adicionais...',
                'rows': 4
            }),
            'data_evento': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'hora_evento': forms.TimeInput(attrs={
                'class': 'form-control',
                'type': 'time',
                'value': '16:00'
            }),
            'periodo_evento': forms.Select(attrs={
                'class': 'form-control',
            }, choices=[('1', '1 hora'), ('2', '2 horas'), ('3', '3 horas'), 
                       ('4', '4 horas'), ('5', '5 horas'), ('6', '6 horas')]),
            'tipo_evento': forms.Select(attrs={
                'class': 'form-control',
                'choices': [
                    ('Aniversário', 'Aniversário'),
                    ('Casamento', 'Casamento'),
                    ('Corporativo', 'Corporativo'),
                    ('Evento Público', 'Evento Público'),
                    ('Outro', 'Outro')
                ]
            }),
            'valor_adicional': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '0.00',
                'step': '0.01',
                'min': '0'
            }),
            'endereco': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Endereço completo do evento',
                'rows': 2
            }),
            'valor_pago': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '0.00',
                'step': '0.5',
                'min': '0'
            }),
            'custo_operacional': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '0.00',
                'step': '0.01',
                'min': '0'
            }),
        }
        labels = {
            'cliente': 'Cliente',
            'desconto_geral': 'Desconto Geral (%)',
            'observacoes': 'Observações',
            'data_evento': 'Data do Evento',
            'hora_evento': 'Hora do Evento',
            'periodo_evento': 'Duração do Evento (horas)',
            'tipo_evento': 'Tipo do Evento',
            'valor_adicional': 'Valor Adicional (R$)',
            'endereco': 'Endereço do Evento', 
            'valor_pago': 'Valor Pago (R$)',   
            'custo_operacional': 'Custo Operacional (R$)',        
        }
    
    def __init__(self, *args, **kwargs):
        self.empresa = kwargs.pop('empresa', None)
        self.usuario = kwargs.pop('usuario', None)
        super().__init__(*args, **kwargs)
        
        # Filtrar clientes apenas da empresa do usuário
        if self.empresa:
            self.fields['cliente'].queryset = Cliente.objects.filter(empresa=self.empresa)
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.empresa:
            instance.empresa = self.empresa
        if self.usuario:
            instance.criado_por = self.usuario
        if commit:
            instance.save()
        return instance

class OrcamentoItemForm(forms.ModelForm):
    class Meta:
        model = OrcamentoItem
        fields = ['item', 'quantidade', 'valor', 'desconto']
        widgets = {
            'item': forms.Select(attrs={
                'class': 'form-control'
            }),
            'quantidade': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'value': '1'
            }),
            'valor': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '0.00',
                'step': '0.01',
                'min': '0'
            }),
            'desconto': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '0',
                'step': '1',
                'min': '0',
                'max': '100'
            }),
        }
        labels = {
            'item': 'Item',
            'quantidade': 'Quantidade',
            'valor': 'Valor Unitário (R$)',
            'desconto': 'Desconto (%)',
        }
    
    def __init__(self, *args, **kwargs):
        self.empresa = kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)
        
        # Filtrar itens apenas da empresa do usuário
        if self.empresa:
            self.fields['item'].queryset = Item.objects.filter(empresa=self.empresa, disponivel=True)

# Formulário para busca de orçamentos
class OrcamentoSearchForm(forms.Form):
    STATUS_CHOICES = [
        ('all', 'Todos'),
        ('pendente', 'Pendentes'),
        ('confirmado', 'Confirmados'),
        ('concluido', 'Concluídos'),
        ('cancelado', 'Cancelados'),
    ]
    
    SORT_CHOICES = [
        ('recentes', 'Mais recentes'),
        ('antigos', 'Mais antigos'),
        ('valor-maior', 'Maior valor'),
        ('valor-menor', 'Menor valor'),
        ('proximo-evento', 'Próximo evento'),
    ]
    
    q = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Buscar por cliente, telefone, observações...'
        }),
        label='Buscar'
    )
    
    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-control'
        }),
        initial='all',
        label='Status'
    )
    
    sort = forms.ChoiceField(
        choices=SORT_CHOICES,
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-control'
        }),
        initial='recentes',
        label='Ordenar por'
    )

# Formulário para filtro de agendamentos
class AgendamentoFilterForm(forms.Form):
    STATUS_CHOICES = [
        ('todos', 'Todos'),
        ('confirmado', 'Confirmados'),
        ('concluido', 'Concluídos'),
    ]
    
    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-control'
        }),
        initial='todos',
        label='Status'
    )
    
    data = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        }),
        label='Data específica'
    )

# Formulário para conclusão de agendamento
class ConcluirAgendamentoForm(forms.Form):
    observacoes_conclusao = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'placeholder': 'Observações sobre a conclusão do evento...',
            'rows': 4
        }),
        label='Observações da Conclusão'
    )

# Formulário para cadastro rápido de cliente (modal)
class ClienteRapidoForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ['nome', 'telefone']
        widgets = {
            'nome': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nome do cliente',
                'required': 'required'
            }),
            'telefone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '(00) 00000-0000',
                'required': 'required'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        self.empresa = kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.empresa:
            instance.empresa = self.empresa
        if commit:
            instance.save()
        return instance

# Formulário para cadastro rápido de item (modal)
class ItemRapidoForm(forms.ModelForm):
    class Meta:
        model = Item
        fields = ['nome', 'descricao', 'valor_unitario', 'categoria']
        widgets = {
            'nome': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nome do item (opcional)'
            }),
            'descricao': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Descrição do item',
                'required': 'required'
            }),
            'valor_unitario': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '0.00',
                'step': '0.01',
                'min': '0',
                'required': 'required'
            }),
            'categoria': forms.Select(attrs={
                'class': 'form-control',
                'required': 'required'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        self.empresa = kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.empresa:
            instance.empresa = self.empresa
        if commit:
            instance.save()
        return instance