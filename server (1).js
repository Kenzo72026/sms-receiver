const express = require('express');
const bodyParser = require('body-parser');
const cors = require('cors');
const fs = require('fs');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3000;

app.use(cors());
app.use(bodyParser.json());
app.use(bodyParser.urlencoded({ extended: true }));

const SMS_FILE = path.join(__dirname, 'sms_data.json');

function loadSMS() {
  if (!fs.existsSync(SMS_FILE)) return [];
  try { return JSON.parse(fs.readFileSync(SMS_FILE, 'utf8')); }
  catch { return []; }
}

function saveSMS(data) {
  fs.writeFileSync(SMS_FILE, JSON.stringify(data, null, 2));
}

// ✅ URL À METTRE DANS SMS FORWARDER : https://VOTRE_DOMAINE/sms
app.post('/sms', (req, res) => {
  const body = req.body;
  const smsEntry = {
    id: Date.now(),
    recu_le: new Date().toISOString(),
    expediteur: body.from || body.sender || body.number || body.phone || 'Inconnu',
    message: body.message || body.text || body.sms || body.body || '',
    date_sms: body.sentStamp || body.date || body.timestamp || new Date().toISOString(),
    appareil: body.deviceName || body.device || 'Téléphone',
    sim: body.simSlot || body.sim || '1',
  };
  const allSMS = loadSMS();
  allSMS.unshift(smsEntry);
  saveSMS(allSMS);
  console.log('📩 SMS reçu de:', smsEntry.expediteur, '-', smsEntry.message);
  res.json({ success: true, id: smsEntry.id, total: allSMS.length });
});

// Tableau de bord
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
    body { font-family: -apple-system, sans-serif; background: #0f0f23; color: #e0e0e0; }
    header { background: #1a1a3e; padding: 20px 30px; display: flex; align-items: center; justify-content: space-between; border-bottom: 2px solid #f5a623; }
    header h1 { font-size: 1.4rem; color: #f5a623; }
    .badge { background: #f5a623; color: #000; border-radius: 20px; padding: 3px 10px; font-size: 0.8rem; font-weight: bold; }
    .stats { background: #141428; padding: 15px 30px; display: flex; gap: 30px; border-bottom: 1px solid #333; }
    .stat-num { font-size: 1.8rem; font-weight: bold; color: #f5a623; }
    .stat-label { font-size: 0.75rem; color: #888; }
    .controls { padding: 15px 30px; display: flex; gap: 10px; flex-wrap: wrap; background: #141428; border-bottom: 1px solid #222; }
    input { flex: 1; min-width: 200px; padding: 8px 14px; border-radius: 8px; border: 1px solid #444; background: #1e1e3e; color: #e0e0e0; }
    button { padding: 8px 16px; border-radius: 8px; border: none; cursor: pointer; font-weight: bold; }
    .btn-refresh { background: #f5a623; color: #000; }
    .btn-export { background: #1e3a1e; color: #7fff7f; }
    .btn-clear { background: #3a1e1e; color: #ff8888; }
    .container { padding: 20px 30px; }
    .sms-card { background: #1a1a3e; border: 1px solid #333; border-radius: 12px; padding: 16px; margin-bottom: 12px; }
    .sms-card:hover { border-color: #f5a623; }
    .sms-header { display: flex; justify-content: space-between; margin-bottom: 10px; }
    .sender { font-weight: bold; color: #f5a623; }
    .time { font-size: 0.8rem; color: #666; }
    .message { background: #12122a; padding: 10px 14px; border-radius: 8px; line-height: 1.5; color: #ccc; }
    .meta { margin-top: 8px; font-size: 0.75rem; color: #555; }
    .empty { text-align: center; padding: 60px; color: #444; }
  </style>
</head>
<body>
  <header>
    <h1>📱 Récepteur SMS Instantané</h1>
    <span class="badge">${allSMS.length} messages</span>
  </header>
  <div class="stats">
    <div><div class="stat-num">${allSMS.length}</div><div class="stat-label">Total SMS</div></div>
    <div><div class="stat-num">${new Set(allSMS.map(s => s.expediteur)).size}</div><div class="stat-label">Contacts</div></div>
    <div><div class="stat-num">${allSMS.filter(s => new Date(s.recu_le) > new Date(Date.now() - 86400000)).length}</div><div class="stat-label">Dernières 24h</div></div>
  </div>
  <div class="controls">
    <input type="text" id="search" placeholder="🔍 Rechercher..." oninput="filterSMS()">
    <button class="btn-refresh" onclick="location.reload()">🔄 Actualiser</button>
    <button class="btn-export" onclick="exportJSON()">⬇️ Exporter</button>
    <button class="btn-clear" onclick="clearAll()">🗑️ Effacer tout</button>
  </div>
  <div class="container" id="list">
    ${allSMS.length === 0
      ? '<div class="empty"><p style="font-size:3rem">📭</p><p style="margin-top:10px">Aucun SMS reçu — configurez SMS Forwarder avec l\'URL /sms</p></div>'
      : allSMS.map(s => `
        <div class="sms-card" data-q="${s.expediteur} ${s.message}">
          <div class="sms-header">
            <span class="sender">📞 ${s.expediteur}</span>
            <span class="time">${new Date(s.recu_le).toLocaleString('fr-FR')}</span>
          </div>
          <div class="message">${s.message.replace(/</g,'&lt;')}</div>
          <div class="meta">📱 ${s.appareil} · SIM ${s.sim}</div>
        </div>`).join('')}
  </div>
  <script>
    function filterSMS() {
      const q = document.getElementById('search').value.toLowerCase();
      document.querySelectorAll('.sms-card').forEach(c => {
        c.style.display = c.dataset.q.toLowerCase().includes(q) ? '' : 'none';
      });
    }
    function exportJSON() {
      fetch('/api/sms').then(r => r.json()).then(data => {
        const a = document.createElement('a');
        a.href = URL.createObjectURL(new Blob([JSON.stringify(data,null,2)], {type:'application/json'}));
        a.download = 'sms_' + new Date().toISOString().slice(0,10) + '.json';
        a.click();
      });
    }
    function clearAll() {
      if(confirm('Effacer tous les SMS ?')) fetch('/api/clear',{method:'DELETE'}).then(()=>location.reload());
    }
    setTimeout(() => location.reload(), 15000);
  </script>
</body>
</html>`;
  res.send(html);
});

app.get('/api/sms', (req, res) => {
  res.json(loadSMS());
});

app.delete('/api/clear', (req, res) => {
  saveSMS([]);
  res.json({ success: true });
});

app.get('/ping', (req, res) => {
  res.json({ status: 'OK', timestamp: new Date().toISOString() });
});

app.listen(PORT, () => {
  console.log(`🚀 Serveur démarré sur le port ${PORT}`);
  console.log(`🔗 Webhook SMS Forwarder : http://localhost:${PORT}/sms`);
});
