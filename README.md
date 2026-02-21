# 📱 Système Récepteur SMS Instantané

## Ce que fait ce système
Reçoit **instantanément** tous vos SMS depuis l'app **SMS Forwarder (Transitaire SMS)** et les affiche dans un tableau de bord web. Chaque SMS est sauvegardé automatiquement.

---

## 🚀 Déploiement GRATUIT en 5 minutes (Railway)

### Étape 1 — Créer un compte gratuit
Allez sur **https://railway.app** et créez un compte (avec GitHub).

### Étape 2 — Déployer le projet
1. Cliquez **"New Project"** → **"Deploy from GitHub repo"**
2. Importez ce code (ou uploadez les fichiers)
3. Railway démarre automatiquement le serveur
4. Vous obtenez une URL comme: `https://sms-receiver-production.up.railway.app`

### Étape 3 — Configurer SMS Forwarder (Transitaire SMS)
Dans l'application sur votre téléphone :
1. Appuyez sur **"+ Ajouter"**
2. Choisissez **"URL"**
3. Entrez cette URL :
   ```
   https://VOTRE_URL_RAILWAY/sms
   ```
4. Méthode : **POST**
5. Appuyez **"Suivant"** et terminez la configuration

### Étape 4 — Voir vos SMS
Ouvrez dans votre navigateur :
```
https://VOTRE_URL_RAILWAY/
```

---

## 🖥️ Déploiement sur votre propre serveur (VPS)

```bash
# Cloner/uploader les fichiers puis:
npm install
node server.js
```

Le serveur écoute sur le port **3000**.

---

## 📡 URLs disponibles

| URL | Description |
|-----|-------------|
| `GET /` | Tableau de bord visuel |
| `POST /sms` | **URL à mettre dans SMS Forwarder** |
| `GET /api/sms` | Tous les SMS en JSON |
| `GET /api/sms?from=+33612345678` | Filtrer par numéro |
| `GET /api/sms?limit=10` | Limiter le nombre |
| `DELETE /api/clear` | Effacer tous les SMS |
| `GET /ping` | Vérifier que le serveur est actif |

---

## 📋 Format du webhook accepté

L'application SMS Forwarder envoie des données en POST. Le serveur accepte ces champs (compatibles avec plusieurs applications) :

```json
{
  "from": "+33612345678",
  "message": "Bonjour comment ça va ?",
  "sentStamp": "2024-01-15T14:30:00Z",
  "deviceName": "Mon Téléphone",
  "simSlot": "1"
}
```

---

## ⚙️ Configuration SMS Forwarder

Dans l'app, lors de la configuration URL :
- **URL** : `https://VOTRE_DOMAINE/sms`
- **Méthode HTTP** : POST
- **Type de contenu** : JSON (application/json)

Le tableau de bord s'actualise automatiquement toutes les 10 secondes.
