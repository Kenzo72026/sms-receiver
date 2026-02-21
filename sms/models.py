from django.db import models


class Message(models.Model):
    expediteur = models.CharField(max_length=50, verbose_name="Expéditeur")
    contenu = models.TextField(verbose_name="Contenu du message")
    date_reception_telephone = models.DateTimeField(
        null=True, blank=True,
        verbose_name="Date de réception (téléphone)"
    )
    date_reception_serveur = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de réception (serveur)"
    )
    lu = models.BooleanField(default=False, verbose_name="Lu")
    source_ip = models.GenericIPAddressField(
        null=True, blank=True,
        verbose_name="IP source"
    )

    class Meta:
        verbose_name = "Message SMS"
        verbose_name_plural = "Messages SMS"
        ordering = ['-date_reception_serveur']

    def __str__(self):
        return f"[{self.expediteur}] {self.contenu[:50]}"
