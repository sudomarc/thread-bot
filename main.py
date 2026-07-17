import os
import re
import json
import random
import smtplib
import requests
import time
import email.utils
import io
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from email.mime.base import MIMEBase
from email import encoders

# ─── UTILS ────────────────────────────────────────────────────────────────────

def safe_encode(text):
    if not isinstance(text, str):
        text = str(text)
    return "".join(char for char in text if ord(char) < 128)

# ─── CONFIG ───────────────────────────────────────────────────────────────────

NEWS_API_KEY = os.environ.get("NEWS_API_KEY", "")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
GMAIL_USER = safe_encode(os.environ.get("GMAIL_USER", ""))
GMAIL_APP_PASSWORD = safe_encode(os.environ.get("GMAIL_APP_PASSWORD", ""))
HF_TOKEN = os.environ.get("HF_TOKEN", "")
TO_EMAIL = os.environ.get("RECIPIENT_EMAIL", "")

# ─── CONFIGURABLE COUNTS (env-overridable, with sane clamps) ─────────────────
# Read from env (repo Variables, not secrets — not sensitive) so Patrick can
# tweak these from GitHub Settings without touching code. Defaults preserve
# current behavior (5 posts, 3 images) if unset or invalid.

def _read_int_env(name, default, min_val, max_val):
    raw = os.environ.get(name, "")
    try:
        val = int(raw)
    except (ValueError, TypeError):
        val = default
    return max(min_val, min(max_val, val))

TOTAL_POSTS = _read_int_env("TOTAL_POSTS", default=5, min_val=1, max_val=8)
IMAGE_POST_COUNT = _read_int_env("IMAGE_POST_COUNT", default=3, min_val=0, max_val=TOTAL_POSTS)
# IMAGE_POST_COUNT must never exceed TOTAL_POSTS even if env vars disagree
IMAGE_POST_COUNT = min(IMAGE_POST_COUNT, TOTAL_POSTS)

QUALITY_SCORE_THRESHOLD = 6.5  # out of 10, average across all posts
MAX_GENERATION_ATTEMPTS = 3  # 1 normal + up to 2 regenerations if quality is low

STATE_FILE_PATH = "state/history.json"
MAX_HISTORY_TOPICS = 20   # how many recent relatable topic tags to remember
MAX_HISTORY_TITLES = 30   # how many recent post titles to remember (log)

# ─── NICHE ROTATION ───────────────────────────────────────────────────────────
# Infrastructure for multiple niches, defaulted to cybersecurity-only so
# behavior doesn't silently change. Add more niches to this list later if
# wanted (e.g. "ai", "dev") — each needs its own NEWS_TOPICS/RELATABLE_TOPICS.
NICHES = ["cybersecurity"]

NEWS_TOPICS_BY_NICHE = {
    "cybersecurity": [
        "CVE-2024",
        "data breach $1M",
        "Google sued",
        "Microsoft hacked",
        "Cloudflare vulnerability",
        "AWS zero-day",
        "ransomware attack",
        "AI security exploit",
        "phishing campaign",
        "supply chain attack",
    ],
}

# Relatable topic pool with stable TAG identifiers (used for rotation
# tracking and history logging — see TOPIC_TAG parsing below).
RELATABLE_TOPICS_BY_NICHE = {
    "cybersecurity": [
        ("imposter_syndrome", "imposter syndrome starting out in cybersecurity / feeling like a fraud despite certs"),
        ("untested_backups", "never testing your backups until it's too late"),
        ("password_hypocrisy", "password reuse / using weak passwords even among security people"),
        ("own_phishing_test", "getting phished by your own company's phishing test"),
        ("budget_disparity", "security budget vs marketing budget disparity"),
        ("audit_dread", "the dread of hearing the word audit"),
        ("one_person_team", "one-person IT/security team doing everything"),
        ("compliance_theater", "compliance theater vs actual security"),
        ("users_click_anyway", "users clicking things they shouldn't no matter how many trainings"),
        ("cert_vs_reality", "the gap between LinkedIn cert-flexing and actual job reality"),
    ],
}

NEWS_TONES = [
    "cold and institutional, like an AFP/Reuters wire report",
    "dry and matter-of-fact, just the facts landing like a gut punch",
    "urgent and blunt, like breaking-news alert energy",
]

TOPICS = NEWS_TOPICS_BY_NICHE["cybersecurity"]  # kept for backward compat with fetch_articles()

