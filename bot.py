import os
import re
import json
import random
import smtplib
import requests
import email.utils
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from email.mime.base import MIMEBase
from email import encoders
import io

NEWS_API_KEY = os.environ.get("NEWS_API_KEY", "").strip()
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
GMAIL_USER = os.environ.get("GMAIL_USER", "").strip()
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
TO_EMAIL = os.environ.get("RECIPIENT_EMAIL", "").strip()
HF_TOKEN = os.environ.get("HF_TOKEN", "").strip()

STATE_FILE_PATH = "state/history.json"
REPORT_FILE_PATH = "state/latest_threads.txt"
MAX_HISTORY_TOPICS = 40
MAX_HISTORY_TITLES = 60
QUALITY_SCORE_THRESHOLD = 6.5
MAX_GENERATION_ATTEMPTS = 3


def read_int_env(name, default, min_val, max_val):
    try:
        value = int(os.environ.get(name, ""))
    except (TypeError, ValueError):
        value = default
    return max(min_val, min(max_val, value))


TOTAL_POSTS = read_int_env("TOTAL_POSTS", 5, 1, 8)
# Images are optional. Defaulting to zero prevents an unavailable image provider
# from blocking the content pipeline; set IMAGE_POST_COUNT in Actions Variables.
IMAGE_POST_COUNT = min(read_int_env("IMAGE_POST_COUNT", 0, 0, TOTAL_POSTS), TOTAL_POSTS)

# The bot now mixes categories every run instead of choosing one niche for the
# whole run. Queries explicitly cover current cybersecurity, tech/AI and games.
NEWS_QUERY_GROUPS = {
    "cybersecurity": [
        "cybersecurity attack breach vulnerability ransomware zero-day",
        "hacker data leak cybercrime security incident",
        "CVE exploit cloud security Microsoft Google Apple Cisco",
    ],
    "technology": [
        "technology news AI artificial intelligence OpenAI Anthropic Google Nvidia Microsoft",
        "Apple Google Microsoft Meta Nvidia tech industry news",
        "chips semiconductor cloud computing startup technology",
    ],
    "gaming": [
        "video game news GTA 6 Rockstar PlayStation Xbox Nintendo Steam",
        "gaming leak release delay trailer esports game studio",
        "GTA 6 CyberLeek Rockstar Take-Two",
    ],
}

RELATABLE_TOPICS = [
    ("password_hypocrisy", "using weak or reused passwords despite working in tech"),
    ("imposter_syndrome", "feeling like a fraud while learning cybersecurity or programming"),
    ("ai_hype_fatigue", "every product suddenly being called AI-powered"),
    ("spec_sheet_nerd", "memorizing specs for hardware you will never buy"),
    ("group_chat_explainer", "being the friend who explains every tech story to the group chat"),
    ("backlog_shame", "buying games while an untouched backlog keeps growing"),
    ("release_delay_pain", "getting hyped and then seeing a game delayed again"),
    ("leak_spoiler_avoid", "trying to avoid leaks before a huge game release"),
    ("patch_notes_hope", "reading patch notes hoping your favorite bug finally got fixed"),
    ("controller_rage", "blaming lag or the controller after losing"),
    ("beta_tester_unpaid", "becoming an unpaid beta tester for buggy new features"),
    ("preorder_regret", "preordering hardware or a game and regretting it immediately"),
    ("doomscroll_news", "refreshing tech news waiting for the next big announcement"),
    ("cert_vs_reality", "having certificates while still googling basic things"),
    ("one_person_team", "one person doing IT, security, support, and everything else"),
]

FALLBACK_IMAGE_PROMPTS = [
    "realistic technology newsroom desk with laptop and security dashboards",
    "realistic gaming journalist workspace with controller and monitor",
    "realistic server room with rows of modern servers",
]


def clean_text(value):
    return "".join(ch for ch in str(value or "") if ord(ch) < 128).strip()


