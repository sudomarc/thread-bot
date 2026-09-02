import email.utils
import io
import json
import os
import random
import re
import smtplib
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests

NEWS_API_KEY = os.environ.get("NEWS_API_KEY", "").strip()
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
GMAIL_USER = os.environ.get("GMAIL_USER", "").strip()
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
TO_EMAIL = os.environ.get("RECIPIENT_EMAIL", "").strip()
HF_TOKEN = os.environ.get("HF_TOKEN", "").strip()
HF_IMAGE_MODEL = os.environ.get("HF_IMAGE_MODEL", "black-forest-labs/FLUX.1-schnell").strip()

STATE_FILE_PATH = "state/history.json"
REPORT_FILE_PATH = "state/latest_threads.txt"
SOURCES_FILE_PATH = "state/latest_sources.txt"
MAX_HISTORY_TOPICS = 40
MAX_HISTORY_TITLES = 60
MAX_HISTORY_URLS = 200
QUALITY_SCORE_THRESHOLD = 6.5
MAX_GENERATION_ATTEMPTS = 3
NEWS_MAX_AGE_HOURS = 72
REQUEST_USER_AGENT = "thread-bot/2.1 (+https://github.com/sudomarc/thread-bot)"
RETRYABLE_HTTP = {408, 409, 425, 429, 500, 502, 503, 504}
TRACKING_QUERY_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid"}


def read_int_env(name, default, min_val, max_val):
    try:
        value = int(os.environ.get(name, ""))
    except (TypeError, ValueError):
        value = default
    return max(min_val, min(max_val, value))


def read_bool_env(name, default=False):
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


TOTAL_POSTS = read_int_env("TOTAL_POSTS", 5, 1, 8)
IMAGE_POST_COUNT = min(read_int_env("IMAGE_POST_COUNT", 0, 0, TOTAL_POSTS), TOTAL_POSTS)
ENABLE_LLM_SCORING = read_bool_env("ENABLE_LLM_SCORING", False)

NEWS_QUERY_GROUPS = {
    "cybersecurity": 'cybersecurity OR ransomware OR breach OR vulnerability OR "zero-day" OR hacker OR "data leak" OR cybercrime',
    "technology": 'technology OR AI OR "artificial intelligence" OR OpenAI OR Anthropic OR Nvidia OR Apple OR Google OR Microsoft OR semiconductor OR cloud',
    "gaming": '"GTA 6" OR "GTA VI" OR Rockstar OR "Take-Two" OR PlayStation OR Xbox OR Nintendo OR Steam OR gaming OR "game delay" OR esports',
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
    text = unicodedata.normalize("NFC", str(value or ""))
    return "".join(ch for ch in text if ch in "\n\t" or ord(ch) >= 32).strip()


def title_key(value):
    return re.sub(r"[^a-z0-9]+", " ", clean_text(value).lower()).strip()


def canonicalize_url(value):
    url = str(value or "").strip()
    if not url:
        return ""
    try:
        parts = urlsplit(url)
        query = [(key, val) for key, val in parse_qsl(parts.query, keep_blank_values=True) if not key.lower().startswith("utm_") and key.lower() not in TRACKING_QUERY_KEYS]
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), urlencode(query), ""))
    except ValueError:
        return url


def parse_iso_datetime(value):
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def default_state():
    return {
        "schema_version": 2,
        "recent_relatable_topic_tags": [],
        "recent_post_titles": [],
        "seen_article_urls": [],
        "last_run_at": None,
    }


def load_state():
    default = default_state()
    if not os.path.exists(STATE_FILE_PATH):
        return default
    try:
        with open(STATE_FILE_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"State file unreadable; starting fresh: {exc}")
        return default
    if not isinstance(data, dict):
        return default
    for key in ("recent_relatable_topic_tags", "recent_post_titles", "seen_article_urls"):
        if not isinstance(data.get(key), list):
            data[key] = []
    if data.get("last_run_at") is not None and not isinstance(data.get("last_run_at"), str):
        data["last_run_at"] = None
    data["schema_version"] = 2
    return data


def save_state(state):
    state["schema_version"] = 2
    state["recent_relatable_topic_tags"] = list(dict.fromkeys(state.get("recent_relatable_topic_tags", [])))[-MAX_HISTORY_TOPICS:]
    state["recent_post_titles"] = list(dict.fromkeys(state.get("recent_post_titles", [])))[-MAX_HISTORY_TITLES:]
    state["seen_article_urls"] = list(dict.fromkeys(state.get("seen_article_urls", [])))[-MAX_HISTORY_URLS:]
    state["last_run_at"] = datetime.now(timezone.utc).isoformat()
    state_dir = os.path.dirname(STATE_FILE_PATH) or "."
    os.makedirs(state_dir, exist_ok=True)
    tmp_path = STATE_FILE_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    os.replace(tmp_path, STATE_FILE_PATH)