# Fallback image prompt used when the LLM fails to produce a usable one.
# Keeps the "3 images always" guarantee even if parsing/formatting breaks.
FALLBACK_IMAGE_PROMPTS = [
    "anonymous person in dark suit typing on laptop in dimly lit office, face out of frame, realistic press photo, 4K",
    "modern tech company open office, empty desk, screen with code, cold fluorescent light, realistic AFP wire photo, 4K, no people, no text",
    "empty server room, rows of blinking servers, cold blue light, realistic press photo, 4K, no text",
]

# ─── FETCH NEWS ───────────────────────────────────────────────────────────────

def fetch_articles():
    articles = []
    seen_titles = set()
    error_count = 0

    for topic in TOPICS:
        url = (
            f"https://newsapi.org/v2/everything"
            f"?q={topic}&language=en&sortBy=publishedAt&pageSize=5"
            f"&apiKey={NEWS_API_KEY}"
        )
        try:
            r = requests.get(url, timeout=10)
            data = r.json()

            if data.get("articles"):
                for a in data["articles"]:
                    title = safe_encode(a.get('title', ''))
                    desc = safe_encode(a.get('description', '') or '')

                    title_key = title.lower()[:60]
                    if title_key in seen_titles or not title:
                        continue

                    if not has_concrete_fact(title, desc):
                        print(f"Skipping vague article: {title[:50]}")
                        continue

                    seen_titles.add(title_key)
                    articles.append(f"- {title}: {desc}")
        except Exception as e:
            print(f"Error fetching news for {topic}: {e}")
            error_count += 1

    # Distinguish "API is broken" (every single query errored — bad key,
    # network down, service outage) from "API worked fine, just a quiet
    # news day" (queries succeeded, filter just found nothing concrete).
    # The former is a real failure that should trigger the failure-email
    # alert; the latter is normal and should stay a silent exit(0). Without
    # this check, an expired NEWS_API_KEY would silently produce "no
    # articles" forever with no alert ever firing.
    if error_count == len(TOPICS) and len(TOPICS) > 0:
        raise RuntimeError(
            f"All {len(TOPICS)} news queries failed (likely bad NEWS_API_KEY or API outage) — "
            f"not a quiet news day, this is an actual failure."
        )

    return "\n".join(articles[:9])

def has_concrete_fact(title, desc):
    companies = [
        "google", "microsoft", "apple", "amazon", "meta", "facebook",
        "cloudflare", "aws", "openai", "anthropic", "nvidia", "intel",
        "uber", "stripe", "twitter", "x corp", "github", "gitlab",
        "cisco", "ibm", "oracle", "salesforce", "slack", "zoom"
    ]
    action_verbs = [
        "sued", "hack", "fine", "ban", "breach", "leak", "stolen",
        "exploit", "vulnerability", "attack", "arrest", "charge",
        "recall", "withdraw", "shutdown", "restrict"
    ]

    combined_text = (title + " " + desc).lower()

    if any(company in combined_text for company in companies):
        return True
    if "cve-20" in combined_text:
        return True
    if "$" in combined_text or " million " in combined_text or " billion " in combined_text:
        return True
    if any(verb in combined_text for verb in action_verbs):
        return True

    return False

# ─── GENERATE THREADS ─────────────────────────────────────────────────────────

def pick_relatable_topics(niche, exclude_tags, count):
    """
    Pick `count` (tag, description) pairs for relatable posts, preferring
    topics NOT in exclude_tags (recently used, per state file) to reduce
    repetition across runs. Falls back to the full pool (allowing reuse)
    if there aren't enough fresh topics left — better to repeat once than
    to crash or come up short.
    """
    pool = RELATABLE_TOPICS_BY_NICHE.get(niche, RELATABLE_TOPICS_BY_NICHE["cybersecurity"])
    fresh = [t for t in pool if t[0] not in exclude_tags]

    if len(fresh) >= count:
        random.shuffle(fresh)
        return fresh[:count]

    # Not enough fresh topics — reuse allowed, but keep the fresh ones first
    print(f"Only {len(fresh)} fresh relatable topics available (need {count}); reusing some recent ones.")
    remainder_pool = pool[:]
    random.shuffle(remainder_pool)
    combined = fresh + [t for t in remainder_pool if t not in fresh]
    return combined[:count]


