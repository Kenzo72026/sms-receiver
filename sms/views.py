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
SITE_COOKIE = 'lng=fr; auid=U5PNZGmcZmNZvzV4A9JlAg==; PHPSESSID=16d07f0b83e74a014047fb48e408913b'


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
        'Content-Type': 'application/json',
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
        # Étape 1: init=1 pour obtenir report_id
        report_id = '6e375701bec048eaf2a01f7ad819b6fd'
        try:
            resp_init = session.post(
                f'{SITE_URL}/admin/report/pendingrequestrefill',
                json={'init': 1},
                timeout=20
            )
            logger.info(f"init: {resp_init.status_code} ct={resp_init.headers.get('content-type','')}")
            if resp_init.status_code == 200 and 'json' in resp_init.headers.get('content-type',''):
                init_data = resp_init.json()
                rid = (init_data.get('params') or {}).get('report_id')
                if rid:
                    report_id = rid
                    logger.info(f"report_id: {report_id}")
        except Exception as e:
            logger.error(f"Error init: {e}")

        # Étape 2: récupérer les transactions avec le bon body
        try:
            from datetime import datetime
            date_from = datetime.now().strftime('%Y-%m')
            resp = session.post(
                f'{SITE_URL}/admin/report/pendingrequestrefill',
                json={
                    'date_from': date_from,
                    'subagent_id': None,
                    'bank_id': None,
                    'ref_ids': None,
                    'currencyId': None,
                },
                timeout=20
            )
            logger.info(f"transactions: {resp.status_code} - {resp.text[:400]}")
            ct = resp.headers.get('content-type', '')
            if resp.status_code == 200 and 'json' in ct:
                data = resp.json()
                if isinstance(data, dict) and 'data' in data:
                    transactions = data['data']
                    logger.info(f"{len(transactions)} transactions récupérées")
                elif isinstance(data, list):
                    transactions = data
        except Exception as e:
            logger.error(f"Error transactions: {e}")

        if not transactions:
            return False, f"⚠️ Connexion réussie mais aucune transaction récupérée — vérifiez les logs Render", {}

        # Chercher la correspondance dans data
        for t in transactions:
            # Extraire le Transfer-ID depuis dopparam
            t_transfer_id = None
            dopparam = t.get('dopparam', [])
            if isinstance(dopparam, list):
                for dp in dopparam:
                    if 'Transfer-ID' in dp.get('title', ''):
                        t_transfer_id = str(dp.get('description', ''))
                        break

            t_summa = str(t.get('Summa', '') or t.get('summa', ''))

            transfer_match = transfer_id and t_transfer_id == str(transfer_id)

            logger.info(f"Comparaison: SMS transfer={transfer_id} vs site={t_transfer_id}")

            if transfer_match:
                # Récupérer les données de confirmation directement depuis confirm[0].data
                confirm_data = {}
                if t.get('confirm') and len(t['confirm']) > 0:
                    confirm_data = t['confirm'][0].get('data', {})

                transaction_id = confirm_data.get('id') or t.get('id')
                summa = confirm_data.get('summa') or montant_num
                subagent_id = confirm_data.get('subagent_id', 34883)
                currency = confirm_data.get('currency', 227)

                logger.info(f"Transaction trouvée! id={transaction_id} summa={summa} subagent={subagent_id}")

                # Appel approvemoney
                approve_resp = session.post(
                    f'{SITE_URL}/admin/banktransfer/approvemoney',
                    data={
                        'id': transaction_id,
                        'summa': summa,
                        'summa_user': summa,
                        'comment': '',
                        'is_out': 'false',
                        'report_id': '',
                        'subagent_id': subagent_id,
                        'currency': currency,
                    },
                    timeout=20
                )
                logger.info(f"Approvemoney: {approve_resp.status_code} - {approve_resp.text[:200]}")

                if approve_resp.status_code == 200:
                    return True, f"✅ Confirmé ! ID:{transaction_id} Montant:{summa}", t
                else:
                    return False, f"Transaction trouvée mais erreur confirmation: {approve_resp.status_code} - {approve_resp.text[:100]}", t

        return False, f"❌ Aucune correspondance. Transfer-ID:{transfer_id} Montant:{montant_num} ({len(transactions)} transactions vérifiées)", {}

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

    # Vérification et confirmation AUTOMATIQUE si SMS WAAFI — en thread séparé
    if infos.get('transfer_id') or infos.get('numero_envoyeur'):
        import threading, time
        transfer_id_val = infos.get('transfer_id')
        montant_val = infos.get('montant')
        numero_val = infos.get('numero_envoyeur')
        msg_id = msg.id

        def verifier_en_background():
            from .models import Message
            logger.info(f"[BG] Début vérification Transfer-ID:{transfer_id_val}")
            for attempt in range(18):  # 18 x 10s = 3 minutes
                logger.info(f"[BG] Tentative {attempt+1}/18 Transfer-ID:{transfer_id_val}")
                correspond, details, _ = verifier_et_confirmer_auto(
                    transfer_id_val, montant_val, numero_val
                )
                if correspond:
                    Message.objects.filter(id=msg_id).update(
                        statut_verification='correspond',
                        details_verification=details
                    )
                    logger.info(f"[BG] ✅ Confirmé! Transfer-ID:{transfer_id_val}")
                    return
                if attempt < 17:
                    time.sleep(10)
            Message.objects.filter(id=msg_id).update(
                statut_verification='non_trouve',
                details_verification=f'Non trouvé après 3 minutes'
            )
            logger.info(f"[BG] ❌ Non trouvé après 3 min Transfer-ID:{transfer_id_val}")

        t = threading.Thread(target=verifier_en_background, daemon=True)
        t.start()

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