def write_report(content, sources):
    state_dir = os.path.dirname(REPORT_FILE_PATH) or "."
    os.makedirs(state_dir, exist_ok=True)
    with open(REPORT_FILE_PATH, "w", encoding="utf-8") as handle:
        handle.write(content.rstrip() + "\n")
    with open(SOURCES_FILE_PATH, "w", encoding="utf-8") as handle:
        for idx, article in enumerate(sources, 1):
            handle.write(
                f"SOURCE {idx} | {article['category']} | {article['published']} | {article['source']}\n"
                f"{article['title']}\n{article['url']}\n\n"
            )


def request_with_retries(method, url, *, retries=3, timeout=20, **kwargs):
    headers = dict(kwargs.pop("headers", {}) or {})
    headers.setdefault("User-Agent", REQUEST_USER_AGENT)
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            response = requests.request(method, url, timeout=timeout, headers=headers, **kwargs)
            if response.status_code not in RETRYABLE_HTTP:
                return response
            last_error = RuntimeError(f"HTTP {response.status_code}: {response.text[:250]}")
        except requests.RequestException as exc:
            last_error = exc
        if attempt < retries:
            delay = min(2 ** (attempt - 1), 8) + random.random()
            time.sleep(delay)
    raise RuntimeError(f"Request failed after {retries} attempts: {last_error}")


def validate_runtime_config():
    missing = [name for name, value in (("NEWS_API_KEY", NEWS_API_KEY), ("OPENROUTER_API_KEY", OPENROUTER_API_KEY)) if not value]
    if missing:
        raise RuntimeError("Missing required environment variables: " + ", ".join(missing))