def generate_threads(articles_text, exclude_topic_tags=None, niche="cybersecurity"):
    exclude_topic_tags = exclude_topic_tags or set()
    relatable_count = TOTAL_POSTS - 1  # POST 1 is always news
    chosen_topics = pick_relatable_topics(niche, exclude_topic_tags, relatable_count)
    news_tone = random.choice(NEWS_TONES)

    topics_listing = "\n".join(
        f'- TAG "{tag}": {desc}' for tag, desc in chosen_topics
    )

    # Build POST 2..N sections dynamically so the prompt always matches
    # TOTAL_POSTS exactly (a hardcoded "POST 1..POST 5" template would go
    # silently out of sync the moment TOTAL_POSTS is configured differently).
    relatable_sections = []
    for i in range(2, TOTAL_POSTS + 1):
        topic_tag, topic_desc = chosen_topics[i - 2]
        relatable_sections.append(f"""POST {i}
[ONE OR TWO SENTENCES MAX — about: {topic_desc}]
KEYWORDS: keyword1, keyword2
TOPIC_TAG: {topic_tag}
IMAGE_PROMPT: [scene description]""")
    relatable_block = "\n\n".join(relatable_sections)

    prompt = f"""You write like a real person on Twitter/Threads who's obsessed with tech and cybersecurity — NOT a corporate blog, NOT a SaaS marketing account.

Generate exactly {TOTAL_POSTS} DIFFERENT Threads posts in ENGLISH:
- POST 1 = a hard-news post based on ONE of the news articles below (pick the sharpest one).
- POST 2 through POST {TOTAL_POSTS} = RELATABLE / MEME-STYLE posts about everyday life in cybersecurity/infosec, one per assigned topic below. NOT based on the news.

POST 1 — NEWS STYLE (4 to 6 short lines, line breaks for rhythm):
Tone for this run: {news_tone}.
Example:
Oracle PeopleSoft has a zero-day.
CVE-2026-35273.
It's being exploited RIGHT NOW.
If you're running PeopleSoft and haven't patched —
you're not "at risk."
You're already owned.

- Short fragments. NO corporate vocabulary ("consequences," "implications," "leverage," "robust").
- Specific > vague. Name the CVE, the company, the number, the mechanism from the article.
- Punchline lands HARD and concrete. Never end on generic advice alone.

POST 2 THROUGH POST {TOTAL_POSTS} — RELATABLE/MEME STYLE — STRICT LENGTH LIMIT:
MAXIMUM 2 SHORT SENTENCES TOTAL PER POST. NOT 4-6 lines. ONE OR TWO SENTENCES ONLY.
Think tweet-length, not thread-length. A single punchy joke, not a mini-story.

Good length example (this is the target length, do not exceed it):
"Got a new cert. Still Google how to unplug a router."

Each relatable post below is assigned a specific topic (with a TAG you must echo back exactly in the TOPIC_TAG field) — write about THAT topic for THAT post, don't swap them around:
{topics_listing}

Style: self-aware, self-deprecating, sounds like a real person venting/joking. NO hashtags, no "thoughts?" bait, NO listicle format.

OUTPUT FORMAT — FOLLOW EXACTLY, EACH TAG ON ITS OWN LINE, NOTHING ELSE ON THAT LINE:

POST 1
[line 1]
[line 2]
[line 3]
[line 4 or 5 — punchline]
KEYWORDS: keyword1, keyword2
IMAGE_PROMPT: [scene description]

{relatable_block}

CRITICAL FORMAT RULES:
- ALWAYS use proper apostrophes in contractions: "it's", "I'm", "you're", "don't", "can't" — NEVER write them without the apostrophe ("its", "Im", "youre", "dont"). Missing apostrophes cause words to visually run together and look broken.
- "KEYWORDS:", "TOPIC_TAG:", and "IMAGE_PROMPT:" MUST each start on their OWN new line. Never append them to the end of a content line.
- Always leave a line break BEFORE each of these tags.
- Never skip IMAGE_PROMPT or TOPIC_TAG for any post, even short ones.
- TOPIC_TAG must be copied EXACTLY as given above (e.g. "imposter_syndrome"), not reworded.

IMAGE_PROMPT STYLE GUIDE — French TV news / BFM style:
- Realistic press photo style, NOT sci-fi, NOT cyberpunk, NOT illustration
- POST 1: serious, institutional, cold, urgent — like AFP/Reuters wire photo. Real-world location (office, courtroom, government building, server room).
- POST 2 onward: relatable everyday office/home realism, mundane/tired mood, still realistic press-photo style
- Anonymous figures only, NO real faces, NO named people
- Desaturated, realistic colors, NOT neon
- Sharp focus, shallow depth of field, 4K, no text, no watermark, no logos

RULES:
- OUTPUT ONLY THE {TOTAL_POSTS} POSTS. No intro, no conclusion, no explanation.
- POST 1 = 4 to 6 lines. POST 2 onward = 1 to 2 sentences ONLY, this is a hard limit.
- NO corporate tone, NO marketing language.
- Never write "stay safe," "protect your systems," "consider the implications," or "raises questions about."

News (use ONLY for POST 1, pick the single sharpest article):
{articles_text}

"""

    models_to_try = [
        "deepseek/deepseek-chat-v3-0324:free",
        "meta-llama/llama-3.3-70b-instruct:free",
        "openrouter/auto",
        "qwen/qwen3-coder:free"
    ]

    for model in models_to_try:
        print(f"Trying model: {model}...")
        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/sudomarc/thread-bot",
                    "X-Title": "Thread Bot"
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}]
                },
                timeout=45
            )
            data = response.json()

            if "choices" in data:
                print(f"Success with {model}!")
                return safe_encode(data["choices"][0]["message"]["content"])

            print(f"Failed with {model}: {data.get('error', {}).get('message', 'Unknown')}")
            time.sleep(3)
        except Exception as e:
            print(f"Network error with {model}: {e}")
            time.sleep(3)

    return None

