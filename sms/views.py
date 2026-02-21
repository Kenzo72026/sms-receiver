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

SITE_USERNAME = 'Waafi_Basta_Main'
SITE_PASSWORD = '82LMBJPT3t'
SITE_URL = 'https://my-managment.com'


def extraire_infos_sms(contenu):
    """Extrait Transfer ID, montant, numéro et nom depuis le SMS WAAFI."""
    infos = {
        'transfer_id': None,
        'montant': None,
        'montant_num': None,
        'numero_envoyeur': None,
        'nom_envoyeur': None,
    }

    # Transfer ID (ex: Transfer-Id: 59808713)
    m = re.search(r'Transfer-Id[:\s]+(\d+)', contenu, re.IGNORECASE)
    if m:
        infos['transfer_id'] = m.group(1)

    # Montant (ex: Received DJF 100 from)
    m = re.search(r'Received\s+([\w\s]+?)\s+from', contenu, re.IGNORECASE)
    if m:
        infos['montant'] = m.group(1).strip()
        num = re.search(r'(\d+)', infos['montant'])
        if num:
            infos['montant_num'] = num.group(1)

    # Nom et numéro (ex: Kenedid Yacin Boulaleh(77280597))
    m = re.search(r'from\s+([A-Za-z\s]+)\((\d+)\)', contenu, re.IGNORECASE)
    if m:
        infos['nom_envoyeur'] = m.group(1).strip()
        infos['numero_envoyeur'] = m.group(2).strip()

    return infos


def get_session():
    """Crée une session authentifiée sur my-managment.com."""
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'fr,fr-FR;q=0.9,en;q=0.8',
        'X-Requested-With': 'XMLHttpRequest',
        'X-Time-Zone': 'GMT+03',
        'Origin': SITE_URL,
        'Referer': f'{SITE_URL}/fr/admin/report/pendingrequestrefill',
    })

    # Connexion
    try:
        login_resp = session.post(
            f'{SITE_URL}/api/auth/login',
            json={'username': SITE_USERNAME, 'password': SITE_PASSWORD},
            timeout=20
        )
        logger.info(f"Login: {login_resp.status_code}")

        if login_resp.status_code not in (200, 201):
            for endpoint in [
                f'{SITE_URL}/api/login',
                f'{SITE_URL}/api/v1/auth/login',
            ]:
                login_resp = session.post(
                    endpoint,
                    json={'username': SITE_USERNAME, 'password': SITE_PASSWORD},
                    timeout=20
                )
                if login_resp.status_code in (200, 201):
                    break

        # Récupérer token si présent
        try:
            login_data = login_resp.json()
            token = (
                login_data.get('token') or
                login_data.get('access_token') or
                login_data.get('data', {}).get('token')
            )
            if token:
                session.headers.update({'Authorization': f'Bearer {token}'})
        except Exception:
            pass

    except Exception as e:
        logger.error(f"Erreur login: {e}")

    return session