def fetch_articles(state):
    if not NEWS_API_KEY:
        raise RuntimeError("NEWS_API_KEY is missing")

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=NEWS_MAX_AGE_HOURS)
    seen_urls = {canonicalize_url(url) for url in state.get("seen_article_urls", [])}
    picked = []
    seen_keys = set()
    failures = 0

    for category, query in NEWS_QUERY_GROUPS.items():
        try:
            response = request_with_retries(
                "GET",
                "https://newsapi.org/v2/everything",
                retries=3,
                timeout=20,
                headers={"X-Api-Key": NEWS_API_KEY},
                params={
                    "q": query,
                    "language": "en",
                    "sortBy": "publishedAt",
                    "pageSize": 25,
                    "from": cutoff.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "to": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                },
            )
            if response.status_code >= 400:
                if response.status_code in {401, 403}:
                    raise RuntimeError(f"NewsAPI authentication/permission error HTTP {response.status_code}")
                raise RuntimeError(f"NewsAPI error HTTP {response.status_code}: {response.text[:250]}")
            data = response.json()
        except Exception as exc:
            failures += 1
            print(f"News query failed [{category}]: {type(exc).__name__}: {exc}")
            continue

        category_count = 0
        for article in data.get("articles", []):
            title = clean_text(article.get("title"))
            description = clean_text(article.get("description"))
            url = canonicalize_url(article.get("url"))
            published = clean_text(article.get("publishedAt"))
            source = clean_text((article.get("source") or {}).get("name"))
            published_at = parse_iso_datetime(published)
            key = title_key(title)
            if not title or len(title) < 15 or not url or key in seen_keys or url in seen_urls:
                continue
            if not published_at or published_at < cutoff or published_at > now:
                continue
            if "removed by the source" in title.lower():
                continue
            seen_keys.add(key)
            picked.append({
                "category": category,
                "title": title,
                "description": description,
                "source": source or "Unknown source",
                "published": published,
                "url": url,
            })
            category_count += 1
            if category_count >= 8:
                break

    if failures == len(NEWS_QUERY_GROUPS):
        raise RuntimeError("All NewsAPI category queries failed")

    picked.sort(key=lambda item: parse_iso_datetime(item["published"]) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    per_category = {category: 0 for category in NEWS_QUERY_GROUPS}
    balanced = []
    for article in picked:
        category = article["category"]
        if per_category[category] >= 4:
            continue
        balanced.append(article)
        per_category[category] += 1
        if len(balanced) >= max(8, TOTAL_POSTS + 3):
            break

    minimum = min(5, max(3, TOTAL_POSTS))
    if len(balanced) < minimum:
        raise RuntimeError(f"Too few usable current articles: {len(balanced)}")
    print(f"Fetched {len(balanced)} recent articles across categories: {per_category}")
    return balanced


def choose_relatable_topics(state, count):
    exclude = set(state.get("recent_relatable_topic_tags", []))
    fresh = [item for item in RELATABLE_TOPICS if item[0] not in exclude]
    random.shuffle(fresh)
    if len(fresh) < count:
        remainder = [item for item in RELATABLE_TOPICS if item not in fresh]
        random.shuffle(remainder)
        fresh.extend(remainder)
    return fresh[:count]


def build_generation_prompt(articles, relatable_topics, state):
    news_lines = []
    for idx, article in enumerate(articles, 1):
        news_lines.append(
            f"NEWS {idx} | {article['category']} | {article['published']} | {article['source']}\n"
            f"TITLE: {article['title']}\nSUMMARY: {article['description']}\nURL: {article['url']}"
        )
    topic_lines = "\n".join(f"- {tag}: {desc}" for tag, desc in relatable_topics) or "- none"
    previous_titles = state.get("recent_post_titles", [])[-10:]
    history_hint = "\n".join(f"- {title}" for title in previous_titles) or "- none"
    required_news = min(3, TOTAL_POSTS)
    return f"""You write an English-language social feed about cybersecurity, technology, AI, gaming, and internet culture.

Create exactly {TOTAL_POSTS} posts. At least {required_news} posts must be current-news posts. When a gaming source is supplied, at least one current-news post must use a gaming source. Remaining posts may be relatable observations.

Every current-news post MUST use exactly one SOURCE: NEWS N marker. Every relatable post MUST use SOURCE: NONE. Do not reuse the same NEWS source in two posts. Use only the supplied source facts. Never invent quotes, dates, accusations, breach details, exploit details, or unverified claims. For rumors/leaks, say reported/alleged. Do not provide piracy links, stolen files, credential dumps, or instructions for accessing stolen material.

Choose TOPIC_TAG only from the supplied relatable tags for relatable posts; use current_news for news posts.

Tone: sharp, human, concise, scroll-stopping. No corporate PR language. No generic motivational filler.

Avoid repeating these recent titles or obvious paraphrases:
{history_hint}

Output ONLY this exact structure:
POST 1
<title/opening line>
<2-6 short lines of post text>
KEYWORDS: keyword1, keyword2
TOPIC_TAG: current_news OR one supplied relatable tag
SOURCE: NEWS 1 OR NONE

Continue until POST {TOTAL_POSTS}. Use one SOURCE line per post.

CURRENT NEWS:
{chr(10).join(news_lines)}

RELATABLE TOPIC IDEAS:
{topic_lines}
"""


def openrouter_chat(prompt, timeout=60):
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is missing")
    response = request_with_retries(
        "POST",
        "https://openrouter.ai/api/v1/chat/completions",
        retries=4,
        timeout=timeout,
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/sudomarc/thread-bot",
            "X-Title": "Thread Bot",
        },
        json={
            "model": "openrouter/free",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.85,
        },
    )
    if response.status_code >= 400:
        raise RuntimeError(f"OpenRouter HTTP {response.status_code}: {response.text[:300]}")
    data = response.json()
    choices = data.get("choices") or []
    if not choices:
        error = data.get("error") or {}
        raise RuntimeError(f"OpenRouter returned no choices: {error.get('message', 'unknown error')}")
    content = choices[0].get("message", {}).get("content", "")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("OpenRouter returned empty content")
    return content.strip()