# ─── EXTRACT DATA FROM THREADS (ROBUST REGEX-BASED PARSING) ──────────────────

# Matches KEYWORDS: even if it's glued to the end of a preceding sentence,
# e.g. "...embarrassment.KEYWORDS: keyword1, keyword2" — this was the bug
# that caused both the visible "KEYWORDS:" leak in the email AND the missing
# images (because IMAGE_PROMPT parsing used the same fragile logic).
KEYWORDS_RE = re.compile(r"KEYWORDS:\s*(.*?)(?=TOPIC_TAG:|IMAGE_PROMPT:|POST\s+\d|\Z)", re.IGNORECASE | re.DOTALL)
TOPIC_TAG_RE = re.compile(r"TOPIC_TAG:\s*(.*?)(?=KEYWORDS:|IMAGE_PROMPT:|POST\s+\d|\Z)", re.IGNORECASE | re.DOTALL)
IMAGE_PROMPT_RE = re.compile(r"IMAGE_PROMPT:\s*(.*?)(?=POST\s+\d|\Z)", re.IGNORECASE | re.DOTALL)
POST_SPLIT_RE = re.compile(r"POST\s+(\d+)\s*\n", re.IGNORECASE)


def extract_posts_data(threads_content):
    """
    Regex-based, tolerant of the LLM gluing tags onto the previous line
    (no leading newline) instead of putting them on their own line.
    Returns list of dicts: [{title, image_prompt}, ...] — always length 3,
    padding with fallback prompts if the LLM output was malformed.
    """
    posts = []

    # Split on "POST N" markers regardless of what's on the rest of that line
    chunks = re.split(r"(?=POST\s+\d)", threads_content, flags=re.IGNORECASE)

    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk or not re.match(r"POST\s+\d", chunk, re.IGNORECASE):
            continue

        # Strip the "POST N" header line itself
        body = re.sub(r"^POST\s+\d+\s*\n?", "", chunk, flags=re.IGNORECASE).strip()

        # Pull out KEYWORDS/TOPIC_TAG/IMAGE_PROMPT wherever they are (even glued to text)
        kw_match = KEYWORDS_RE.search(body)
        tag_match = TOPIC_TAG_RE.search(body)
        img_match = IMAGE_PROMPT_RE.search(body)

        # Remove the tags (and everything after the first tag) to get clean post text
        cut_at = len(body)
        if kw_match:
            cut_at = min(cut_at, kw_match.start())
        if tag_match:
            cut_at = min(cut_at, tag_match.start())
        if img_match:
            cut_at = min(cut_at, img_match.start())
        clean_body = body[:cut_at].strip()

        # Title = first non-empty line of the clean post text
        first_line = ""
        for line in clean_body.split("\n"):
            if line.strip():
                first_line = line.strip()
                break

        raw_image_prompt = img_match.group(1).strip() if img_match else ""
        # Guard against a prompt that's empty, a placeholder, or accidentally
        # swallowed the next POST's content due to malformed input.
        if not raw_image_prompt or len(raw_image_prompt) < 8 or raw_image_prompt.lower().startswith("[scene"):
            raw_image_prompt = None

        raw_topic_tag = tag_match.group(1).strip() if tag_match else ""
        # Normalize: keep only the first "word" (tags are snake_case, single
        # token) in case the LLM appended extra text after it.
        raw_topic_tag = raw_topic_tag.split()[0].strip('.,;:"\'') if raw_topic_tag else None

        posts.append({
            "title": first_line,
            "image_prompt": raw_image_prompt,  # None triggers fallback later
            "topic_tag": raw_topic_tag,  # None if POST 1 (news) or unparseable
            "raw_body": clean_body,
        })

    # Guarantee exactly TOTAL_POSTS posts, padding with safe fallback content
    # if the LLM produced fewer than TOTAL_POSTS parseable posts.
    while len(posts) < TOTAL_POSTS:
        posts.append({
            "title": "Thread unavailable this run",
            "image_prompt": None,
            "topic_tag": None,
            "raw_body": "Thread unavailable this run.",
        })

    posts = posts[:TOTAL_POSTS]

    # Apply fallback image prompts + styling ONLY for the first
    # IMAGE_POST_COUNT posts (images are capped regardless of how many
    # total posts are generated). Posts beyond that get image_prompt=None,
    # which generate_hf_image() already treats as "skip, no image".
    for i, post in enumerate(posts):
        if i < IMAGE_POST_COUNT:
            prompt = post["image_prompt"] or FALLBACK_IMAGE_PROMPTS[i % len(FALLBACK_IMAGE_PROMPTS)]
            post["image_prompt"] = (
                f"{prompt}, "
                "realistic AFP Reuters wire photo style, "
                "natural or fluorescent lighting, desaturated colors, "
                "sharp focus, no neon, no sci-fi, no illustrations, "
                "no text, no watermark, no logos, "
                "Canon EOS R5, f/2.8, ISO 800, 4K press photo"
            )
        else:
            post["image_prompt"] = None

    return posts

