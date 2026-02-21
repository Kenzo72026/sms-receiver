from django.db import models


class Message(models.Model):
    expediteur = models.CharField(max_length=50, verbose_name="Expéditeur")
    contenu = models.TextField(verbose_name="Contenu du message")
    date_reception_telephone = models.DateTimeField(null=True, blank=True)
    date_reception_serveur = models.DateTimeField(auto_now_add=True)
    lu = models.BooleanField(default=False)
    source_ip = models.GenericIPAddressField(null=True, blank=True)

    # Champs extraits automatiquement du SMS
    transfer_id = models.CharField(max_length=50, blank=True, null=True, verbose_name="Transfer ID")
    montant = models.CharField(max_length=50, blank=True, null=True, verbose_name="Montant")
    numero_envoyeur = models.CharField(max_length=50, blank=True, null=True, verbose_name="Numéro envoyeur")
    nom_envoyeur = models.CharField(max_length=100, blank=True, null=True, verbose_name="Nom envoyeur")

    # Résultat de la vérification
    STATUT_CHOICES = [
        ('non_verifie', '⏳ Non vérifié'),
        ('correspond', '✅ Correspond'),
        ('ne_correspond_pas', '❌ Ne correspond pas'),
        ('non_trouve', '🔍 Non trouvé sur le site'),
    ]
    statut_verification = models.CharField(
        max_length=30, choices=STATUT_CHOICES,
        default='non_verifie', verbose_name="Statut vérification"
    )
    details_verification = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "Message SMS"
        verbose_name_plural = "Messages SMS"
        ordering = ['-date_reception_serveur']

    def __str__(self):
        return f"[{self.expediteur}] {self.contenu[:50]}"
