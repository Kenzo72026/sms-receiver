const express = require('express');
const bodyParser = require('body-parser');
const cors = require('cors');
const fs = require('fs');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3000;

// Middleware
app.use(cors());
app.use(bodyParser.json());
app.use(bodyParser.urlencoded({ extended: true }));

// Stockage des SMS (fichier JSON)
const SMS_FILE = path.join(__dirname, 'sms_data.json');

function loadSMS() {
  if (!fs.existsSync(SMS_FILE)) return [];
  try {
    return JSON.parse(fs.readFileSync(SMS_FILE, 'utf8'));
  } catch {
    return [];
  }
}

function saveSMS(data) {
  fs.writeFileSync(SMS_FILE, JSON.stringify(data, null, 2));
}

// ============================================================
// ENDPOINT PRINCIPAL - Reçoit les SMS depuis SMS Forwarder
// Mettre cette URL dans l'app: http://VOTRE_DOMAINE/sms
// ============================================================
app.post('/sms', (req, res) => {
  const body = req.body;

  console.log('📩 Nouveau SMS reçu:', JSON.stringify(body, null, 2));

  // Compatibilité avec différents formats de SMS Forwarder
  const smsEntry = {
    id: Date.now(),
    recu_le: new Date().toISOString(),
    expediteur: body.from || body.sender || body.number || body.phone || 'Inconnu',
    message: body.message || body.text || body.sms || body.body || '',
    date_sms: body.sentStamp || body.date || body.timestamp || new Date().toISOString(),
    appareils: body.deviceName || body.device || 'Téléphone',
    sim: body.simSlot || body.sim || '1',
    raw: body // Sauvegarde tout le payload brut
  };

  const allSMS = loadSMS();
  allSMS.unshift(smsEntry); // Ajoute en tête de liste (plus récent d'abord)
  saveSMS(allSMS);

  console.log(`✅ SMS sauvegardé. Total: ${allSMS.length} messages`);

  res.json({
    success: true,
    message: 'SMS reçu et sauvegardé',
    id: smsEntry.id,
    total: allSMS.length
  });
});