# ─── CLEAN TEXT FOR EMAIL BODY ────────────────────────────────────────────────

KNOWN_CAMELCASE = [
    "WordPress", "JavaScript", "GitHub", "GitLab", "YouTube", "iPhone",
    "iPad", "macOS", "PowerShell", "TypeScript", "LinkedIn", "PayPal",
]


def fix_glued_words(text):
    """
    Safe fix for one specific glue pattern seen in production: a lowercase
    word run directly followed by a Capitalized word with no space (e.g.
    "guruIm" -> "guru Im", "confidenceIm" -> ...).

    Known brand/product CamelCase names (WordPress, GitHub, etc.) are
    protected via placeholder substitution so they are never incorrectly
    split (e.g. "WordPress" -> "Word Press", a real false positive caught
    in testing before this fix was added).

    Known limitation, accepted after testing: if a glue word is stuck
    DIRECTLY onto the start of a protected brand name (e.g. "newGitHub"),
    the missing space is not inserted, to avoid the complexity/risk of a
    more aggressive rule. Not observed in production so far.

    Does NOT catch all-lowercase glue (e.g. "itnow") -- that class of bug
    is addressed at the source via the generation prompt (explicit
    instruction to always use apostrophes in contractions), because a
    dictionary-based fix for that case produced false positives (e.g.
    "still" containing "ill") and was rejected after testing.
    """
    placeholders = {}
    working = text
    for i, word in enumerate(KNOWN_CAMELCASE):
        if word in working:
            token = f"__PROTECTED_{i}__"
            placeholders[token] = word
            working = working.replace(word, token)

    working = re.sub(r"([a-z]{2,})([A-Z][a-z])", r"\1 \2", working)

    for token, word in placeholders.items():
        working = working.replace(token, word)

    return working


def clean_threads_text(threads_content):
    """
    Regex-based cleanup — strips KEYWORDS/IMAGE_PROMPT even when glued to
    the previous sentence with no line break (the bug seen in production).
    """
    text = threads_content

    # Remove "KEYWORDS: ...", "TOPIC_TAG: ...", "IMAGE_PROMPT: ..." up to the
    # next tag/POST marker or end of string (order-independent)
    text = re.sub(r"KEYWORDS:\s*.*?(?=TOPIC_TAG:|IMAGE_PROMPT:|POST\s+\d|\Z)", "", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"TOPIC_TAG:\s*.*?(?=KEYWORDS:|IMAGE_PROMPT:|POST\s+\d|\Z)", "", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"IMAGE_PROMPT:\s*.*?(?=POST\s+\d|\Z)", "", text, flags=re.IGNORECASE | re.DOTALL)

    # Ensure each "POST N" marker starts on its own line with a blank line
    # before it, even if the LLM glued the previous post's last sentence
    # directly onto "POST N" with no line break.
    text = re.sub(r"(?<!\n)(?<!^)(POST\s+\d)", r"\n\n\1", text, flags=re.IGNORECASE)

    # Collapse leftover blank lines (3+ newlines -> 2)
    text = re.sub(r"\n{3,}", "\n\n", text)

    text = fix_glued_words(text)

    return text.strip()