def parse_posts(raw):
    blocks = re.split(r"(?=^POST\s+\d+\s*$)", str(raw or ""), flags=re.IGNORECASE | re.MULTILINE)
    posts = []
    for block in blocks:
        match = re.search(r"^POST\s+(\d+)\s*$", block, flags=re.IGNORECASE | re.MULTILINE)
        if not match:
            continue
        number = int(match.group(1))
        body = re.sub(r"^POST\s+\d+\s*$", "", block, count=1, flags=re.IGNORECASE | re.MULTILINE).strip()
        source_match = re.search(r"^SOURCE:\s*(.+?)\s*$", body, flags=re.IGNORECASE | re.MULTILINE)
        tag_match = re.search(r"^TOPIC_TAG:\s*(.+?)\s*$", body, flags=re.IGNORECASE | re.MULTILINE)
        keyword_match = re.search(r"^KEYWORDS:\s*(.+?)\s*$", body, flags=re.IGNORECASE | re.MULTILINE)
        content_only = re.split(r"^KEYWORDS:\s*.*$|^TOPIC_TAG:\s*.*$|^SOURCE:\s*.*$", body, maxsplit=1, flags=re.IGNORECASE | re.MULTILINE)[0].strip()
        lines = [line.strip() for line in content_only.splitlines() if line.strip()]
        if not lines:
            continue
        posts.append({
            "number": number,
            "title": lines[0],
            "body": content_only,
            "keywords": [item.strip() for item in (keyword_match.group(1).split(",") if keyword_match else []) if item.strip()],
            "source": source_match.group(1).strip() if source_match else "NONE",
            "topic_tag": tag_match.group(1).strip() if tag_match else "",
        })
    return posts


def validate_posts(posts, articles, relatable_topics=None, previous_titles=None):
    if len(posts) != TOTAL_POSTS:
        raise ValueError(f"LLM produced {len(posts)}/{TOTAL_POSTS} valid posts")
    numbers = [post.get("number") for post in posts]
    expected = list(range(1, TOTAL_POSTS + 1))
    if numbers != expected or len(set(numbers)) != TOTAL_POSTS:
        raise ValueError(f"Post numbering is not exactly sequential: {numbers}")
    if any(not clean_text(post.get("body")) for post in posts):
        raise ValueError("LLM produced an empty post")
    if any(len(post.get("body", "")) > 1500 for post in posts):
        raise ValueError("LLM produced an excessively long post")

    allowed_tags = {tag for tag, _ in (relatable_topics or RELATABLE_TOPICS)}
    source_ids = []
    source_seen = set()
    for post in posts:
        source = post.get("source", "NONE").strip().upper()
        tag = post.get("topic_tag", "").strip()
        if source.startswith("NEWS "):
            parts = source.split()
            if len(parts) != 2 or not parts[1].isdigit():
                raise ValueError(f"Invalid source marker: {source}")
            source_id = int(parts[1])
            if not 1 <= source_id <= len(articles):
                raise ValueError(f"Source marker out of range: {source}")
            if source_id in source_seen:
                raise ValueError(f"Source reused by multiple posts: {source}")
            source_seen.add(source_id)
            source_ids.append(source_id)
            if tag != "current_news":
                raise ValueError("Current-news post must use TOPIC_TAG: current_news")
        elif source != "NONE":
            raise ValueError(f"Invalid source marker: {source}")
        elif tag == "current_news":
            raise ValueError("Relatable post cannot use TOPIC_TAG: current_news")
        elif tag not in allowed_tags:
            raise ValueError(f"Unknown relatable topic tag: {tag}")

    required_news = min(3, TOTAL_POSTS)
    if len(source_ids) < required_news:
        raise ValueError(f"Need at least {required_news} source-grounded posts, got {len(source_ids)}")

    gaming_ids = {idx + 1 for idx, article in enumerate(articles) if article.get("category") == "gaming"}
    if gaming_ids and not gaming_ids.intersection(source_ids):
        raise ValueError("LLM ignored all supplied gaming sources")

    normalized_previous = {title_key(title) for title in (previous_titles or []) if title}
    current_titles = [title_key(post.get("title")) for post in posts]
    if len(set(current_titles)) != len(current_titles):
        raise ValueError("LLM produced duplicate post titles")
    if normalized_previous and any(title in normalized_previous for title in current_titles):
        raise ValueError("LLM repeated a recent post title")
    return True


def score_posts_quality(posts):
    if not ENABLE_LLM_SCORING:
        return None
    labeled = "\n\n".join(f"POST {post['number']}\n{post['body']}" for post in posts)
    try:
        raw = openrouter_chat(
            "Score each post 1-10 for specificity, freshness, clarity and scroll-stopping quality. "
            "Output ONLY one line per post in the form POST N SCORE: number.\n\n" + labeled,
            timeout=40,
        )
        matches = re.findall(r"POST\s+(\d+)\s+SCORE:\s*(\d+(?:\.\d+)?)", raw, flags=re.IGNORECASE)
        scores = {int(num): float(score) for num, score in matches if 0 < float(score) <= 10}
        if any(num not in scores for num in range(1, TOTAL_POSTS + 1)):
            print("Quality scoring response incomplete; skipping scoring for this attempt.")
            return None
        return sum(scores.values()) / TOTAL_POSTS
    except Exception as exc:
        print(f"Quality scoring unavailable; skipping scoring: {type(exc).__name__}: {exc}")
        return None


