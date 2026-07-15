# Thread Bot

Génère et envoie 3 threads tech/cybersec par email via GitHub Actions.

## Setup (5 étapes)

### 1. Crée le repo GitHub
- Nouveau repo **privé**, nom : `thread-bot`
- Upload les fichiers : `main.py` + `.github/workflows/thread-bot.yml`

### 2. Ajoute les secrets
Dans ton repo → Settings → Secrets and variables → Actions → New repository secret

| Nom | Valeur |
|---|---|
| `NEWS_API_KEY` | ta clé newsapi.org |
| `OPENROUTER_API_KEY` | ta clé openrouter.ai |
| `GMAIL_USER` | ton adresse Gmail d'envoi |
| `GMAIL_APP_PASSWORD` | ton app password 16 caractères |
| `HF_TOKEN` | ta clé Hugging Face |
| `RECIPIENT_EMAIL` | l'adresse qui reçoit les threads |

Aucune information personnelle (email, nom) ne doit jamais être écrite en dur dans `main.py` — tout passe par ces secrets.

### 3. Active GitHub Actions
Onglet Actions → Enable

### 4. Test manuel
Actions → Thread Bot → Run workflow

### 5. Vérifie ta boîte mail
Email reçu = tout marche. Le bot tourne ensuite automatiquement selon le cron défini dans le workflow.