# ─── GENERATE IMAGE VIA HF ────────────────────────────────────────────────────

def generate_hf_image(prompt):
    if not HF_TOKEN:
        print("HF_TOKEN missing")
        return None
    if not prompt:
        print("Empty image prompt — skipping (should not happen, fallback should have filled it)")
        return None

    endpoints = [
        "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell",
        "https://api-inference.huggingface.co/models/black-forest-labs/FLUX.1-schnell",
        "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-2-1",
    ]
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}

    for endpoint in endpoints:
        for attempt in range(2):
            try:
                print(f"Generating (attempt {attempt+1}): {prompt[:70]}...")
                r = requests.post(endpoint, headers=headers, json={"inputs": prompt}, timeout=120)

                if r.status_code == 200 and len(r.content) > 1000:
                    print(f"Image OK from {endpoint.split('/')[2]}")
                    return r.content
                elif r.status_code == 503:
                    print(f"Model loading, waiting 20s...")
                    time.sleep(20)
                else:
                    print(f"HF error {r.status_code}: {r.text[:80]}")
                    break
            except Exception as e:
                print(f"Image error: {e}")
                if attempt == 0:
                    time.sleep(5)

    print("All endpoints failed")
    return None

# ─── ADD OVERLAY (Petit Journal style) ───────────────────────────────────────

def add_overlay(image_bytes, title_text):
    try:
        from PIL import Image, ImageDraw, ImageFont
        import textwrap

        img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        w, h = img.size

        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw_ov = ImageDraw.Draw(overlay)
        grad_height = h // 3
        for i in range(grad_height):
            alpha = int(210 * (i / grad_height))
            draw_ov.rectangle([(0, h - grad_height + i), (w, h - grad_height + i + 1)], fill=(0, 0, 0, alpha))
        img = Image.alpha_composite(img, overlay)

        draw = ImageDraw.Draw(img)

        font_size = int(h * 0.055)
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size=font_size)
        except:
            font = ImageFont.load_default()

        clean_title = title_text.replace("**", "").replace("*", "").strip()
        wrapped = textwrap.wrap(clean_title.upper(), width=26)
        y = h - (len(wrapped) * int(h * 0.072)) - int(h * 0.05)

        for i, line in enumerate(wrapped):
            words = line.split(" ", 1)
            x = int(w * 0.04)
            if i == 0:
                draw.text((x, y), words[0], font=font, fill=(255, 80, 0, 255))
                if len(words) > 1:
                    bbox = draw.textbbox((0, 0), words[0] + " ", font=font)
                    draw.text((x + bbox[2], y), words[1], font=font, fill=(255, 255, 255, 255))
            else:
                draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))
            y += int(h * 0.068)

        final = img.convert("RGB")
        buf = io.BytesIO()
        final.save(buf, format="PNG")
        return buf.getvalue()

    except Exception as e:
        print(f"Overlay error: {e}")
        return image_bytes

# ─── SEND EMAIL — single email only ──────────────────────────────────────────

def send_email(threads_content, images=None, subject="Threads Report"):
    clean_content = safe_encode(threads_content)

    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = GMAIL_USER
    msg["To"] = TO_EMAIL
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = email.utils.make_msgid()

    msg.attach(MIMEText(clean_content, "plain", "us-ascii"))

    attached = 0
    if images:
        for i, img_bytes in enumerate(images):
            if img_bytes:
                part = MIMEImage(img_bytes, name=f"image_{i+1}.png")
                part.add_header("Content-Disposition", "attachment", filename=f"image_{i+1}.png")
                msg.attach(part)
                attached += 1
                print(f"Attached image {i+1}")

    # Plain-text export attachment — ready to copy-paste directly onto
    # Threads without needing to re-copy from the email body.
    txt_part = MIMEBase("text", "plain")
    txt_part.set_payload(clean_content.encode("us-ascii", errors="replace"))
    encoders.encode_base64(txt_part)
    txt_part.add_header("Content-Disposition", "attachment", filename="threads_export.txt")
    msg.attach(txt_part)

    print(f"Sending email with {attached} image(s) + 1 text export...")

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
            server.ehlo()
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_USER, TO_EMAIL, msg.as_bytes())
        print("Email sent successfully.")
    except Exception as e:
        print(f"Email error: {e}")
        raise e