def generate_threads(articles, state):
    required_news = min(3, TOTAL_POSTS)
    relatable_count = max(0, TOTAL_POSTS - required_news)
    relatable_topics = choose_relatable_topics(state, relatable_count)
    prompt = build_generation_prompt(articles, relatable_topics, state)
    best = None
    best_score = -1.0

    for attempt in range(1, MAX_GENERATION_ATTEMPTS + 1):
        print(f"Generation attempt {attempt}/{MAX_GENERATION_ATTEMPTS}...")
        try:
            raw = openrouter_chat(prompt)
            posts = parse_posts(raw)
            validate_posts(posts, articles, relatable_topics, state.get("recent_post_titles", []))
            score = score_posts_quality(posts)
            print(f"Attempt {attempt}: {len(posts)} posts, score={score}")
            candidate = "\n\n".join(post["body"].strip() for post in posts)
            if score is None:
                return candidate, posts
            if score > best_score:
                best, best_score = (candidate, posts), score
            if score >= QUALITY_SCORE_THRESHOLD:
                return candidate, posts
        except Exception as exc:
            print(f"Generation attempt {attempt} rejected: {type(exc).__name__}: {exc}")

    if best:
        print(f"No attempt cleared {QUALITY_SCORE_THRESHOLD}; keeping best score {best_score:.1f}.")
        return best
    raise RuntimeError("All LLM generation attempts failed validation")


def generate_hf_image(prompt):
    if not HF_TOKEN or not prompt:
        return None
    try:
        response = request_with_retries(
            "POST",
            f"https://router.huggingface.co/hf-inference/models/{HF_IMAGE_MODEL}",
            retries=2,
            timeout=90,
            headers={"Authorization": f"Bearer {HF_TOKEN}"},
            json={"inputs": prompt},
        )
        content_type = response.headers.get("Content-Type", "")
        if response.status_code == 200 and response.content and (content_type.startswith("image/") or len(response.content) > 1000):
            return response.content
        print(f"HF image skipped: HTTP {response.status_code} {response.text[:160]}")
    except Exception as exc:
        print(f"HF image skipped: {type(exc).__name__}: {exc}")
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
        draw.text((image.width // 30, image.height - image.height // 5), clean_text(title).upper()[:120], fill=(255, 255, 255), font=font)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()
    except Exception as exc:
        print(f"Image overlay failed (non-fatal): {type(exc).__name__}: {exc}")
        return image_bytes


def send_email(content, images):
    if not (GMAIL_USER and GMAIL_APP_PASSWORD and TO_EMAIL):
        print("Email delivery skipped: Gmail configuration is incomplete.")
        return False

    message = MIMEMultipart()
    message["Subject"] = f"Threads Report - {datetime.now(timezone.utc):%Y-%m-%d}"
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
        print(f"Email delivery failed (non-fatal): {type(exc).__name__}: {exc}")
        return False


def used_articles_from_posts(posts, articles):
    indices = []
    for post in posts:
        source = post.get("source", "NONE").strip().upper()
        if source.startswith("NEWS "):
            indices.append(int(source.split()[1]) - 1)
    return [articles[index] for index in indices]


def main():
    validate_runtime_config()
    state = load_state()
    articles = fetch_articles(state)
    content, posts = generate_threads(articles, state)
    used_articles = used_articles_from_posts(posts, articles)
    write_report(content, used_articles)

    print("--- FINAL REPORT ---")
    print(content)
    print("--- END REPORT ---")

    state["recent_post_titles"].extend(post["title"] for post in posts)
    state["seen_article_urls"].extend(article["url"] for article in used_articles if article.get("url"))
    state["recent_relatable_topic_tags"].extend(
        post["topic_tag"] for post in posts if post.get("source", "").upper() == "NONE" and post.get("topic_tag") in {tag for tag, _ in RELATABLE_TOPICS}
    )
    save_state(state)

    images = []
    for index, post in enumerate(posts[:IMAGE_POST_COUNT]):
        prompt = (
            f"{FALLBACK_IMAGE_PROMPTS[index % len(FALLBACK_IMAGE_PROMPTS)]}, "
            f"inspired by: {post['title']}, realistic editorial photography, no text, no logos"
        )
        raw_image = generate_hf_image(prompt)
        images.append(add_overlay(raw_image, post["title"]) if raw_image else None)

    send_email(content, images)
    print("State updated.")


if __name__ == "__main__":
    main()