def load_state():
    default = {"recent_relatable_topic_tags": [], "recent_post_titles": [], "seen_article_urls": []}
    if not os.path.exists(STATE_FILE_PATH):
        return default
    try:
        with open(STATE_FILE_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            return default
        for key, value in default.items():
            if not isinstance(data.get(key), list):
                data[key] = value
        return data
    except (OSError, json.JSONDecodeError) as exc:
        print(f"State file unreadable, starting fresh: {exc}")
        return default


def save_state(state):
    state["recent_relatable_topic_tags"] = state.get("recent_relatable_topic_tags", [])[-MAX_HISTORY_TOPICS:]
    state["recent_post_titles"] = state.get("recent_post_titles", [])[-MAX_HISTORY_TITLES:]
    state["seen_article_urls"] = state.get("seen_article_urls", [])[-200:]
    os.makedirs(os.path.dirname(STATE_FILE_PATH), exist_ok=True)
    with open(STATE_FILE_PATH, "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2)


def write_report(content):
    os.makedirs(os.path.dirname(REPORT_FILE_PATH), exist_ok=True)
    with open(REPORT_FILE_PATH, "w", encoding="utf-8") as handle:
        handle.write(content.rstrip() + "\n")


def fetch_articles(state):
    if not NEWS_API_KEY:
        raise RuntimeError("NEWS_API_KEY is missing")

    seen_urls = set(state.get("seen_article_urls", []))
    articles = []
    seen_keys = set()

    for category, queries in NEWS_QUERY_GROUPS.items():
        for query in queries:
            try:
                response = requests.get(
                    "https://newsapi.org/v2/everything",
                    params={
                        "q": query,
                        "language": "en",
                        "sortBy": "publishedAt",
                        "pageSize": 6,
                        "apiKey": NEWS_API_KEY,
                    },
                    timeout=20,
                )
                response.raise_for_status()
                data = response.json()
            except Exception as exc:
                print(f"News query failed [{category}] {query!r}: {exc}")
                continue

            for article in data.get("articles", []):
                title = clean_text(article.get("title"))
                description = clean_text(article.get("description"))
                url = article.get("url") or ""
                published = article.get("publishedAt") or ""
                source = clean_text((article.get("source") or {}).get("name"))
                key = re.sub(r"\W+", " ", title.lower()).strip()
                if not title or len(title) < 15 or key in seen_keys or url in seen_urls:
                    continue
                if "removed" in title.lower():
                    continue
                seen_keys.add(key)
                articles.append({
                    "category": category,
                    "title": title,
                    "description": description,
                    "source": source,
                    "published": published,
                    "url": url,
                })

    articles.sort(key=lambda item: item.get("published", ""), reverse=True)
    picked = []
    per_category = {key: 0 for key in NEWS_QUERY_GROUPS}
    for article in articles:
        category = article["category"]
        if per_category[category] >= 4:
            continue
        picked.append(article)
        per_category[category] += 1
        if len(picked) >= 12:
            break

    print(f"Fetched {len(picked)} recent articles across categories: {per_category}")
    return picked


def choose_relatable_topics(state, count):
    exclude = set(state.get("recent_relatable_topic_tags", []))
    fresh = [item for item in RELATABLE_TOPICS if item[0] not in exclude]
    random.shuffle(fresh)
    if len(fresh) < count:
        remainder = [item for item in RELATABLE_TOPICS if item not in fresh]
        random.shuffle(remainder)
        fresh.extend(remainder)
    return fresh[:count]


def build_generation_prompt(articles, relatable_topics):
    news_lines = []
    for idx, article in enumerate(articles, 1):
        news_lines.append(
            f"NEWS {idx} | {article['category']} | {article['published']} | {article['source']}\n"
            f"TITLE: {article['title']}\nSUMMARY: {article['description']}\nURL: {article['url']}"
        )
    topic_lines = "\n".join(f"- {tag}: {desc}" for tag, desc in relatable_topics)
    return f"""You write an English-language social feed about cybersecurity, technology, AI, gaming, and internet culture.

Create exactly {TOTAL_POSTS} posts. Do NOT make the feed cybersecurity-only. Prefer current hard news over evergreen filler. When enough source material exists, at least 3 posts must be current news and at least 1 must cover gaming, entertainment, consumer tech or AI. The remaining posts can be relatable observations.

For current stories, state only facts supported by the supplied sources. Never invent quotes, dates, accusations, breach details, or technical exploit details. For rumors/leaks, say they are reported or alleged. Do not provide piracy links, stolen files, credential dumps, or instructions for accessing leaked material.

Tone: sharp, human, concise, scroll-stopping. No corporate PR language, no generic motivational filler, no 'in today's fast-paced world'.

Output ONLY blocks in this exact shape:
POST 1
<title/opening line>
<2-6 short lines of post text>
KEYWORDS: ...
TOPIC_TAG: current_news

POST 2
...

POST {TOTAL_POSTS}
...

CURRENT NEWS:
{chr(10).join(news_lines)}

RELATABLE TOPIC IDEAS:
{topic_lines}
"""


def openrouter_chat(prompt, timeout=60):
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is missing")
    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/sudomarc/thread-bot",
            "X-Title": "Thread Bot",
        },
        json={
            "model": "openrouter/free",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.9,
        },
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"OpenRouter returned no choices: {data}")
    content = choices[0].get("message", {}).get("content", "")
    if not content.strip():
        raise RuntimeError("OpenRouter returned empty content")
    return content.strip()


