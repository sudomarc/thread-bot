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

TOPICS = ["cybersecurity", "artificial intelligence Claude Anthropic", "tech news"]

HF_API_URL = "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell"

# ─── FETCH NEWS ───────────────────────────────────────────────────────────────
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
                    title = safe_encode(a.get('title', ''))
                    desc  = safe_encode(a.get('description', ''))
                    articles.append(f"- {title}: {desc}")
        except Exception as e:
            print(f"Error fetching news for {topic}: {e}")
    return "\n".join(articles[:9])

# ─── IMAGE LINKS (removed) ───────────────────────────────────────────────────

# ─── GENERATE THREADS ─────────────────────────────────────────────────────────
def generate_threads(articles_text):
    prompt = f"""You are a viral tech/cybersecurity content creator.
From these news articles, generate exactly 3 Threads posts in ENGLISH.
Each post = 4 to 5 lines MAX. No more.

STRICT RULES:
1. OUTPUT ONLY THE POSTS. NO intro, NO conclusion, NO metadata.
2. Each post starts with a SHOCKING HOOK (a bold stat or provocative claim).
3. High contrast writing: short punchy sentences. No corporate tone.
4. End each post with one implicit call-to-action line.
5. After each post, on a new line write: KEYWORDS: [2-3 topic keywords in English, comma separated]
6. After KEYWORDS, write: IMAGE_PROMPT: [a vivid, cinematic scene description in English for image generation, NO real person names, fictional characters only]

Format:
POST 1
[hook line]
[line 2]
[line 3]
[line 4]
[CTA line]
KEYWORDS: keyword1, keyword2
IMAGE_PROMPT: a dramatic scene of ...

POST 2
...

News:
{articles_text}
"""

    models_to_try = [
        "openrouter/free",
        "deepseek/deepseek-chat-v3-0324:free",
        "meta-llama/llama-3.3-70b-instruct:free",
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
                print(f"Success with {model}!")
                return safe_encode(data["choices"][0]["message"]["content"])
            print(f"Failed with {model}: {data.get('error', {}).get('message', 'Unknown')}")
            time.sleep(3)
        except Exception as e:
            print(f"Network error with {model}: {e}")
            time.sleep(3)
    return None

# ─── EXTRACT IMAGE PROMPTS ────────────────────────────────────────────────────
def extract_image_prompts(threads_content):
    prompts = []
    for line in threads_content.split("\n"):
        if line.strip().startswith("IMAGE_PROMPT:"):
            prompt = line.strip().replace("IMAGE_PROMPT:", "").strip()
            # Style injection: Petit Journal / media card aesthetic
            styled = (
                f"{prompt}, "
                "dark dramatic background, bold graphic design, "
                "news media style, high contrast, cinematic lighting, "
                "photorealistic, 4k sharp"
            )
            prompts.append(styled)
    return prompts[:3]  # max 3

# ─── GENERATE IMAGE VIA HF ────────────────────────────────────────────────────
def generate_hf_image(prompt):
    if not HF_TOKEN:
        print("HF_TOKEN missing, skipping image generation")
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
                print(f"Generating image (attempt {attempt+1}): {prompt[:60]}...")
                r = requests.post(endpoint, headers=headers, json={"inputs": prompt}, timeout=120)
                if r.status_code == 200 and len(r.content) > 1000:
                    print(f"Image generated OK from {endpoint.split('/')[2]}")
                    return r.content
                elif r.status_code == 503:
                    print(f"Model loading ({r.status_code}), waiting 20s...")
                    time.sleep(20)
                else:
                    print(f"HF error {r.status_code}: {r.text[:80]}")
                    break
            except Exception as e:
                print(f"Image generation error: {e}")
                if attempt == 0:
                    time.sleep(5)
    print("All image endpoints failed")
    return None

# ─── ADD OVERLAY (Petit Journal style) ───────────────────────────────────────
def add_overlay(image_bytes, title_text):
    """Add bold text overlay in Petit Journal style using Pillow."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        import textwrap

        img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        w, h = img.size

        # Dark gradient overlay at bottom
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw_ov = ImageDraw.Draw(overlay)
        for i in range(h // 3):
            alpha = int(200 * (i / (h // 3)))
            draw_ov.rectangle([(0, h - h//3 + i), (w, h - h//3 + i + 1)], fill=(0, 0, 0, alpha))
        img = Image.alpha_composite(img, overlay)

        draw = ImageDraw.Draw(img)

        # Font — fallback to default if no TTF available
        try:
            font_big = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size=int(h * 0.055))
        except:
            font_big = ImageFont.load_default()

        # Wrap title
        wrapped = textwrap.wrap(title_text.upper(), width=28)

        # Draw text bottom-left with orange accent on first word
        y = h - (len(wrapped) * int(h * 0.07)) - int(h * 0.04)
        for i, line in enumerate(wrapped):
            # First line: first word in orange, rest white
            if i == 0:
                words = line.split(" ", 1)
                draw.text((int(w * 0.04), y), words[0], font=font_big, fill=(255, 90, 0, 255))
                if len(words) > 1:
                    bbox = draw.textbbox((0, 0), words[0] + " ", font=font_big)
                    draw.text((int(w * 0.04) + bbox[2], y), words[1], font=font_big, fill=(255, 255, 255, 255))
            else:
                draw.text((int(w * 0.04), y), line, font=font_big, fill=(255, 255, 255, 255))
            y += int(h * 0.065)

        # Convert back to RGB PNG
        final = img.convert("RGB")
        buf = io.BytesIO()
        final.save(buf, format="PNG")
        return buf.getvalue()

    except Exception as e:
        print(f"Overlay error: {e} — sending raw image")
        return image_bytes

# ─── CLEAN TEXT (strip IMAGE_PROMPT / KEYWORDS from email body) ───────────────
def clean_threads_text(threads_content):
    """Keep only POST headers and post body lines. Strip metadata."""
    lines = threads_content.split("\n")
    output = []
    skip_next = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("KEYWORDS:") or stripped.startswith("IMAGE_PROMPT:") or stripped == "=" * 50:
            continue
        output.append(line)
    # Remove trailing blank lines between posts
    return "\n".join(output).strip()

# ─── SEND EMAIL ───────────────────────────────────────────────────────────────
def send_email(threads_content, images=None):
    clean_content = safe_encode(threads_content)

    msg = MIMEMultipart()
    msg["Subject"] = "Threads Report"
    msg["From"]    = GMAIL_USER
    msg["To"]      = TO_EMAIL
    msg["Date"]    = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = email.utils.make_msgid()

    msg.attach(MIMEText(clean_content, "plain", "us-ascii"))

    if images:
        for i, img_bytes in enumerate(images):
            if img_bytes:
                part = MIMEImage(img_bytes, name=f"image_{i+1}.png")
                part.add_header("Content-Disposition", "attachment", filename=f"image_{i+1}.png")
                msg.attach(part)
                print(f"Attached image {i+1}")

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
            server.ehlo()
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_USER, TO_EMAIL, msg.as_bytes())
        print("Email sent successfully.")
    except Exception as e:
        print(f"Critical email error: {e}")
        raise e

# ─── MAIN ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        print("Error: Missing Gmail credentials.")
        exit(1)

    articles = fetch_articles()
    if not articles:
        print("No articles fetched.")
        exit(0)

    threads = generate_threads(articles)
    if not threads:
        print("Total generation failure.")
        exit(1)

    final_content = clean_threads_text(threads)

    # Generate images
    image_prompts = extract_image_prompts(threads)
    generated_images = []

    for i, prompt in enumerate(image_prompts):
        # Extract post title for overlay (first non-empty line after POST N)
        post_lines = [l.strip() for l in threads.split("\n") if l.strip()]
        title = prompt.split(",")[0]  # fallback
        try:
            post_markers = [j for j, l in enumerate(post_lines) if l.startswith(f"POST {i+1}")]
            if post_markers:
                title = post_lines[post_markers[0] + 1]
        except:
            pass

        raw_img = generate_hf_image(prompt)
        if raw_img:
            styled_img = add_overlay(raw_img, title)
            generated_images.append(styled_img)
        else:
            generated_images.append(None)

    send_email(final_content, images=generated_images)


