from django.contrib import admin
from .models import Cliente, Item, Orcamento, OrcamentoItem

@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ['nome', 'telefone', 'data_cadastro']
    list_filter = ['data_cadastro']
    search_fields = ['nome', 'telefone']
    list_per_page = 20

@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ['descricao', 'valor_unitario', 'desconto', 'categoria', 'disponivel']
    list_filter = ['categoria', 'disponivel']
    search_fields = ['descricao']
    list_editable = ['valor_unitario', 'desconto', 'disponivel']
    list_per_page = 20

class OrcamentoItemInline(admin.TabularInline):  # ou admin.StackedInline
    model = OrcamentoItem
    extra = 1  # número de forms vazios para adicionar novos itens
    fields = ['item', 'quantidade']
    autocomplete_fields = ['item']

@admin.register(Orcamento)
class OrcamentoAdmin(admin.ModelAdmin):
    list_display = ['id', 'cliente', 'data_criacao', 'data_evento', 'status', 'calcular_total']
    list_filter = ['data_criacao', 'data_evento', 'status']
    search_fields = ['cliente__nome', 'observacoes']
    list_editable = ['status']
    readonly_fields = ['data_criacao', 'calcular_total_display']
    inlines = [OrcamentoItemInline]
    fieldsets = [
        ('Informações Básicas', {
            'fields': ['cliente', 'data_evento', 'status']
        }),
        ('Valores', {
            'fields': ['desconto_geral', 'calcular_total_display']
        }),
        ('Arquivos', {
            'fields': ['pdf', 'png'],
            'classes': ['collapse']
        }),
        ('Observações', {
            'fields': ['observacoes'],
            'classes': ['collapse']
        }),
    ]
    
    def calcular_total_display(self, obj):
        return f"R$ {obj.calcular_total():.2f}"
    calcular_total_display.short_description = 'Total do Orçamento'
    
    # Para exibir o total na listagem
    def calcular_total(self, obj):
        return f"R$ {obj.calcular_total():.2f}"
    calcular_total.short_description = 'Total'

@admin.register(OrcamentoItem)
class OrcamentoItemAdmin(admin.ModelAdmin):
    list_display = ['orcamento', 'item', 'quantidade', 'subtotal']
    list_filter = ['item__categoria']
    search_fields = ['orcamento__cliente__nome', 'item__descricao']
    
    def subtotal(self, obj):
        valor_item = obj.quantidade * obj.item.valor_unitario
        desconto_item = valor_item * (obj.item.desconto / 100)
        return f"R$ {valor_item - desconto_item:.2f}"
    subtotal.short_description = 'Subtotal'