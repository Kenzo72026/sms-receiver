import json
import logging
import re
import requests
from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import Message

logger = logging.getLogger(__name__)


def extraire_infos_sms(contenu):
    """Extrait Transfer ID, montant, numéro et nom depuis le SMS WAAFI/SALAAMBANK."""
    infos = {
        'transfer_id': None,
        'montant': None,
        'numero_envoyeur': None,
        'nom_envoyeur': None,
    }

    # Transfer ID
    m = re.search(r'Transfer-Id[:\s]+(\d+)', contenu, re.IGNORECASE)
    if m:
        infos['transfer_id'] = m.group(1)

    # Montant (ex: DJF 100)
    m = re.search(r'Received\s+([\w\s]+?)\s+from', contenu, re.IGNORECASE)
    if m:
        infos['montant'] = m.group(1).strip()

    # Nom et numéro (ex: Kenedid Yacin Boulaleh(77280597))
    m = re.search(r'from\s+([A-Za-z\s]+)\((\d+)\)', contenu, re.IGNORECASE)
    if m:
        infos['nom_envoyeur'] = m.group(1).strip()
        infos['numero_envoyeur'] = m.group(2).strip()

    return infos


def verifier_sur_site(transfer_id, montant, numero):
    """
    Se connecte sur my-managment.com et vérifie si la transaction correspond.
    Retourne (correspond: bool, details: str, donnees_site: dict)
    """
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Content-Type': 'application/json',
    })

    try:
        # 1. Connexion
        login_resp = session.post(
            'https://my-managment.com/api/auth/login',
            json={'username': 'Waafi_Booker_Main', 'password': 'e5FdYjEkJD'},
            timeout=15
        )

        if login_resp.status_code not in (200, 201):
            # Essai avec un autre endpoint
            login_resp = session.post(
                'https://my-managment.com/api/signin',
                json={'login': 'Waafi_Booker_Main', 'password': 'e5FdYjEkJD'},
                timeout=15
            )

        logger.info(f"Login status: {login_resp.status_code}")

        # 2. Récupérer les pending deposits
        endpoints = [
            'https://my-managment.com/api/payment/pending-deposits',
            'https://my-managment.com/api/deposits/pending',
            'https://my-managment.com/api/transactions/pending',
        ]

        transactions = []
        for endpoint in endpoints:
            try:
                resp = session.get(endpoint, timeout=15)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list):
                        transactions = data
                    elif isinstance(data, dict):
                        transactions = data.get('data', data.get('items', data.get('transactions', [])))
                    if transactions:
                        break
            except Exception:
                continue

        # 3. Chercher la transaction correspondante
        for t in transactions:
            t_str = json.dumps(t).lower()
            id_match = transfer_id and str(transfer_id) in t_str
            montant_num = re.search(r'\d+', montant or '').group() if montant else None
            montant_match = montant_num and montant_num in t_str
            numero_match = numero and str(numero) in t_str

            if id_match or (montant_match and numero_match):
                return True, f"Transaction trouvée : {json.dumps(t, ensure_ascii=False)}", t

        if transactions:
            return False, f"{len(transactions)} transactions trouvées mais aucune ne correspond", {}
        else:
            return False, "Impossible de récupérer les transactions du site", {}

    except Exception as e:
        logger.error(f"Erreur vérification site: {e}")
        return False, f"Erreur de connexion au site: {str(e)}", {}


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

    # ---- Extraction infos SMS ----
    infos = extraire_infos_sms(contenu)

    # ---- Sauvegarde ----
    msg = Message.objects.create(
        expediteur=str(expediteur)[:50],
        contenu=contenu,
        source_ip=ip_source or None,
        transfer_id=infos['transfer_id'],
        montant=infos['montant'],
        numero_envoyeur=infos['numero_envoyeur'],
        nom_envoyeur=infos['nom_envoyeur'],
        statut_verification='non_verifie',
    )

    logger.info(f"[WEBHOOK] SMS sauvegarde ID={msg.id} transfer_id={infos['transfer_id']} montant={infos['montant']} de={expediteur}")
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
        'id', 'expediteur', 'contenu', 'transfer_id', 'montant',
        'numero_envoyeur', 'nom_envoyeur', 'statut_verification',
        'date_reception_telephone', 'date_reception_serveur', 'lu'
    )[:50]
    return JsonResponse({'messages': list(msgs)})


@login_required
def verifier_transaction(request, pk):
    """Lance la vérification d'un SMS sur my-managment.com."""
    msg = get_object_or_404(Message, pk=pk)

    if not msg.transfer_id and not msg.numero_envoyeur:
        return JsonResponse({
            'status': 'error',
            'message': 'Impossible d\'extraire les infos du SMS'
        })

    correspond, details, donnees_site = verifier_sur_site(
        msg.transfer_id, msg.montant, msg.numero_envoyeur
    )

    msg.statut_verification = 'correspond' if correspond else 'non_trouve'
    msg.details_verification = details
    msg.save(update_fields=['statut_verification', 'details_verification'])

    return JsonResponse({
        'status': 'ok',
        'correspond': correspond,
        'transfer_id': msg.transfer_id,
        'montant': msg.montant,
        'numero': msg.numero_envoyeur,
        'nom': msg.nom_envoyeur,
        'details': details,
        'donnees_site': donnees_site,
    })


def ping(request):
    return JsonResponse({'status': 'ok', 'total_sms': Message.objects.count()})
