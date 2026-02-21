import json
import logging
from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import Message

logger = logging.getLogger(__name__)


@csrf_exempt
def webhook_recevoir_sms(request):
    """
    Webhook universel - accepte TOUT format envoyé par n'importe quelle app SMS.
    URL : https://sms-receiver-0a3f.onrender.com/webhook/sms/
    """

    # ---- Collecte toutes les données de TOUTES les sources ----
    data = {}

    # 1. Paramètres dans l'URL (?from=xxx&message=yyy)
    data.update(request.GET.dict())

    # 2. Corps POST (JSON ou form-data)
    if request.method == 'POST':
        # Essai JSON
        try:
            body_str = request.body.decode('utf-8').strip()
            if body_str:
                parsed = json.loads(body_str)
                if isinstance(parsed, dict):
                    data.update(parsed)
        except Exception:
            pass

        # Essai form-data
        try:
            if request.POST:
                data.update(request.POST.dict())
        except Exception:
            pass

    # Log complet pour debug
    logger.info(f"[WEBHOOK] methode={request.method} content_type={request.content_type}")
    logger.info(f"[WEBHOOK] donnees={json.dumps(data, ensure_ascii=False)}")
    logger.info(f"[WEBHOOK] body_brut={request.body[:300]}")

    # ---- Extraction expéditeur ----
    expediteur = (
        data.get('from') or data.get('sender') or data.get('number') or
        data.get('phone') or data.get('phonenumber') or data.get('msisdn') or
        data.get('from_number') or data.get('source') or data.get('originator') or
        'Inconnu'
    )

    # Ignorer les valeurs non substituées comme {sender}
    if expediteur and expediteur.startswith('{') and expediteur.endswith('}'):
        expediteur = 'Inconnu'

    # ---- Extraction contenu ----
    contenu = (
        data.get('message') or data.get('msg') or data.get('body') or
        data.get('text') or data.get('sms') or data.get('content') or
        data.get('sms_message') or data.get('messagetext') or
        data.get('message_text') or data.get('sms_body') or
        data.get('Message') or data.get('Text') or data.get('Body') or ''
    )

    # Ignorer les valeurs non substituées
    if contenu and contenu.startswith('{') and contenu.endswith('}'):
        contenu = ''

    # Si toujours vide, sauvegarder quand même avec les données brutes
    if not contenu:
        contenu = f"[Données reçues: {json.dumps(data, ensure_ascii=False)}]"

    # ---- Date ----
    date_telephone = None
    ts_brut = (
        data.get('sentStamp') or data.get('receivedStamp') or
        data.get('timestamp') or data.get('date') or data.get('time')
    )
    if ts_brut:
        try:
            ts = int(str(ts_brut))
            if ts > 9999999999:
                ts = ts // 1000
            date_telephone = datetime.fromtimestamp(ts, tz=timezone.utc)
        except Exception:
            pass

    # ---- IP source ----
    ip_source = (
        request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or
        request.META.get('REMOTE_ADDR')
    )

    # ---- Sauvegarde ----
    msg = Message.objects.create(
        expediteur=str(expediteur)[:50],
        contenu=contenu,
        date_reception_telephone=date_telephone,
        source_ip=ip_source or None,
    )

    logger.info(f"[WEBHOOK] SMS sauvegarde ID={msg.id} de={expediteur}")
    return JsonResponse({'status': 'ok', 'id': msg.id}, status=201)


@login_required
def dashboard(request):
    messages_qs = Message.objects.all()
    filtre_expediteur = request.GET.get('expediteur', '')
    if filtre_expediteur:
        messages_qs = messages_qs.filter(expediteur__icontains=filtre_expediteur)
    filtre_non_lu = request.GET.get('non_lu', '')
    if filtre_non_lu:
        messages_qs = messages_qs.filter(lu=False)
    total = Message.objects.count()
    non_lus = Message.objects.filter(lu=False).count()
    if not filtre_expediteur and not filtre_non_lu:
        Message.objects.filter(lu=False).update(lu=True)
    expediteurs = Message.objects.values_list('expediteur', flat=True).distinct()
    context = {
        'messages': messages_qs[:200],
        'total': total,
        'non_lus': non_lus,
        'expediteurs': expediteurs,
        'filtre_expediteur': filtre_expediteur,
        'filtre_non_lu': filtre_non_lu,
        'webhook_url': 'https://sms-receiver-0a3f.onrender.com/webhook/sms/',
    }
    return render(request, 'sms/dashboard.html', context)


@login_required
def detail_message(request, pk):
    msg = get_object_or_404(Message, pk=pk)
    msg.lu = True
    msg.save(update_fields=['lu'])
    return render(request, 'sms/detail.html', {'msg': msg})


@login_required
@require_http_methods(["POST"])
def supprimer_message(request, pk):
    msg = get_object_or_404(Message, pk=pk)
    msg.delete()
    return JsonResponse({'status': 'ok'})


@login_required
def api_messages(request):
    depuis_id = request.GET.get('depuis_id', 0)
    msgs = Message.objects.filter(id__gt=depuis_id).values(
        'id', 'expediteur', 'contenu',
        'date_reception_telephone', 'date_reception_serveur', 'lu'
    )[:50]
    return JsonResponse({'messages': list(msgs)})


def ping(request):
    return JsonResponse({'status': 'ok', 'total_sms': Message.objects.count()})
