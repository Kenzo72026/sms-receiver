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

SITE_URL = 'https://my-managment.com'
# Cookie de session - à mettre à jour si expiré
SITE_COOKIE = 'lng=fr; auid=U5PNZGmZkZ07s+1QAwaPAg==; PHPSESSID=c81f6b610bfd21d6fd3e7d842dc5e0df'


def extraire_infos_sms(contenu):
    infos = {'transfer_id': None, 'montant': None, 'montant_num': None,
              'numero_envoyeur': None, 'nom_envoyeur': None}

    m = re.search(r'Transfer-Id[:\s]+(\d+)', contenu, re.IGNORECASE)
    if m:
        infos['transfer_id'] = m.group(1)

    m = re.search(r'Received\s+([\w\s]+?)\s+from', contenu, re.IGNORECASE)
    if m:
        infos['montant'] = m.group(1).strip()
        num = re.search(r'(\d+)', infos['montant'])
        if num:
            infos['montant_num'] = num.group(1)

    m = re.search(r'from\s+([A-Za-z\s]+)\((\d+)\)', contenu, re.IGNORECASE)
    if m:
        infos['nom_envoyeur'] = m.group(1).strip()
        infos['numero_envoyeur'] = m.group(2).strip()

    return infos


def get_session():
    """Utilise le cookie de session directement — pas besoin de login."""
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'fr,fr-FR;q=0.9,en;q=0.8',
        'X-Requested-With': 'XMLHttpRequest',
        'X-Time-Zone': 'GMT+03',
        'Origin': SITE_URL,
        'Referer': f'{SITE_URL}/fr/admin/report/pendingrequestrefill',
        'Cookie': SITE_COOKIE,
    })
    return session


def verifier_et_confirmer_auto(transfer_id, montant, numero):
    """Vérifie dans Pending deposit requests et appelle approvemoney si ça correspond."""
    session = get_session()
    montant_num = re.search(r'(\d+)', montant or '').group(1) if montant else None

    try:
        # Récupérer les transactions pending
        transactions = []
        # URL exacte trouvée dans Network — POST avec body {init: 1}
        try:
            resp = session.post(
                f'{SITE_URL}/admin/report/pendingrequestrefill',
                json={'init': 1},
                timeout=20
            )
            logger.info(f"pendingrequestrefill: {resp.status_code} - {resp.text[:300]}")
            ct = resp.headers.get('content-type', '')
            if resp.status_code == 200 and 'json' in ct:
                data = resp.json()
                if isinstance(data, list):
                    transactions = data
                elif isinstance(data, dict):
                    for key in ['data', 'items', 'transactions', 'deposits', 'list', 'results']:
                        if key in data and isinstance(data[key], list):
                            transactions = data[key]
                            break
        except Exception as e:
            logger.error(f"Error pendingrequestrefill: {e}")

        if not transactions:
            return False, f"⚠️ Connexion réussie mais aucune transaction récupérée — vérifiez les logs Render", {}

        # Chercher la correspondance
        for t in transactions:
            t_str = json.dumps(t, ensure_ascii=False).lower()
            # Vérification uniquement sur Transfer-ID ET Montant
            transfer_match = transfer_id and str(transfer_id) in t_str
            montant_match = montant_num and montant_num in t_str

            if transfer_match and montant_match:
                transaction_id = (t.get('id') or t.get('transaction_id') or t.get('ID'))
                summa = t.get('summa') or t.get('amount') or montant_num or '0'
                report_id = t.get('report_id') or t.get('reportId') or ''
                subagent_id = t.get('subagent_id', 34883)
                currency = t.get('currency', 227)

                if not transaction_id:
                    return True, "Transaction trouvée mais ID manquant pour confirmer", t

                # Appel approvemoney
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
                    return True, f"✅ Confirmé ! ID:{transaction_id} Montant:{summa}", t
                else:
                    return False, f"Transaction trouvée mais erreur confirmation: {approve_resp.status_code}", t

        return False, f"❌ Aucune correspondance. Transfer-ID:{transfer_id} Montant:{montant_num} Numéro:{numero} ({len(transactions)} transactions vérifiées)", {}

    except Exception as e:
        logger.error(f"Erreur: {e}")
        return False, f"Erreur: {str(e)}", {}


@csrf_exempt
def webhook_recevoir_sms(request):
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

    expediteur = (data.get('from') or data.get('sender') or data.get('number') or 'Inconnu')
    if expediteur and expediteur.startswith('{'):
        expediteur = 'Inconnu'

    contenu = (data.get('message') or data.get('msg') or data.get('body') or
               data.get('text') or data.get('sms') or data.get('key') or '')
    if contenu and contenu.startswith('{'):
        contenu = ''
    if not contenu:
        contenu = f"[Données: {json.dumps(data, ensure_ascii=False)}]"

    infos = extraire_infos_sms(contenu)
    ip_source = (request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or
                 request.META.get('REMOTE_ADDR'))

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

    # Vérification et confirmation AUTOMATIQUE si SMS WAAFI
    if infos.get('transfer_id') or infos.get('numero_envoyeur'):
        logger.info(f"SMS WAAFI — vérification automatique Transfer-ID:{infos.get('transfer_id')}")
        correspond, details, _ = verifier_et_confirmer_auto(
            infos.get('transfer_id'), infos.get('montant'), infos.get('numero_envoyeur')
        )
        msg.statut_verification = 'correspond' if correspond else 'non_trouve'
        msg.details_verification = details
        msg.save(update_fields=['statut_verification', 'details_verification'])

    return JsonResponse({'status': 'ok', 'id': msg.id}, status=201)


@login_required
def dashboard(request):
    messages_qs = Message.objects.all()
    filtre_expediteur = request.GET.get('expediteur', '')
    if filtre_expediteur:
        messages_qs = messages_qs.filter(expediteur__icontains=filtre_expediteur)
    total = Message.objects.count()
    non_lus = Message.objects.filter(lu=False).count()
    Message.objects.filter(lu=False).update(lu=True)
    expediteurs = Message.objects.values_list('expediteur', flat=True).distinct()
    context = {
        'messages': messages_qs[:200],
        'total': total,
        'non_lus': non_lus,
        'expediteurs': expediteurs,
        'filtre_expediteur': filtre_expediteur,
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
        'details_verification', 'date_reception_serveur', 'lu'
    )[:50]
    return JsonResponse({'messages': list(msgs)})


def ping(request):
    return JsonResponse({'status': 'ok', 'total_sms': Message.objects.count()})