// ============================================================
// TABLEAU DE BORD - Voir tous les SMS reçus
// Ouvrir dans le navigateur: http://VOTRE_DOMAINE/
// ============================================================
app.get('/', (req, res) => {
  const allSMS = loadSMS();

  const html = `<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>📱 Récepteur SMS</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f0f23; color: #e0e0e0; }
    header { background: linear-gradient(135deg, #1a1a3e, #2d2d5e); padding: 20px 30px; display: flex; align-items: center; justify-content: space-between; border-bottom: 2px solid #f5a623; }
    header h1 { font-size: 1.5rem; color: #f5a623; }
    .stats { background: #1a1a3e; padding: 15px 30px; display: flex; gap: 30px; border-bottom: 1px solid #333; }
    .stat { text-align: center; }
    .stat-num { font-size: 2rem; font-weight: bold; color: #f5a623; }
    .stat-label { font-size: 0.8rem; color: #888; }
    .controls { padding: 15px 30px; display: flex; gap: 10px; flex-wrap: wrap; align-items: center; background: #141428; }
    input[type="text"] { flex: 1; min-width: 200px; padding: 8px 14px; border-radius: 8px; border: 1px solid #444; background: #1e1e3e; color: #e0e0e0; font-size: 0.9rem; }
    button { padding: 8px 18px; border-radius: 8px; border: none; cursor: pointer; font-size: 0.9rem; transition: 0.2s; }
    .btn-refresh { background: #f5a623; color: #000; font-weight: bold; }
    .btn-export { background: #2d5a2d; color: #7fff7f; }
    .btn-clear { background: #5a2d2d; color: #ff8888; }
    .container { padding: 20px 30px; }
    .sms-card { background: #1a1a3e; border: 1px solid #333; border-radius: 12px; padding: 16px; margin-bottom: 12px; transition: 0.2s; }
    .sms-card:hover { border-color: #f5a623; transform: translateY(-1px); }
    .sms-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
    .sender { font-size: 1rem; font-weight: bold; color: #f5a623; }
    .time { font-size: 0.8rem; color: #666; }
    .message { font-size: 0.95rem; line-height: 1.5; color: #ccc; background: #12122a; padding: 10px 14px; border-radius: 8px; }
    .meta { margin-top: 8px; display: flex; gap: 15px; }
    .meta span { font-size: 0.75rem; color: #555; }
    .empty { text-align: center; padding: 60px; color: #444; }
    .empty-icon { font-size: 4rem; margin-bottom: 10px; }
    .badge { background: #f5a623; color: #000; border-radius: 20px; padding: 2px 8px; font-size: 0.75rem; font-weight: bold; }
    @media (max-width: 600px) { .container { padding: 15px; } header { padding: 15px; } }
  </style>
</head>
<body>
  <header>
    <h1>📱 Récepteur SMS Instantané</h1>
    <span class="badge">${allSMS.length} messages</span>
  </header>
  <div class="stats">
    <div class="stat">
      <div class="stat-num">${allSMS.length}</div>
      <div class="stat-label">Total SMS</div>
    </div>
    <div class="stat">
      <div class="stat-num">${new Set(allSMS.map(s => s.expediteur)).size}</div>
      <div class="stat-label">Contacts</div>
    </div>
    <div class="stat">
      <div class="stat-num">${allSMS.filter(s => new Date(s.recu_le) > new Date(Date.now() - 86400000)).length}</div>
      <div class="stat-label">Dernières 24h</div>
    </div>
  </div>
  <div class="controls">
    <input type="text" id="search" placeholder="🔍 Rechercher par numéro ou message..." oninput="filterSMS()">
    <button class="btn-refresh" onclick="location.reload()">🔄 Actualiser</button>
    <button class="btn-export" onclick="exportJSON()">⬇️ Exporter JSON</button>
    <button class="btn-clear" onclick="clearAll()">🗑️ Tout effacer</button>
  </div>
  <div class="container" id="sms-list">
    ${allSMS.length === 0 ? `
      <div class="empty">
        <div class="empty-icon">📭</div>
        <p>Aucun SMS reçu pour l'instant</p>
        <p style="font-size:0.85rem;margin-top:8px;color:#555">Configurez l'app SMS Forwarder avec l'URL webhook</p>
      </div>
    ` : allSMS.map(sms => `
      <div class="sms-card" data-sender="${sms.expediteur}" data-msg="${sms.message}">
        <div class="sms-header">
          <span class="sender">📞 ${sms.expediteur}</span>
          <span class="time">${new Date(sms.recu_le).toLocaleString('fr-FR')}</span>
        </div>
        <div class="message">${sms.message.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</div>
        <div class="meta">
          <span>📱 ${sms.appareils}</span>
          <span>SIM ${sms.sim}</span>
        </div>
      </div>
    `).join('')}
  </div>
  <script>
    function filterSMS() {
      const q = document.getElementById('search').value.toLowerCase();
      document.querySelectorAll('.sms-card').forEach(card => {
        const match = card.dataset.sender.toLowerCase().includes(q) || card.dataset.msg.toLowerCase().includes(q);
        card.style.display = match ? '' : 'none';
      });
    }
    function exportJSON() {
      fetch('/api/sms').then(r => r.json()).then(data => {
        const blob = new Blob([JSON.stringify(data, null, 2)], {type: 'application/json'});
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = 'sms_export_' + new Date().toISOString().slice(0,10) + '.json';
        a.click();
      });
    }
    function clearAll() {
      if(confirm('Effacer tous les SMS ?')) {
        fetch('/api/clear', {method: 'DELETE'}).then(() => location.reload());
      }
    }
    // Auto-actualisation toutes les 10 secondes
    setTimeout(() => location.reload(), 10000);
  </script>
</body>
</html>`;

  res.send(html);
});

// API - Récupérer tous les SMS en JSON
app.get('/api/sms', (req, res) => {
  const allSMS = loadSMS();
  const { from, limit } = req.query;
  let result = allSMS;
  if (from) result = result.filter(s => s.expediteur.includes(from));
  if (limit) result = result.slice(0, parseInt(limit));
  res.json({ total: allSMS.length, sms: result });
});

// API - Effacer tous les SMS
app.delete('/api/clear', (req, res) => {
  saveSMS([]);
  res.json({ success: true, message: 'Tous les SMS effacés' });
});

// Test - Vérifier que le serveur fonctionne
app.get('/ping', (req, res) => {
  res.json({ status: 'OK', message: 'Serveur SMS actif ✅', timestamp: new Date().toISOString() });
});

app.listen(PORT, () => {
  console.log(`\n🚀 Serveur SMS démarré sur le port ${PORT}`);
  console.log(`📊 Tableau de bord: http://localhost:${PORT}/`);
  console.log(`🔗 URL Webhook à mettre dans SMS Forwarder: http://VOTRE_DOMAINE/sms`);
  console.log(`📡 API JSON: http://localhost:${PORT}/api/sms\n`);
});