def verifier_et_confirmer(transfer_id, montant, numero, confirmer=False):
    """
    1. Se connecte sur my-managment.com
    2. Cherche dans Pending deposit requests
    3. Si trouve → appelle approvemoney automatiquement
    """
    session = get_session()

    try:
        # Récupérer les pending deposits
        transactions = []
        endpoints_deposits = [
            f'{SITE_URL}/api/payment/pending-deposits',
            f'{SITE_URL}/api/deposits/pending',
            f'{SITE_URL}/api/v1/deposits/pending',
            f'{SITE_URL}/api/banktransfer/pending',
            f'{SITE_URL}/admin/banktransfer/pendingrequestrefill',
        ]

        raw_response = ""
        for endpoint in endpoints_deposits:
            try:
                resp = session.get(endpoint, timeout=20)
                raw_response += f"\n{endpoint}: {resp.status_code}"
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        if isinstance(data, list) and len(data) > 0:
                            transactions = data
                            break
                        elif isinstance(data, dict):
                            for key in ['data', 'items', 'transactions', 'deposits', 'list', 'results']:
                                if key in data and isinstance(data[key], list) and len(data[key]) > 0:
                                    transactions = data[key]
                                    break
                        if transactions:
                            break
                    except Exception:
                        pass
            except Exception as e:
                logger.error(f"Erreur {endpoint}: {e}")
                continue

        if not transactions:
            return False, f"Aucune transaction récupérée. Endpoints testés: {raw_response}", {}

        # Chercher la transaction correspondante
        montant_num = re.search(r'(\d+)', montant or '').group(1) if montant else None

        for t in transactions:
            t_str = json.dumps(t, ensure_ascii=False).lower()

            transfer_match = transfer_id and str(transfer_id) in t_str
            montant_match = montant_num and montant_num in t_str
            numero_match = numero and str(numero) in t_str

            if transfer_match or (montant_match and numero_match):
                # Transaction trouvée — appeler approvemoney
                transaction_id = (
                    t.get('id') or t.get('transaction_id') or
                    t.get('ID') or t.get('_id')
                )
                summa = (
                    t.get('summa') or t.get('amount') or
                    t.get('montant') or montant_num or '0'
                )
                report_id = (
                    t.get('report_id') or t.get('reportId') or
                    t.get('report') or ''
                )
                subagent_id = t.get('subagent_id', 34883)
                currency = t.get('currency', 227)

                if not transaction_id:
                    return True, "Transaction trouvée mais ID manquant pour approvemoney", t

                # Appel à approvemoney
                approve_resp = session.post(
                    f'{SITE_URL}/admin/banktransfer/approvemoney',
                    data={
                        'id': transaction_id,
                        'summa': summa,
                        'summa_user': summa,
                        'comment': '',
                        'is_out': 'false',
                        'report_id': report_id,
                        'subagent_id': subagent_id,
                        'currency': currency,
                    },
                    timeout=20
                )

                logger.info(f"Approvemoney: {approve_resp.status_code} - {approve_resp.text[:200]}")

                if approve_resp.status_code == 200:
                    return True, f"✅ Transaction confirmée avec succès ! ID: {transaction_id}, Montant: {summa}", t
                else:
                    return False, f"Transaction trouvée mais erreur lors de la confirmation: {approve_resp.status_code} - {approve_resp.text[:100]}", t

        return False, f"❌ Aucune transaction correspondante. Transfer-ID: {transfer_id}, Montant: {montant_num}, Numéro: {numero}. Total transactions: {len(transactions)}", {}

    except Exception as e:
        logger.error(f"Erreur vérification: {e}")
        return False, f"Erreur: {str(e)}", {}


@csrf_exempt
def webhook_recevoir_sms(request):
    """Webhook - reçoit les SMS et extrait automatiquement les infos."""
    data = {}
    data.update(request.GET.dict())
    if request.method == 'POST':
        try:
            body_str = request.body.decode('utf-8').strip()
            if body_str:
                parsed = json.loads(body_str)
                if isinstance(parsed, dict):
                    data.update(parsed)
        except Exception:
            pass
        try:
            if request.POST:
                data.update(request.POST.dict())
        except Exception:
            pass

    logger.info(f"[WEBHOOK] donnees={json.dumps(data, ensure_ascii=False)[:500]}")

    expediteur = (
        data.get('from') or data.get('sender') or data.get('number') or
        data.get('phone') or 'Inconnu'
    )
    if expediteur and expediteur.startswith('{'):
        expediteur = 'Inconnu'

    contenu = (
        data.get('message') or data.get('msg') or data.get('body') or
        data.get('text') or data.get('sms') or data.get('key') or ''
    )
    if contenu and contenu.startswith('{'):
        contenu = ''
    if not contenu:
        contenu = f"[Données: {json.dumps(data, ensure_ascii=False)}]"

    infos = extraire_infos_sms(contenu)

    ip_source = (
        request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or
        request.META.get('REMOTE_ADDR')
    )

    msg = Message.objects.create(
        expediteur=str(expediteur)[:50],
        contenu=contenu,
        source_ip=ip_source or None,
        transfer_id=infos.get('transfer_id'),
        montant=infos.get('montant'),
        numero_envoyeur=infos.get('numero_envoyeur'),
        nom_envoyeur=infos.get('nom_envoyeur'),
        statut_verification='non_verifie',
    )

    logger.info(f"SMS ID={msg.id} transfer_id={infos.get('transfer_id')} montant={infos.get('montant')}")
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
    """Vérifie et confirme automatiquement si les infos correspondent."""
    msg = get_object_or_404(Message, pk=pk)

    if not msg.transfer_id and not msg.numero_envoyeur:
        return JsonResponse({
            'status': 'error',
            'message': 'Impossible d\'extraire les infos du SMS'
        })

    correspond, details, donnees_site = verifier_et_confirmer(
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
    })


def ping(request):
    return JsonResponse({'status': 'ok', 'total_sms': Message.objects.count()})