def send_failure_email(error_summary):
    """
    Best-effort short notification when the run fails partway through.
    Sanitized: only the exception type + a truncated message, NEVER a full
    traceback or raw request bodies (avoids any chance of leaking secrets
    that might appear in a lower-level error string). If sending this
    notification itself fails, that failure is logged and swallowed here —
    the CALLER is still responsible for exiting non-zero either way, so a
    failed run is never mistaken for a success.
    """
    if not GMAIL_USER or not GMAIL_APP_PASSWORD or not TO_EMAIL:
        print("Cannot send failure notification — Gmail/recipient config missing too.")
        return

    safe_summary = safe_encode(str(error_summary))[:500]

    msg = MIMEMultipart()
    msg["Subject"] = "Thread Bot FAILED"
    msg["From"] = GMAIL_USER
    msg["To"] = TO_EMAIL
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = email.utils.make_msgid()
    msg.attach(MIMEText(
        f"The thread-bot run failed partway through.\n\n"
        f"Error summary (truncated, sanitized):\n{safe_summary}\n\n"
        f"Check the GitHub Actions log for the full traceback.",
        "plain", "us-ascii",
    ))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
            server.ehlo()
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_USER, TO_EMAIL, msg.as_bytes())
        print("Failure notification email sent.")
    except Exception as e:
        print(f"Could not send failure notification either: {e}")

# ─── STATE PERSISTENCE (topic rotation + sent-post log) ──────────────────────
# Stored as a small JSON file committed back to the repo by the workflow
# (see .github/workflows/thread-bot.yml) using the built-in ephemeral
# GITHUB_TOKEN — not Patrick's personal PAT. Read/write are pure functions
# parameterized by path so they're testable without touching the real file.

def load_state(path=STATE_FILE_PATH):
    """
    Returns {"recent_relatable_topic_tags": [...], "recent_post_titles": [...]}.
    Missing file, empty file, or corrupt JSON all fall back to empty state —
    never crash the run just because history tracking has a hiccup.
    """
    default = {"recent_relatable_topic_tags": [], "recent_post_titles": []}
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return default
        data.setdefault("recent_relatable_topic_tags", [])
        data.setdefault("recent_post_titles", [])
        return data
    except (json.JSONDecodeError, OSError) as e:
        print(f"State file unreadable ({e}), starting fresh.")
        return default


def save_state(state, path=STATE_FILE_PATH):
    """
    Writes state back to disk, truncating each list to its max length so
    the file doesn't grow unbounded over months of daily runs. Creates the
    parent directory if needed. Failure here is non-fatal — logged, not
    raised, since losing rotation history is annoying, not critical.
    """
    state["recent_relatable_topic_tags"] = state["recent_relatable_topic_tags"][-MAX_HISTORY_TOPICS:]
    state["recent_post_titles"] = state["recent_post_titles"][-MAX_HISTORY_TITLES:]
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        return True
    except OSError as e:
        print(f"Could not save state file: {e}")
        return False


def update_state_with_run(state, posts_data):
    """
    Given the final chosen posts_data (list of post dicts), returns an
    updated state dict with new topic tags + titles appended. Pure function
    (doesn't write to disk) so it's testable in isolation.
    """
    new_tags = [p["topic_tag"] for p in posts_data if p.get("topic_tag")]
    new_titles = [p["title"] for p in posts_data if p.get("title")]

    state["recent_relatable_topic_tags"] = state["recent_relatable_topic_tags"] + new_tags
    state["recent_post_titles"] = state["recent_post_titles"] + new_titles
    return state


# ─── QUALITY SCORING + REGENERATION ───────────────────────────────────────────

SCORE_RE = re.compile(r"POST\s+(\d+)\s+SCORE:\s*(\d+(?:\.\d+)?)", re.IGNORECASE)


