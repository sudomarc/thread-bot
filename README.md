# Thread Bot

Automated cybersecurity/tech content bot — generates posts via LLM, scores them for quality, sends them by email with AI-generated images. Runs on GitHub Actions.

**Current version: [v1.0.0](https://github.com/sudomarc/thread-bot/releases/tag/v1.0.0)**

---

## What it does

Each run generates **5 posts** (1 hard-news + 4 relatable/meme-style infosec), scores them for quality, and sends them to your inbox with:
- 3 AI-generated press-photo style images (FLUX.1-schnell)
- A plain `.txt` export ready to copy-paste directly onto Threads
- Topic rotation to avoid repeating the same angle two runs in a row
- A failure alert email if anything breaks

---

## Setup

### 1. Create the repo
- New repo on GitHub (public or private)
- Upload `main.py` + `.github/workflows/thread-bot.yml`

### 2. Add secrets
Settings → Secrets and variables → Actions → **Secrets** tab → New repository secret

| Secret | Where to get it |
|---|---|
| `NEWS_API_KEY` | [newsapi.org](https://newsapi.org) |
| `OPENROUTER_API_KEY` | [openrouter.ai](https://openrouter.ai) |
| `GMAIL_USER` | Your Gmail sending address |
| `GMAIL_APP_PASSWORD` | Gmail → Security → App Passwords (16 chars) |
| `HF_TOKEN` | [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) |
| `RECIPIENT_EMAIL` | Address that receives the posts |

> No personal info ever goes in the code — everything flows through these secrets.

### 3. (Optional) Configure post/image counts
Settings → Secrets and variables → Actions → **Variables** tab

| Variable | Default | Range | Effect |
|---|---|---|---|
| `TOTAL_POSTS` | `5` | 1–8 | Total posts per run (1 news + rest relatable) |
| `IMAGE_POST_COUNT` | `3` | 0–TOTAL_POSTS | How many posts get an AI image |

Leave unset to use defaults.

### 4. Enable GitHub Actions
Actions tab → Enable

### 5. Run manually to test
Actions → Thread Bot Daily Runner → Run workflow

### 6. Check your inbox
Email with posts + images + `.txt` export = everything works. The bot then runs automatically every day at 08:00 UTC.

---

## How it works

```
fetch news → generate 5 posts → score quality → regenerate if needed
     → generate images → send email → commit topic history
```

1. **Fetch** — pulls recent cybersecurity/tech articles from NewsAPI, filters for concrete facts (CVEs, breaches, named companies).
2. **Generate** — calls OpenRouter LLM with a structured prompt: 1 news post + 4 relatable infosec posts on different topics.
3. **Score** — second LLM call rates each post 1-10 on punch/originality. If average < 6.5, regenerates (up to 3 attempts, keeps the best).
4. **Images** — generates 3 press-photo style images via FLUX.1-schnell (Hugging Face), adds a BFM/Petit Journal style text overlay.
5. **Send** — one email: posts in body + images attached + plain `.txt` export.
6. **Persist** — commits `state/history.json` back to the repo (topic rotation tracking). Uses `[skip ci]` to avoid re-triggering the workflow.

---

## What you receive per run

| Attachment | Content |
|---|---|
| Email body | 5 posts, clean text, no metadata |
| `image_1.png` | Image for POST 1 (news) |
| `image_2.png` | Image for POST 2 |
| `image_3.png` | Image for POST 3 |
| `threads_export.txt` | All 5 posts, copy-paste ready |

---

## Failure handling

- If the run fails at any point → you receive a short "Thread Bot FAILED" email with the error summary + a pointer to the GitHub Actions log.
- If the news API key is invalid → raises a real error (doesn't silently exit 0 like a quiet news day would).
- If the LLM skips an image prompt → fallback prompt used, 3 images always generated.

---

## Files

```
main.py                          — bot logic
.github/workflows/thread-bot.yml — GitHub Actions workflow
state/history.json               — auto-generated, topic rotation state (committed by bot)
.gitignore
README.md
```

---

## Privacy

- No names, emails, or personal info anywhere in the code.
- All sensitive values live in GitHub Secrets only.
- `state/history.json` contains only topic tag strings (e.g. `"untested_backups"`) — no personal data.
