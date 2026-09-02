# Thread Bot

Automated social-content bot for current **cybersecurity, technology, AI, gaming, and internet news**. It generates source-grounded posts, optionally creates images, emails the report when Gmail works, and keeps a GitHub Actions artifact.

## Current architecture

`NewsAPI → filtering/deduplication → OpenRouter generation → strict parsing/validation → optional LLM quality scoring → report/state → optional images/email`

The maintained implementation is `bot.py`. `main.py` remains a compatibility entrypoint.

### Reliability and consistency

- Searches cybersecurity, technology/AI, and gaming on every run.
- Restricts articles to a rolling 72-hour window and rejects future/invalid timestamps.
- Sends the NewsAPI key through `X-Api-Key` instead of the query string.
- Canonicalizes article URLs and removes common tracking parameters before deduplication.
- Remembers only **articles actually used by generated posts**, avoiding accidental starvation of future runs.
- Keeps `latest_sources.txt` aligned with the sources cited by the generated report.
- Requires sequential post numbering, valid source markers, unique source usage, valid topic tags, minimum current-news coverage, and gaming coverage when gaming sources are available.
- Rejects duplicate titles and exact repeats from recent history.
- Preserves Unicode and writes state atomically.
- Treats Gmail and image generation as non-fatal enrichment channels.
- Makes the optional LLM quality scorer opt-in so a normal run does not double its model traffic.

## Required secrets

Settings → Secrets and variables → Actions → **Secrets**

| Secret | Purpose |
|---|---|
| `NEWS_API_KEY` | Current news retrieval |
| `OPENROUTER_API_KEY` | LLM generation |

Optional:

| Secret | Purpose |
|---|---|
| `GMAIL_USER` | Gmail sender |
| `GMAIL_APP_PASSWORD` | Gmail app password |
| `RECIPIENT_EMAIL` | Destination email |
| `HF_TOKEN` | Optional image generation |

## Optional Actions variables

| Variable | Default | Effect |
|---|---:|---|
| `TOTAL_POSTS` | `5` | Number of posts per run (1–8) |
| `IMAGE_POST_COUNT` | `0` | Optional AI images (0–TOTAL_POSTS) |
| `ENABLE_LLM_SCORING` | `false` | Adds an OpenRouter scoring pass for higher quality gating |
| `HF_IMAGE_MODEL` | `black-forest-labs/FLUX.1-schnell` | Hugging Face image model used when `HF_TOKEN` is configured |

## Workflow behavior

The workflow runs on the daily schedule or through `workflow_dispatch`. It no longer launches a full bot execution on every code push, which prevents ordinary repository maintenance from consuming API quota.

GitHub Actions uses current Node 24-compatible action releases (`checkout@v7`, `setup-python@v7`, `upload-artifact@v7`). Tests run before the bot. Generated state is committed only after a successful run.

## State files

`state/history.json` is the persistent deduplication state. `state/latest_threads.txt` and `state/latest_sources.txt` are runtime outputs and are ignored by Git. The workflow uploads all three as an artifact for 14 days.

## Safety around leaks

The bot may discuss reported leaks and legal actions, but it does not distribute leaked files, stolen credentials, piracy links, or instructions for accessing stolen material.

## Local verification

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m py_compile bot.py main.py
```
