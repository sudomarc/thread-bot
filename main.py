import os
import smtplib
import requests
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- CONFIG ---
NEWS_API_KEY = os.environ["NEWS_API_KEY"]
OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
GMAIL_USER = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
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
                    # Nettoyage basique des titres/descriptions
                    title = a['title'].replace('\xa0', ' ')
                    desc = a.get('description', '').replace('\xa0', ' ')
                    articles.append(f"- {title}: {desc}")
        except Exception as e:
            print(f"Erreur lors de la récupération des news pour {topic}: {e}")
    return "\n".join(articles[:9])

# --- GENERATE THREADS ---
def generate_threads(articles_text):
    prompt = f"""Tu es un créateur de contenu tech/cybersec francophone.
À partir de ces actualités, génère exactement 3 threads Twitter/Threads en français.
Chaque thread = 5 tweets max, percutants, informatifs, ton humain pas corporate.
Format :

🧵 THREAD 1 — [Sujet]
1/
...

Actualités :
{articles_text}
"""
    
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
                return data["choices"][0]["message"]["content"]
            
            print(f"⚠️ Échec avec {model} : {data.get('error', {}).get('message', 'Erreur inconnue')}")
            time.sleep(3) 
            
        except Exception as e:
            print(f"❌ Erreur réseau avec {model} : {e}")
            time.sleep(3)
            
    return None

# --- SEND EMAIL ---
def send_email(threads_content):
    # Nettoyage final pour supprimer les caractères non-ASCII problématiques pour SMTP
    # On force l'encodage et on décode pour nettoyer les caractères invisibles
    clean_content = threads_content.encode('utf-8', 'replace').decode('utf-8')
    clean_content = clean_content.replace('\xa0', ' ')

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "🧵 Tes threads du jour"
    msg["From"] = GMAIL_USER
    msg["To"] = TO_EMAIL

    # Attribution explicite de l'encodage utf-8
    body = MIMEText(clean_content, "plain", "utf-8")
    msg.attach(body)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_USER, TO_EMAIL, msg.as_string())
        print("✅ Email envoyé avec succès.")
    except Exception as e:
        print(f"❌ Erreur critique lors de l'envoi email : {e}")
        raise e

# --- MAIN ---
if __name__ == "__main__":
    articles = fetch_articles()
    if not articles:
        print("No articles fetched.")
        exit(0)
        
    threads = generate_threads(articles)
    
    if threads:
        send_email(threads)
    else:
        print("❌ Échec de la génération.")
        exit(1)
