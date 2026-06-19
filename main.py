import os
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
NEWS_API_KEY        = os.environ.get("NEWS_API_KEY", "")
OPENROUTER_API_KEY  = os.environ.get("OPENROUTER_API_KEY", "")
GMAIL_USER          = safe_encode(os.environ.get("GMAIL_USER", ""))
GMAIL_APP_PASSWORD  = safe_encode(os.environ.get("GMAIL_APP_PASSWORD", ""))
HF_TOKEN            = os.environ.get("HF_TOKEN", "")
TO_EMAIL            = "elom.karl.patrick@gmail.com"

# TARGETED QUERIES — concrete facts only
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

HF_API_URL = "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell"

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
                    desc  = safe_encode(a.get('description', '') or '')
                    # Deduplicate by title
                    title_key = title.lower()[:60]
                    if title_key in seen_titles or not title:
                        continue
                    
                    # FILTERING RULE: Extract a concrete fact (name, CVE, $, date)
                    # If none found, skip this article
                    if not has_concrete_fact(title, desc):
                        print(f"Skipping vague article: {title[:50]}")
                        continue
                    
                    seen_titles.add(title_key)
                    articles.append(f"- {title}: {desc}")
        except Exception as e:
            print(f"Error fetching news for {topic}: {e}")
    # Return max 9 unique articles
    return "\n".join(articles[:9])

def has_concrete_fact(title, desc):
    """
    Check if article contains at least ONE concrete fact:
    - Company name (Google, Microsoft, Apple, Amazon, etc.)
    - CVE number (CVE-XXXX-XXXXX)
    - Money amount ($XXX, €, million)
    - Specific date (2024, June, etc.)
    - Action verb (sued, hacked, fined, banned, breached)
    """
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
    
    # Check for company names
    if any(company in combined_text for company in companies):
        return True
    
    # Check for CVE
    if "cve-20" in combined_text:
        return True
    
    # Check for money amounts
    if "$" in combined_text or " million " in combined_text or " billion " in combined_text:
        return True
    
    # Check for action verbs
    if any(verb in combined_text for verb in action_verbs):
        return True
    
    return False

