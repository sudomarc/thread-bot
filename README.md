# Thread Bot

Automated social-content bot for current **cybersecurity, technology, AI, gaming, and internet news**. It generates source-grounded posts, optionally creates images, emails the report when Gmail works, and always keeps a GitHub Actions artifact.

## What the current runner does

- Queries **cybersecurity + technology/AI + gaming** on every run instead of picking one niche for the whole run.
- Targets current stories such as **GTA 6, Rockstar, Take-Two, CyberLeek**, major AI releases, chips, breaches and vulnerabilities.
- Uses recent-news filtering (default 72 hours) and remembers article URLs/titles to reduce repetition.
- Requires the LLM to cite the supplied news record for current-news posts; malformed or unsupported output is rejected and regenerated.
- Uses OpenRouter's `openrouter/free` router for generation and scoring, with retries for transient API failures.
- Treats Gmail and Hugging Face as **non-fatal delivery/enrichment channels**: a mail/image outage cannot destroy an otherwise valid content run.
- Preserves Unicode correctly in reports and email attachments.
- Writes `state/latest_threads.txt`, `state/latest_sources.txt`, and `state/history.json`.
- Uploads those files as a GitHub Actions artifact for 14 days.
- Uses an atomic state-file write and a resilient Git rebase/push loop for history persistence.
- Runs unit tests before the bot and blocks overlapping workflow runs with concurrency control.

## Required secrets

Settings → Secrets and variables → Actions → **Secrets**

| Secret | Purpose |
|---|---|
| `NEWS_API_KEY` | Current news retrieval |
| `OPENROUTER_API_KEY` | LLM generation/scoring |

Optional delivery/enrichment secrets:

| Secret | Purpose |
|---|---|
| `GMAIL_USER` | Gmail sender |
| `GMAIL_APP_PASSWORD` | Gmail app password |
| `RECIPIENT_EMAIL` | Destination email |
| `HF_TOKEN` | Optional image generation |

A working Gmail or Hugging Face configuration is **not** required for the content workflow to succeed.

## Optional Actions variables

Settings → Secrets and variables → Actions → **Variables**

| Variable | Default | Effect |
|---|---:|---|
| `TOTAL_POSTS` | `5` | Number of posts per run (1–8) |
| `IMAGE_POST_COUNT` | `0` | Optional AI images (0–TOTAL_POSTS) |

## Workflow

```text
NewsAPI: cyber + tech/AI + gaming
            ↓
source-grounded LLM generation
            ↓
strict parser/validation
            ↓
quality scoring + regeneration
            ↓
optional images
            ↓
latest_threads + latest_sources
      ┌─────┴─────────┐
    Gmail          Artifact
      └─────┬─────────┘
            ↓
       history state
```

## Reliability design

The previous runner had several independent failure modes: revoked Gmail app passwords, retired image models, Unicode/ASCII email encoding, malformed LLM output being accepted, excessive API calls, duplicate bot implementations, and non-fast-forward state pushes.

The maintained implementation is now **`bot.py`**. `main.py` is only a compatibility entrypoint importing `bot.main`.

The workflow also runs `python -m unittest discover -s tests -v` before generation, uses current Node 24-based GitHub Actions runners, and retries state persistence instead of failing the entire content run on a race.

## Safety around leaks

Gaming/news posts can discuss reported leaks and legal actions around them. The bot does **not** distribute leaked files, stolen credentials, piracy links, or instructions for accessing stolen material.
