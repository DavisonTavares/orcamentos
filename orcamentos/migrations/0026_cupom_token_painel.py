from django.db import migrations, models

import orcamentos.models


def preencher_tokens(apps, schema_editor):
    """Cada cupom que já existe ganha o seu próprio código de painel."""
    Cupom = apps.get_model('orcamentos', 'Cupom')
    for cupom in Cupom.objects.filter(token_painel__isnull=True):
        cupom.token_painel = orcamentos.models.gerar_token_catalogo()
        cupom.save(update_fields=['token_painel'])


class Migration(migrations.Migration):

    dependencies = [
        ('orcamentos', '0025_cupons'),
    ]

    operations = [
        migrations.AddField(
            model_name='cupom',
            name='token_painel',
            field=models.CharField(max_length=32, null=True),
        ),
        migrations.RunPython(preencher_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='cupom',
            name='token_painel',
            field=models.CharField(default=orcamentos.models.gerar_token_catalogo, max_length=32, unique=True),
        ),
    ]
