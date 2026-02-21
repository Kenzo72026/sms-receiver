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

    # Transfer ID (ex: Transfer-Id: 59808713)
    m = re.search(r'Transfer-Id[:\s]+(\d+)', contenu, re.IGNORECASE)
    if m:
        infos['transfer_id'] = m.group(1)

    # Montant (ex: Received DJF 100 from)
    m = re.search(r'Received\s+([\w\s]+?)\s+from', contenu, re.IGNORECASE)
    if m:
        infos['montant'] = m.group(1).strip()
        # Extraire juste le nombre
        num = re.search(r'(\d+)', infos['montant'])
        if num:
            infos['montant_num'] = num.group(1)

    # Nom et numéro (ex: Kenedid Yacin Boulaleh(77280597))
    m = re.search(r'from\s+([A-Za-z\s]+)\((\d+)\)', contenu, re.IGNORECASE)
    if m:
        infos['nom_envoyeur'] = m.group(1).strip()
        infos['numero_envoyeur'] = m.group(2).strip()

    return infos


def verifier_sur_site(transfer_id, montant, numero):
    """
    Se connecte sur my-managment.com et vérifie dans Pending deposit requests
    si le Transfer-ID, montant et numéro correspondent.
    """
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
    })

    try:
        # 1. Connexion au site
        logger.info("Tentative connexion my-managment.com...")
        login_resp = session.post(
            'https://my-managment.com/api/auth/login',
            json={'username': 'Waafi_Basta_Main', 'password': '82LMBJPT3t'},
            timeout=20
        )
        logger.info(f"Login response: {login_resp.status_code} - {login_resp.text[:200]}")

        # Essai d'autres endpoints de login si le premier échoue
        if login_resp.status_code not in (200, 201):
            for endpoint in [
                'https://my-managment.com/api/login',
                'https://my-managment.com/api/v1/auth/login',
                'https://my-managment.com/signin',
            ]:
                try:
                    login_resp = session.post(
                        endpoint,
                        json={'username': 'Waafi_Basta_Main', 'password': '82LMBJPT3t'},
                        timeout=20
                    )
                    logger.info(f"Login {endpoint}: {login_resp.status_code}")
                    if login_resp.status_code in (200, 201):
                        break
                except Exception:
                    continue

        # Récupérer le token si présent
        try:
            login_data = login_resp.json()
            token = (
                login_data.get('token') or
                login_data.get('access_token') or
                login_data.get('data', {}).get('token') or
                login_data.get('data', {}).get('access_token')
            )
            if token:
                session.headers.update({'Authorization': f'Bearer {token}'})
                logger.info(f"Token récupéré: {token[:20]}...")
        except Exception:
            pass

        # 2. Récupérer les pending deposit requests
        transactions = []
        endpoints_deposits = [
            'https://my-managment.com/api/payment/pending-deposits',
            'https://my-managment.com/api/deposits/pending',
            'https://my-managment.com/api/v1/deposits/pending',
            'https://my-managment.com/api/transactions/pending',
            'https://my-managment.com/api/bank-transfers/pending',
            'https://my-managment.com/api/v1/payment/pending',
        ]

        raw_response = ""
        for endpoint in endpoints_deposits:
            try:
                resp = session.get(endpoint, timeout=20)
                logger.info(f"Deposits {endpoint}: {resp.status_code} - {resp.text[:300]}")
                raw_response += f"\n{endpoint}: {resp.status_code} - {resp.text[:200]}"
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list) and len(data) > 0:
                        transactions = data
                        break
                    elif isinstance(data, dict):
                        for key in ['data', 'items', 'transactions', 'deposits', 'list', 'results']:
                            if key in data and isinstance(data[key], list):
                                transactions = data[key]
                                break
                    if transactions:
                        break
            except Exception as e:
                logger.error(f"Erreur endpoint {endpoint}: {e}")
                continue

        if not transactions:
            return False, f"Aucune transaction récupérée. Réponses API: {raw_response}", {}

        # 3. Chercher la correspondance
        # Sur le site: Transfer-ID est dans les infos utilisateur
        # Colonnes: IDENTIFIANT DE LA TRANSACTION, MONTANT, INFOS SUR L'UTILISATEUR
        for t in transactions:
            t_str = json.dumps(t, ensure_ascii=False).lower()

            # Vérifier Transfer-ID
            transfer_match = transfer_id and str(transfer_id) in t_str

            # Vérifier montant (juste le nombre)
            montant_num = re.search(r'(\d+)', montant or '').group(1) if montant else None
            montant_match = montant_num and montant_num in t_str

            # Vérifier numéro envoyeur
            numero_match = numero and str(numero) in t_str

            logger.info(f"Transaction: transfer_match={transfer_match} montant_match={montant_match} numero_match={numero_match}")

            # Correspondance si Transfer-ID ET (montant OU numéro) correspondent
            if transfer_match and (montant_match or numero_match):
                return True, f"✅ Transaction trouvée et vérifiée !", t

            # Correspondance si montant ET numéro correspondent (sans Transfer-ID)
            if montant_match and numero_match:
                return True, f"✅ Transaction trouvée par montant et numéro !", t

        return False, f"❌ Aucune transaction correspondante trouvée parmi {len(transactions)} transactions. Transfer-ID cherché: {transfer_id}, Montant: {montant}, Numéro: {numero}", {}

    except Exception as e:
        logger.error(f"Erreur vérification: {e}")
        return False, f"Erreur de connexion: {str(e)}", {}


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

    # Extraire les infos du SMS WAAFI
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
    """Lance la vérification d'un SMS sur my-managment.com Pending deposit requests."""
    msg = get_object_or_404(Message, pk=pk)

    if not msg.transfer_id and not msg.numero_envoyeur:
        return JsonResponse({
            'status': 'error',
            'message': 'Impossible d\'extraire les infos du SMS (Transfer-ID et numéro manquants)'
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