# ─── GENERATE THREADS ─────────────────────────────────────────────────────────
def generate_threads(articles_text):
    prompt = f"""You write like a real person on Twitter/Threads who's obsessed with tech and cybersecurity — NOT a corporate blog, NOT a SaaS marketing account.

From these news articles, generate exactly 3 DIFFERENT Threads posts in ENGLISH.
Each post must cover a DIFFERENT article/topic. No repetition between posts.

HOW REAL VIRAL TECH/CYBERSEC POSTS ACTUALLY SOUND:

Example 1:
Oracle PeopleSoft has a zero-day.

CVE-2026-35273.

It's being exploited RIGHT NOW.

If you're running PeopleSoft and haven't patched —
you're not "at risk."
You're already owned.

Example 2:
A bug report took down a company's entire codebase.

Not malware. Not phishing.

Just text. In a GitHub issue.

The AI assistant read it, executed it, and leaked the secrets straight to the attacker.

This is the new attack surface. And most teams aren't even looking at it.

Example 3:
Canada wants to ban teens from social media.

Parents: relieved.
Platforms: panicking.
Privacy lawyers: billing hours.

Here's what nobody's talking about: enforcement means age verification. Age verification means ID uploads. ID uploads mean a new database to breach.

WHAT MAKES THESE WORK:
- Short fragments. One fact or idea per line. Heavy use of line breaks for rhythm/suspense.
- NO corporate vocabulary: never say "consequences," "implications," "protect your enterprise," "threat landscape," "robust," "leverage."
- Specific > vague. Name the CVE, the company, the number, the mechanism. If the article gives a number ($ amount, # of users, CVE ID), USE IT in the post, don't just gesture at it.
- The punchline lands HARD and concrete — not a vague warning, not "stay safe out there."
- Sometimes end on an escalation, a blunt fact, or a sharp rhetorical question — never end on generic advice like "patch your systems" alone without a sting.
- Write like you're texting a smart friend who works in tech, not writing a corporate alert.
- Contractions are fine. Sentence fragments are GOOD. Don't write full grammatically "clean" sentences throughout — that's the corporate tell.

STRICT FORMAT — follow EXACTLY:

POST 1
[line 1 — the concrete fact, short]
[line 2]
[line 3]
[line 4 or 5 — punchline/sting, concrete, not generic advice]
KEYWORDS: keyword1, keyword2
IMAGE_PROMPT: [scene description — see style below]

POST 2
[different topic from POST 1]
[line 2]
[line 3]
[line 4 or 5]
KEYWORDS: keyword1, keyword2
IMAGE_PROMPT: [scene description]

POST 3
[different topic from POST 1 and POST 2]
[line 2]
[line 3]
[line 4 or 5]
KEYWORDS: keyword1, keyword2
IMAGE_PROMPT: [scene description]

IMAGE_PROMPT STYLE GUIDE — French TV news / BFM style:
- Realistic press photo style, NOT sci-fi, NOT cyberpunk, NOT illustration
- Scene: real-world location — government building exterior, street protest, corporate office, courtroom, parliament, stock exchange floor, hospital corridor
- Lighting: natural daylight OR harsh indoor fluorescent OR overcast sky — realistic, not dramatic neon
- Subject: anonymous suited figures, crowds, symbolic objects (handcuffs, documents, screens, flags), empty institutions — NO real faces, NO named people
- Mood: serious, institutional, cold, urgent — like a AFP/Reuters wire photo
- Color palette: desaturated, slightly cold, realistic — NOT oversaturated, NOT neon
- Technical: sharp focus, shallow depth of field, realistic proportions, 4K, no text, no watermark, no logos
- Examples by topic:
  * Tech/AI: "modern tech company open office, empty chairs, screens with code, cold fluorescent light, realistic AFP wire photo, 4K, no people, no text"
  * Cybersecurity: "anonymous person in dark suit typing on laptop in dimly lit office, face out of frame, documents on desk, realistic press photo, 4K"
  * Politics/Gov: "empty government chamber with rows of seats, national flags, daylight through tall windows, Reuters wire photo style, 4K, no text"
  * Finance: "stock exchange trading floor, anonymous traders in suits, green and red screens, harsh overhead light, realistic press photo"
  * Crime/Legal: "courthouse exterior stone steps, anonymous figures in suits carrying briefcases, overcast sky, AFP photo style, 4K"

RULES:
- OUTPUT ONLY THE 3 POSTS. No intro, no conclusion, no explanation.
- Each post = 4 to 6 short lines + KEYWORDS + IMAGE_PROMPT. Vary the rhythm — don't make every post the same length.
- NO corporate tone, NO marketing language, NO generic safety advice as the closer.
- Each post on a DIFFERENT topic from the news below.
- If you catch yourself writing "stay safe," "protect your systems," "consider the implications," or "raises questions about" — DELETE it and write a sharper, more specific line instead.

News:
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

# ─── EXTRACT DATA FROM THREADS ────────────────────────────────────────────────
def extract_posts_data(threads_content):
    """
    Returns list of dicts: [{title, image_prompt}, ...]
    title = hook line (first content line after POST N)
    image_prompt = full styled prompt
    """
    posts = []
    lines = threads_content.split("\n")
    current_post = {}
    in_post = False
    hook_captured = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("POST ") and stripped[5:].strip().isdigit():
            if current_post:
                posts.append(current_post)
            current_post = {"title": "", "image_prompt": ""}
            in_post = True
            hook_captured = False
        elif in_post and not hook_captured and stripped and not stripped.startswith("KEYWORDS:") and not stripped.startswith("IMAGE_PROMPT:"):
            current_post["title"] = stripped
            hook_captured = True
        elif stripped.startswith("IMAGE_PROMPT:"):
            raw_prompt = stripped.replace("IMAGE_PROMPT:", "").strip()
            current_post["image_prompt"] = (
                f"{raw_prompt}, "
                "realistic AFP Reuters wire photo style, "
                "natural or fluorescent lighting, desaturated colors, "
                "sharp focus, no neon, no sci-fi, no illustrations, "
                "no text, no watermark, no logos, "
                "Canon EOS R5, f/2.8, ISO 800, 4K press photo"
            )

    if current_post:
        posts.append(current_post)

    return posts[:3]

# ─── CLEAN TEXT FOR EMAIL BODY ────────────────────────────────────────────────
def clean_threads_text(threads_content):
    lines = threads_content.split("\n")
    output = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("KEYWORDS:") or stripped.startswith("IMAGE_PROMPT:") or stripped == "=" * 50:
            continue
        output.append(line)
    return "\n".join(output).strip()

# ─── GENERATE IMAGE VIA HF ────────────────────────────────────────────────────
def generate_hf_image(prompt):
    if not HF_TOKEN:
        print("HF_TOKEN missing")
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

        # Dark gradient at bottom third
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw_ov = ImageDraw.Draw(overlay)
        grad_height = h // 3
        for i in range(grad_height):
            alpha = int(210 * (i / grad_height))
            draw_ov.rectangle([(0, h - grad_height + i), (w, h - grad_height + i + 1)], fill=(0, 0, 0, alpha))
        img = Image.alpha_composite(img, overlay)
        draw = ImageDraw.Draw(img)

        # Font
        font_size = int(h * 0.055)
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size=font_size)
        except:
            font = ImageFont.load_default()

        # Clean title — strip markdown bold markers
        clean_title = title_text.replace("**", "").replace("*", "").strip()
        wrapped = textwrap.wrap(clean_title.upper(), width=26)

        y = h - (len(wrapped) * int(h * 0.072)) - int(h * 0.05)
        for i, line in enumerate(wrapped):
            words = line.split(" ", 1)
            x = int(w * 0.04)
            if i == 0:
                # First word orange
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
    msg["From"]    = GMAIL_USER
    msg["To"]      = TO_EMAIL
    msg["Date"]    = email.utils.formatdate(localtime=True)
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