def score_posts_quality(threads_content):
    """
    Asks the LLM to rate each post 1-10 on how scroll-stopping/non-generic it
    is. Returns (average_score, per_post_scores_dict). Returns (None, {}) on
    any failure (network, unparseable response) — caller must treat None as
    "couldn't score, proceed anyway" rather than crash the whole run over a
    scoring hiccup.
    """
    prompt = f"""Rate each of the following posts from 1 to 10 on how likely they are to stop someone from scrolling — punchy, specific, non-generic, no corporate tone, no cliche.

Output ONLY in this exact format, one line per post, nothing else:
POST 1 SCORE: <number>
POST 2 SCORE: <number>
(one line per post found below)

Posts to rate:
{threads_content}
"""
    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/sudomarc/thread-bot",
                "X-Title": "Thread Bot Scorer",
            },
            json={
                "model": "deepseek/deepseek-chat-v3-0324:free",
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30,
        )
        data = response.json()
        if "choices" not in data:
            print(f"Scoring call failed: {data.get('error', {}).get('message', 'unknown')}")
            return None, {}
        raw = data["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"Scoring network error: {e}")
        return None, {}

    matches = SCORE_RE.findall(raw)
    if not matches:
        print("Scoring response unparseable, skipping quality gate for this attempt.")
        return None, {}

    scores = {int(post_num): float(score) for post_num, score in matches}
    avg = sum(scores.values()) / len(scores)
    return avg, scores


def generate_threads_with_quality_gate(articles_text, exclude_topic_tags):
    """
    Generates posts, scores them, and regenerates (up to
    MAX_GENERATION_ATTEMPTS total) if the average score is below
    QUALITY_SCORE_THRESHOLD. Keeps the best-scoring attempt seen even if
    none clear the threshold, so a run never comes back empty just because
    quality scoring was pessimistic. If scoring itself fails (returns None),
    the attempt is accepted as-is rather than blocked.
    """
    best_content = None
    best_score = -1.0

    for attempt in range(1, MAX_GENERATION_ATTEMPTS + 1):
        print(f"Generation attempt {attempt}/{MAX_GENERATION_ATTEMPTS}...")
        content = generate_threads(articles_text, exclude_topic_tags=exclude_topic_tags)
        if not content:
            continue

        avg, per_post = score_posts_quality(content)
        if avg is None:
            print("Could not score this attempt — accepting it as-is.")
            return content
        print(f"Attempt {attempt} average quality score: {avg:.1f}/10 ({per_post})")

        if avg > best_score:
            best_score = avg
            best_content = content

        if avg >= QUALITY_SCORE_THRESHOLD:
            print(f"Threshold {QUALITY_SCORE_THRESHOLD} met — keeping this attempt.")
            return content

    print(f"No attempt cleared the quality threshold; keeping best attempt (score {best_score:.1f}).")
    return best_content


if __name__ == "__main__":
    import traceback

    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        print("Error: Missing Gmail credentials.")
        exit(1)

    if not TO_EMAIL:
        print("Error: Missing RECIPIENT_EMAIL secret.")
        exit(1)

    try:
        state = load_state()
        exclude_tags = set(state.get("recent_relatable_topic_tags", []))
        print(f"Excluding {len(exclude_tags)} recently-used relatable topics from this run.")

        articles = fetch_articles()
        if not articles:
            print("No articles fetched (all filtered out as too vague).")
            exit(0)

        print(f"Fetched {len(articles.splitlines())} unique, concrete articles")

        threads = generate_threads_with_quality_gate(articles, exclude_topic_tags=exclude_tags)
        if not threads:
            print("Generation failure (all attempts returned nothing).")
            exit(1)

        print("--- RAW LLM OUTPUT ---")
        print(threads[:500])
        print("---")

        final_content = clean_threads_text(threads)
        posts_data = extract_posts_data(threads)
        print(f"Extracted {len(posts_data)} posts with titles+prompts")

        generated_images = []
        for i, post in enumerate(posts_data):
            print(f"\n[POST {i+1}] Title: {post['title'][:60]}")
            if post["image_prompt"] is None:
                print(f"[POST {i+1}] No image for this post (beyond IMAGE_POST_COUNT={IMAGE_POST_COUNT}) — skipping HF call")
                generated_images.append(None)
                continue
            raw_img = generate_hf_image(post["image_prompt"])
            if raw_img:
                styled_img = add_overlay(raw_img, post["title"])
                generated_images.append(styled_img)
            else:
                generated_images.append(None)

        send_email(final_content, images=generated_images)

        # Only record topics/titles as "used" AFTER a successful send — if
        # the email never went out, Patrick never saw them, so they
        # shouldn't be blocked from being picked again next run.
        state = update_state_with_run(state, posts_data)
        save_state(state)
        print("State updated and saved.")

    except Exception as e:
        print("--- RUN FAILED ---")
        traceback.print_exc()
        send_failure_email(f"{type(e).__name__}: {e}")
        exit(1)
