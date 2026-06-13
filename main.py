import os
import smtplib
import requests
import time
import email.utils
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- UTILS POUR LE NETTOYAGE ---
def safe_encode(text):
    """
    Force la conversion en ASCII pur (élimine tout caractère dont le code est >= 128).
    C'est la méthode la plus robuste pour éviter les erreurs d'encodage (UnicodeEncodeError)
    lors de la transmission SMTP et l'envoi vers des serveurs externes.
    """
    if not isinstance(text, str):
        text = str(text)
    return "".join(char for char in text if ord(char) < 128)

# --- CONFIGURATION ---
# Nettoyage systématique des variables d'environnement dès le chargement
NEWS_API_KEY = os.environ.get("NEWS_API_KEY", "")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
GMAIL_USER = safe_encode(os.environ.get("GMAIL_USER", ""))
GMAIL_APP_PASSWORD = safe_encode(os.environ.get("GMAIL_APP_PASSWORD", ""))
TO_EMAIL = "elom.karl.patrick@gmail.com"

TOPICS = ["cybersecurity", "artificial intelligence Claude Anthropic", "tech news"]

# --- FETCH NEWS ---
def fetch_articles():
    articles = []
    for topic in TOPICS:
        url = (
            f"https://newsapi.org/v2/everything"
            f"?q={topic}&language=en&sortBy=publishedAt&pageSize=3"
            f"&apiKey={NEWS_API_KEY}"
        )
        try:
            r = requests.get(url, timeout=10)
            data = r.json()
            if data.get("articles"):
                for a in data["articles"]:
                    # Nettoyage à la source pour éviter tout caractère invisible
                    title = safe_encode(a.get('title', ''))
                    desc = safe_encode(a.get('description', ''))
                    articles.append(f"- {title}: {desc}")
        except Exception as e:
            print(f"Erreur lors de la récupération des news pour {topic}: {e}")
    # On limite à 9 articles pour garantir la stabilité de la génération
    return "\n".join(articles[:9])

# --- GENERATE THREADS ---
def generate_threads(articles_text):
    # Prompt renforcé avec des contraintes négatives strictes pour supprimer les parasites
    prompt = f"""Tu es un créateur de contenu tech/cybersec francophone.
À partir de ces actualités, génère exactement 3 threads Twitter/Threads en français.
Chaque thread = 5 tweets max, percutants, informatifs, ton humain pas corporate.

RÈGLES ABSOLUES ET STRICTES :
1. NE DONNE QUE LE CONTENU DES THREADS.
2. PAS D'INTRODUCTION, PAS DE CONCLUSION.
3. PAS DE LABELS DE SECURITE (Ex: NE PAS ECRIRE 'User Safety').
4. PAS DE COMMENTAIRES MÉTADONNÉES.
5. SORTIE BRUTE UNIQUEMENT.

Format attendu :

THREAD 1 — [Sujet]
1/
2/
3/
...

Actualités :
{articles_text}
"""
    
    # Liste des modèles disponibles en cas d'échec de la requête
    models_to_try = [
        "openrouter/free",
        "deepseek/deepseek-chat-v3-0324:free",
        "meta-llama/llama-3.3-70b-instruct:free",
        "qwen/qwen3-coder:free"
    ]
    
    for model in models_to_try:
        print(f"Tentative de génération avec le modèle : {model}...")
        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/Patrickk2/thread-bot",
                    "X-Title": "Thread Bot GitHub Action"
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}]
                },
                timeout=45
            )
            data = response.json()
            
            if "choices" in data:
                print(f"✅ Succès avec {model} !")
                # Extraction du contenu pur
                raw_content = data["choices"][0]["message"]["content"]
                return safe_encode(raw_content)
            
            print(f"⚠️ Échec avec {model} : {data.get('error', {}).get('message', 'Erreur inconnue')}")
            time.sleep(3) 
            
        except Exception as e:
            print(f"❌ Erreur réseau avec {model} : {e}")
            time.sleep(3)
            
    return None

# --- SEND EMAIL ---
def send_email(threads_content):
    # Nettoyage radical final du contenu avant envoi
    clean_content = safe_encode(threads_content)

    msg = MIMEMultipart()
    msg["Subject"] = "Threads Report"
    msg["From"] = GMAIL_USER
    msg["To"] = TO_EMAIL
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = email.utils.make_msgid()

    # Utilisation explicite de 'us-ascii' pour éviter toute interprétation erronée par SMTP
    msg.attach(MIMEText(clean_content, "plain", "us-ascii"))

    try:
        # Connexion avec timeout pour éviter les blocages de session
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
            server.ehlo()
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            # Envoi des bytes directement pour contourner les codecs Python
            server.sendmail(GMAIL_USER, TO_EMAIL, msg.as_bytes())
        print("✅ Email envoyé avec succès.")
    except Exception as e:
        print(f"❌ Erreur critique lors de l'envoi email : {e}")
        raise e

# --- MAIN ---
if __name__ == "__main__":
    # Vérification des credentials avant exécution
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        print("Erreur : Credentials Gmail manquants.")
        exit(1)
        
    articles = fetch_articles()
    if not articles:
        print("No articles fetched.")
        exit(0)
        
    threads = generate_threads(articles)
    
    if threads:
        send_email(threads)
    else:
        print("❌ Échec total de la génération.")
        exit(1)
