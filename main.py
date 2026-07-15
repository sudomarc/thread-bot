import os
import re
import smtplib
import requests
import time
import email.utils
import io
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage

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
TO_EMAIL = "elom.karl.patrick@gmail.com"

TOPICS = [
    "CVE-2024",
    "data breach $1M",
    "Google sued",
    "Microsoft hacked",
    "Cloudflare vulnerability",
    "AWS zero-day",
    "ransomware attack",
    "AI security exploit",
    "phishing campaign",
    "supply chain attack"
]

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

def generate_threads(articles_text):
    prompt = f"""You write like a real person on Twitter/Threads who's obsessed with tech and cybersecurity — NOT a corporate blog, NOT a SaaS marketing account.

Generate exactly 3 DIFFERENT Threads posts in ENGLISH:
- POST 1 = a hard-news post based on ONE of the news articles below (pick the sharpest one).
- POST 2 = a RELATABLE / MEME-STYLE post about everyday life in cybersecurity/infosec. NOT based on the news.
- POST 3 = another RELATABLE / MEME-STYLE post, different angle/topic from POST 2. NOT based on the news.

POST 1 — NEWS STYLE (4 to 6 short lines, line breaks for rhythm):
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

POST 2 & POST 3 — RELATABLE/MEME STYLE — STRICT LENGTH LIMIT:
MAXIMUM 2 SHORT SENTENCES TOTAL. NOT 4-6 lines. ONE OR TWO SENTENCES ONLY.
Think tweet-length, not thread-length. A single punchy joke, not a mini-story.

Good length example (this is the target length, do not exceed it):
"Got a new cert. Still Google how to unplug a router."

Another good length example:
"Passed my own company's phishing test by accident. First time all year I've done anything right on the first try."

Pull from universal infosec/IT truths: imposter syndrome, untested backups, password reuse hypocrisy, failing your own company's phishing test, security budget vs marketing budget, dreading the word "audit", one-person IT team doing everything, compliance theater, users clicking things no matter the training, cert-flexing vs job reality. Pick 2 DIFFERENT ones for POST 2 and POST 3.

Style: self-aware, self-deprecating, sounds like a real person venting/joking. NO hashtags, no "thoughts?" bait, NO listicle format.

OUTPUT FORMAT — FOLLOW EXACTLY, EACH TAG ON ITS OWN LINE, NOTHING ELSE ON THAT LINE:

POST 1
[line 1]
[line 2]
[line 3]
[line 4 or 5 — punchline]
KEYWORDS: keyword1, keyword2
IMAGE_PROMPT: [scene description]

POST 2
[ONE OR TWO SENTENCES MAX]
KEYWORDS: keyword1, keyword2
IMAGE_PROMPT: [scene description]

POST 3
[ONE OR TWO SENTENCES MAX, different topic from POST 2]
KEYWORDS: keyword1, keyword2
IMAGE_PROMPT: [scene description]

CRITICAL FORMAT RULES:
- ALWAYS use proper apostrophes in contractions: "it's", "I'm", "you're", "don't", "can't" — NEVER write them without the apostrophe ("its", "Im", "youre", "dont"). Missing apostrophes cause words to visually run together and look broken.
- "KEYWORDS:" and "IMAGE_PROMPT:" MUST each start on their OWN new line. Never append them to the end of a content line. Never put them on the same line as the joke/punchline.
- Always leave a line break BEFORE "KEYWORDS:" and BEFORE "IMAGE_PROMPT:".
- Never skip IMAGE_PROMPT for any post, even short ones.

IMAGE_PROMPT STYLE GUIDE — French TV news / BFM style:
- Realistic press photo style, NOT sci-fi, NOT cyberpunk, NOT illustration
- POST 1: serious, institutional, cold, urgent — like AFP/Reuters wire photo. Real-world location (office, courtroom, government building, server room).
- POST 2/3: relatable everyday office/home realism, mundane/tired mood, still realistic press-photo style
- Anonymous figures only, NO real faces, NO named people
- Desaturated, realistic colors, NOT neon
- Sharp focus, shallow depth of field, 4K, no text, no watermark, no logos

RULES:
- OUTPUT ONLY THE 3 POSTS. No intro, no conclusion, no explanation.
- POST 1 = 4 to 6 lines. POST 2 and POST 3 = 1 to 2 sentences ONLY, this is a hard limit.
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
                    "HTTP-Referer": "https://github.com/Patrickk2/thread-bot",
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
KEYWORDS_RE = re.compile(r"KEYWORDS:\s*(.*?)(?=IMAGE_PROMPT:|POST\s+\d|\Z)", re.IGNORECASE | re.DOTALL)
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

        # Pull out KEYWORDS/IMAGE_PROMPT wherever they are (even glued to text)
        kw_match = KEYWORDS_RE.search(body)
        img_match = IMAGE_PROMPT_RE.search(body)

        # Remove the tags (and everything after the first tag) to get clean post text
        cut_at = len(body)
        if kw_match:
            cut_at = min(cut_at, kw_match.start())
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

        posts.append({
            "title": first_line,
            "image_prompt": raw_image_prompt,  # None triggers fallback later
            "raw_body": clean_body,
        })

    # Guarantee exactly 3 posts, padding with safe fallback content if the
    # LLM produced fewer than 3 parseable posts.
    while len(posts) < 3:
        idx = len(posts)
        posts.append({
            "title": "Thread unavailable this run",
            "image_prompt": None,
            "raw_body": "Thread unavailable this run.",
        })

    posts = posts[:3]

    # Apply fallback image prompts + styling for any post missing one
    for i, post in enumerate(posts):
        prompt = post["image_prompt"] or FALLBACK_IMAGE_PROMPTS[i % len(FALLBACK_IMAGE_PROMPTS)]
        post["image_prompt"] = (
            f"{prompt}, "
            "realistic AFP Reuters wire photo style, "
            "natural or fluorescent lighting, desaturated colors, "
            "sharp focus, no neon, no sci-fi, no illustrations, "
            "no text, no watermark, no logos, "
            "Canon EOS R5, f/2.8, ISO 800, 4K press photo"
        )

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

    # Remove "KEYWORDS: ..." up to the next tag/POST marker or end of string
    text = re.sub(r"KEYWORDS:\s*.*?(?=IMAGE_PROMPT:|POST\s+\d|\Z)", "", text, flags=re.IGNORECASE | re.DOTALL)
    # Remove "IMAGE_PROMPT: ..." up to the next POST marker or end of string
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

def send_email(threads_content, images=None):
    clean_content = safe_encode(threads_content)

    msg = MIMEMultipart()
    msg["Subject"] = "Threads Report"
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

    print(f"Sending email with {attached} image(s)...")

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
            server.ehlo()
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_USER, TO_EMAIL, msg.as_bytes())
        print("Email sent successfully.")
    except Exception as e:
        print(f"Email error: {e}")
        raise e

# ─── MAIN ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        print("Error: Missing Gmail credentials.")
        exit(1)

    articles = fetch_articles()
    if not articles:
        print("No articles fetched (all filtered out as too vague).")
        exit(0)

    print(f"Fetched {len(articles.splitlines())} unique, concrete articles")

    threads = generate_threads(articles)
    if not threads:
        print("Generation failure.")
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
        raw_img = generate_hf_image(post["image_prompt"])
        if raw_img:
            styled_img = add_overlay(raw_img, post["title"])
            generated_images.append(styled_img)
        else:
            generated_images.append(None)

    send_email(final_content, images=generated_images)