def parse_posts(raw):
    blocks = re.split(r"(?=^POST\s+\d+\s*$)", raw, flags=re.IGNORECASE | re.MULTILINE)
    posts = []
    for block in blocks:
        match = re.search(r"^POST\s+(\d+)\s*$", block, flags=re.IGNORECASE | re.MULTILINE)
        if not match:
            continue
        number = int(match.group(1))
        body = re.sub(r"^POST\s+\d+\s*$", "", block, count=1, flags=re.IGNORECASE | re.MULTILINE).strip()
        body = re.split(r"\b(?:KEYWORDS|TOPIC_TAG):", body, maxsplit=1, flags=re.IGNORECASE)[0].strip()
        if body:
            title = next((line.strip() for line in body.splitlines() if line.strip()), "Thread Bot post")
            posts.append({"number": number, "title": title, "body": body})
    by_number = {post["number"]: post for post in posts}
    return [by_number[num] for num in sorted(by_number)][:TOTAL_POSTS]


def clean_output(raw):
    posts = parse_posts(raw)
    if len(posts) != TOTAL_POSTS:
        print(f"Generator returned {len(posts)}/{TOTAL_POSTS} parseable posts; using raw output fallback.")
        return raw.strip(), posts
    return "\n\n".join(post["body"].strip() for post in posts), posts


