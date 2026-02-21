import json
import logging
from datetime import datetime

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import Message

logger = logging.getLogger(__name__)


@csrf_exempt
def webhook_recevoir_sms(request):
    """
    Endpoint webhook - reçoit les SMS depuis l'app Transitaire SMS (Android).
    Compatible avec SMS Forwarder, SMS to URL, AutoSMS et autres apps similaires.

    URL à mettre dans l'app : http://VOTRE_IP:8000/webhook/sms/

    Formats acceptés (POST) :
      - JSON : {"from": "+33612345678", "message": "Bonjour", "sentStamp": 1700000000}
      - Form data : from=+33612345678&message=Bonjour&sentStamp=1700000000
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Méthode non autorisée'}, status=405)

    # Vérification token optionnelle
    token = request.GET.get('token') or request.headers.get('X-Auth-Token')
    if settings.SMS_WEBHOOK_TOKEN and token != settings.SMS_WEBHOOK_TOKEN:
        # Pas de token = on accepte quand même (pour faciliter la config initiale)
        # Pour forcer la sécurité, décommenter la ligne ci-dessous :
        # return JsonResponse({'status': 'error', 'message': 'Token invalide'}, status=403)
        pass

    # Lecture des données (JSON ou form)
    try:
        if request.content_type and 'application/json' in request.content_type:
            data = json.loads(request.body.decode('utf-8'))
        else:
            data = request.POST.dict()
            if not data:
                data = json.loads(request.body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.error(f"Erreur décodage webhook: {e}")
        return JsonResponse({'status': 'error', 'message': 'Corps de requête invalide'}, status=400)

    # Extraction des champs (compatibilité multi-apps)
    expediteur = (
        data.get('from') or
        data.get('sender') or
        data.get('number') or
        data.get('phone') or
        'Inconnu'
    )
    contenu = (
        data.get('message') or
        data.get('msg') or
        data.get('body') or
        data.get('text') or
        data.get('sms') or
        ''
    )

    if not contenu:
        return JsonResponse({'status': 'error', 'message': 'Message vide'}, status=400)

    # Date d'envoi depuis le téléphone
    date_telephone = None
    timestamp_brut = (
        data.get('sentStamp') or
        data.get('receivedStamp') or
        data.get('timestamp') or
        data.get('date')
    )
    if timestamp_brut:
        try:
            ts = int(str(timestamp_brut)[:10])  # gère les timestamps en ms ou s
            if int(str(timestamp_brut)) > 9999999999:
                ts = int(str(timestamp_brut)) // 1000
            date_telephone = datetime.fromtimestamp(ts, tz=timezone.utc)
        except (ValueError, OSError):
            pass

    # Récupération IP source
    ip_source = (
        request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or
        request.META.get('REMOTE_ADDR')
    )

    # Enregistrement en base
    msg = Message.objects.create(
        expediteur=str(expediteur)[:50],
        contenu=contenu,
        date_reception_telephone=date_telephone,
        source_ip=ip_source or None,
    )

    logger.info(f"Nouveau SMS reçu de {expediteur} (ID={msg.id})")
    return JsonResponse({'status': 'ok', 'id': msg.id}, status=201)


@login_required
def dashboard(request):
    """Dashboard principal - liste tous les messages."""
    messages = Message.objects.all()

    # Filtre par expéditeur
    filtre_expediteur = request.GET.get('expediteur', '')
    if filtre_expediteur:
        messages = messages.filter(expediteur__icontains=filtre_expediteur)

    # Filtre non lu
    filtre_non_lu = request.GET.get('non_lu', '')
    if filtre_non_lu:
        messages = messages.filter(lu=False)

    total = Message.objects.count()
    non_lus = Message.objects.filter(lu=False).count()

    # Marquer comme lus les messages affichés (si pas de filtre)
    if not filtre_expediteur and not filtre_non_lu:
        Message.objects.filter(lu=False).update(lu=True)

    expediteurs = Message.objects.values_list('expediteur', flat=True).distinct()

    context = {
        'messages': messages[:200],
        'total': total,
        'non_lus': non_lus,
        'expediteurs': expediteurs,
        'filtre_expediteur': filtre_expediteur,
        'filtre_non_lu': filtre_non_lu,
        'webhook_url': request.build_absolute_uri('/webhook/sms/'),
    }
    return render(request, 'sms/dashboard.html', context)


@login_required
def detail_message(request, pk):
    """Détail d'un message."""
    msg = get_object_or_404(Message, pk=pk)
    msg.lu = True
    msg.save(update_fields=['lu'])
    return render(request, 'sms/detail.html', {'msg': msg})


@login_required
@require_http_methods(["POST"])
def supprimer_message(request, pk):
    """Supprime un message."""
    msg = get_object_or_404(Message, pk=pk)
    msg.delete()
    return JsonResponse({'status': 'ok'})


@login_required
def api_messages(request):
    """API JSON pour récupérer les derniers messages (polling depuis le navigateur)."""
    depuis_id = request.GET.get('depuis_id', 0)
    messages = Message.objects.filter(id__gt=depuis_id).values(
        'id', 'expediteur', 'contenu',
        'date_reception_telephone', 'date_reception_serveur', 'lu'
    )[:50]
    return JsonResponse({'messages': list(messages)})
