from django.contrib import admin
from .models import Message


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ['expediteur', 'contenu_court', 'date_reception_telephone', 'date_reception_serveur', 'lu']
    list_filter = ['lu', 'date_reception_serveur', 'expediteur']
    search_fields = ['expediteur', 'contenu']
    readonly_fields = ['date_reception_serveur', 'source_ip']
    list_per_page = 50

    def contenu_court(self, obj):
        return obj.contenu[:80] + '...' if len(obj.contenu) > 80 else obj.contenu
    contenu_court.short_description = "Message"
