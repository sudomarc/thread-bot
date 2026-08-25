# Thread Bot

Automated social-content bot for current **cybersecurity, technology, AI, gaming, and internet news**. It generates posts with an LLM, optionally creates images, emails the report when Gmail works, and always keeps a copy in GitHub Actions artifacts.

## What changed in the resilient runner

The workflow now uses `bot.py` instead of the legacy `main.py` runner.

- **Mixed topics per run:** cybersecurity + tech/AI + gaming are queried every run instead of selecting one niche for the whole run.
- **Current-news focus:** queries include live technology/gaming stories such as GTA 6, Rockstar/Take-Two, CyberLeek, AI companies, chips, breaches, vulnerabilities and major tech announcements.
- **Source-grounded writing:** the LLM receives article titles, descriptions, dates, publishers and URLs; it is instructed not to invent facts or provide access to leaked/stolen material.
- **Gmail is non-fatal:** an SMTP `535 BadCredentials` error no longer turns a successfully generated report into a failed GitHub Action.
- **Images are optional:** Hugging Face `410`, provider changes, DNS failures and model outages are logged and skipped rather than killing the run. `IMAGE_POST_COUNT` defaults to `0`.
- **Report artifact:** every successful content run writes `state/latest_threads.txt`, which GitHub Actions uploads as an artifact for 14 days.
- **State rotation:** `state/history.json` tracks recent titles, topics and article URLs to reduce repetition.
- **Concurrency guard:** overlapping runs on `main` are prevented.

## Required secrets

Settings → Secrets and variables → Actions → Secrets

| Secret | Purpose |
|---|---|
| `NEWS_API_KEY` | Current news retrieval |
| `OPENROUTER_API_KEY` | LLM generation/scoring |
| `GMAIL_USER` | Optional Gmail sender |
| `GMAIL_APP_PASSWORD` | Optional Gmail app password |
| `RECIPIENT_EMAIL` | Optional destination email |
| `HF_TOKEN` | Optional image generation |

A working Gmail configuration is no longer required for the GitHub Action to succeed.

## Optional Actions variables

Settings → Secrets and variables → Actions → Variables

| Variable | Default | Effect |
|---|---:|---|
| `TOTAL_POSTS` | `5` | Number of posts per run (1–8) |
| `IMAGE_POST_COUNT` | `0` | Number of optional AI images (0–TOTAL_POSTS) |

## Workflow

```text
NewsAPI (cyber + tech/AI + gaming)
        ↓
LLM generates mixed current-news + relatable posts
        ↓
Quality scoring / regeneration
        ↓
Optional images
        ↓
state/latest_threads.txt
        ├── Gmail delivery (optional)
        └── GitHub Actions artifact (always)
        ↓
state/history.json rotation
```

## Current-news examples

The gaming query pool explicitly targets stories such as **GTA 6**, Rockstar, Take-Two and **CyberLeek**, alongside PlayStation, Xbox, Nintendo, Steam and other gaming news. The bot treats leaks as reported/alleged events and does not distribute leaked files or access instructions.

## Legacy file

`main.py` is kept for history/rollback. The scheduled GitHub Actions workflow runs `bot.py`.
