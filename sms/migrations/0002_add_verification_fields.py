from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sms', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='message',
            name='transfer_id',
            field=models.CharField(blank=True, max_length=50, null=True, verbose_name='Transfer ID'),
        ),
        migrations.AddField(
            model_name='message',
            name='montant',
            field=models.CharField(blank=True, max_length=50, null=True, verbose_name='Montant'),
        ),
        migrations.AddField(
            model_name='message',
            name='numero_envoyeur',
            field=models.CharField(blank=True, max_length=50, null=True, verbose_name='Numéro envoyeur'),
        ),
        migrations.AddField(
            model_name='message',
            name='nom_envoyeur',
            field=models.CharField(blank=True, max_length=100, null=True, verbose_name='Nom envoyeur'),
        ),
        migrations.AddField(
            model_name='message',
            name='statut_verification',
            field=models.CharField(
                choices=[
                    ('non_verifie', '⏳ Non vérifié'),
                    ('correspond', '✅ Correspond'),
                    ('ne_correspond_pas', '❌ Ne correspond pas'),
                    ('non_trouve', '🔍 Non trouvé sur le site'),
                ],
                default='non_verifie',
                max_length=30,
                verbose_name='Statut vérification',
            ),
        ),
        migrations.AddField(
            model_name='message',
            name='details_verification',
            field=models.TextField(blank=True, null=True),
        ),
    ]