def score_posts_quality(content):
    try:
        raw = openrouter_chat(
            f"Score these social posts from 1-10 for specificity, freshness, clarity and scroll-stopping quality. Output ONLY lines POST N SCORE: number.\n\n{content}",
            timeout=40,
        )
        matches = re.findall(r"POST\s+(\d+)\s+SCORE:\s*(\d+(?:\.\d+)?)", raw, flags=re.IGNORECASE)
        if len(matches) < max(1, TOTAL_POSTS // 2):
            return None
        return sum(float(score) for _, score in matches) / len(matches)
    except Exception as exc:
        print(f"Quality scoring unavailable (non-fatal): {exc}")
        return None


def generate_threads(articles, state):
    relatable_count = max(0, TOTAL_POSTS - min(3, TOTAL_POSTS))
    prompt = build_generation_prompt(articles, choose_relatable_topics(state, relatable_count))
    best = None
    best_score = -1
    for attempt in range(1, MAX_GENERATION_ATTEMPTS + 1):
        print(f"Generation attempt {attempt}/{MAX_GENERATION_ATTEMPTS}...")
        try:
            raw = openrouter_chat(prompt)
            cleaned, posts = clean_output(raw)
            if not posts:
                raise RuntimeError("LLM output could not be parsed")
            score = score_posts_quality(cleaned)
            print(f"Attempt {attempt}: {len(posts)} posts, score={score}")
            if score is None:
                return cleaned, posts
            if score > best_score:
                best, best_score = (cleaned, posts), score
            if score >= QUALITY_SCORE_THRESHOLD:
                return cleaned, posts
        except Exception as exc:
            print(f"Generation failed on attempt {attempt}: {exc}")
    if best:
        return best
    raise RuntimeError("All LLM generation attempts failed")


def generate_hf_image(prompt):
    # Optional feature. Retired models, 410s, DNS failures, etc. never fail a run.
    if not HF_TOKEN or not prompt:
        return None
    endpoint = "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell"
    try:
        response = requests.post(endpoint, headers={"Authorization": f"Bearer {HF_TOKEN}"}, json={"inputs": prompt}, timeout=90)
        if response.status_code == 200 and len(response.content) > 1000:
            return response.content
        print(f"HF image skipped: HTTP {response.status_code} {response.text[:160]}")
    except Exception as exc:
        print(f"HF image skipped: {exc}")
    return None


def add_overlay(image_bytes, title):
    if not image_bytes:
        return None
    try:
        from PIL import Image, ImageDraw, ImageFont
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        draw = ImageDraw.Draw(image)
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size=max(28, image.height // 18))
        except OSError:
            font = ImageFont.load_default()
        draw.rectangle((0, image.height - image.height // 4, image.width, image.height), fill=(0, 0, 0))
        draw.text((image.width // 30, image.height - image.height // 5), title.upper()[:120], fill=(255, 255, 255), font=font)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()
    except Exception as exc:
        print(f"Image overlay failed (non-fatal): {exc}")
        return image_bytes


def send_email(content, images):
    if not (GMAIL_USER and GMAIL_APP_PASSWORD and TO_EMAIL):
        print("Email delivery skipped: Gmail credentials/recipient are not configured.")
        return False

    message = MIMEMultipart()
    message["Subject"] = f"Threads Report — {datetime.now(timezone.utc):%Y-%m-%d}"
    message["From"] = GMAIL_USER
    message["To"] = TO_EMAIL
    message["Date"] = email.utils.formatdate(localtime=True)
    message.attach(MIMEText(content, "plain", "utf-8"))
    for index, image in enumerate(images, 1):
        if image:
            part = MIMEImage(image, name=f"image_{index}.png")
            part.add_header("Content-Disposition", "attachment", filename=f"image_{index}.png")
            message.attach(part)

    txt_part = MIMEBase("text", "plain")
    txt_part.set_payload(content.encode("utf-8"))
    encoders.encode_base64(txt_part)
    txt_part.add_header("Content-Disposition", "attachment", filename="threads_export.txt")
    message.attach(txt_part)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_USER, TO_EMAIL, message.as_bytes())
        print("Email sent successfully.")
        return True
    except Exception as exc:
        # The content pipeline already succeeded. Gmail is a delivery channel,
        # not a reason to fail the GitHub Action and lose the generated report.
        print(f"Email delivery failed (non-fatal): {type(exc).__name__}: {exc}")
        return False


def main():
    state = load_state()
    articles = fetch_articles(state)
    if not articles:
        raise RuntimeError("No usable current articles were returned by NewsAPI")

    content, posts = generate_threads(articles, state)
    content = content.strip()
    write_report(content)
    print("--- FINAL REPORT ---")
    print(content)
    print("--- END REPORT ---")

    images = []
    for index, post in enumerate(posts[:IMAGE_POST_COUNT]):
        prompt = f"{FALLBACK_IMAGE_PROMPTS[index % len(FALLBACK_IMAGE_PROMPTS)]}, inspired by: {post['title']}, realistic editorial photography, no text, no logos"
        raw_image = generate_hf_image(prompt)
        images.append(add_overlay(raw_image, post["title"]) if raw_image else None)

    email_ok = send_email(content, images)
    if not email_ok:
        print("Report remains available at state/latest_threads.txt and as a GitHub Actions artifact.")

    state["recent_post_titles"].extend(post["title"] for post in posts)
    state["seen_article_urls"].extend(article["url"] for article in articles if article.get("url"))
    save_state(state)
    print("State updated.")


if __name__ == "__main__":
    main()
