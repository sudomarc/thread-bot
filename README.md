# Thread Bot

Automated social-content bot for current **cybersecurity, technology, AI, gaming, and internet news**. It generates source-grounded posts, optionally creates images, emails the report when Gmail works, and keeps a GitHub Actions artifact.

## Current architecture

`NewsAPI → filtering/deduplication → strategy slot → OpenRouter generation → strict parsing/validation → optional LLM quality scoring → report/state → optional images/email`

The maintained implementation is `bot.py`. `main.py` remains a compatibility entrypoint. `strategy_runner.py` is the scheduled growth layer: it asks for **one targeted post per scheduled run** and rotates through the 30-day editorial plan.

### 30-day Threads strategy

The strategy is designed from the current audience signals:

- Primary audience: AI/tech-oriented adults with strong gaming overlap.
- Core objective: turn discovery into followers, not just maximize raw views.
- Cadence: **5 targeted posts per week** at GMT/UTC times aligned with the strongest observed audience windows plus controlled test slots.
- Formats: AI/tech opinions, questions, relatable humor, gaming/AI, explainers, and broader observations.
- Hook style: strong first line, short readable lines, direct questions when conversation is the goal.

### Target metrics

These are operating targets for experimentation, not guaranteed outcomes:

| Metric | 30-day target |
|---|---:|
| Views | 20,000–30,000 |
| Spectators | 12,000+ |
| New followers | 75–150 |
| Views → follower conversion | 0.3–0.6% |
| Posts | 20–25 |
| Posts above 1,000 views | 5+ |
| Posts above 5,000 views | 1–3 |

### Scheduled slots (GMT/UTC)

- Monday 18:00
- Wednesday 14:00
- Friday 18:00
- Saturday 13:00
- Sunday 16:00

The workflow runs exactly one strategy slot per scheduled execution. `state/history.json` stores the strategy cursor so the editorial sequence advances only after a successful generation.

### Editorial sequence

The first 20 successful runs cover four weeks of deliberate formats, including:

- strong AI/technology opinions
- reply-oriented questions
- concise tech/developer humor
- gaming + AI discussion
- current-news explainers
- cybersecurity takes
- broader AI observations
- follower-conversion posts aimed at builders and tech audiences

Current-news posts remain source-grounded. Relatable posts use the existing curated topic pool and avoid recent topic repetition.

## Reliability and consistency

- Searches cybersecurity, technology/AI, and gaming on every run.
- Restricts articles to a rolling 72-hour window and rejects future/invalid timestamps.
- Sends the NewsAPI key through `X-Api-Key` instead of the query string.
- Canonicalizes article URLs and removes common tracking parameters before deduplication.
- Remembers only **articles actually used by generated posts**, avoiding accidental starvation of future runs.
- Keeps `latest_sources.txt` aligned with the sources cited by the generated report.
- Requires sequential post numbering, valid source markers, unique source usage, valid topic tags, minimum current-news coverage, and gaming coverage when gaming sources are available in the base bot.
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
| `IMAGE_POST_COUNT` | `0` | Optional AI images for the base bot |
| `ENABLE_LLM_SCORING` | `false` | Adds an OpenRouter scoring pass for higher quality gating |
| `HF_IMAGE_MODEL` | `black-forest-labs/FLUX.1-schnell` | Hugging Face image model used when `HF_TOKEN` is configured |

`TOTAL_POSTS` is intentionally fixed to `1` by the strategy workflow. The base `bot.py` remains capable of multi-post generation for compatibility/local use.

## Workflow behavior

The strategy workflow runs the 30-day editorial sequence on five UTC slots per week. It no longer launches a full five-post generation on every daily schedule, avoiding unnecessary model/API usage and matching the planned publishing cadence.

GitHub Actions uses current Node 24-compatible action releases (`checkout@v7`, `setup-python@v7`, `upload-artifact@v7`). Tests run before the bot. Generated state is committed only after a successful run.

## State files

`state/history.json` is the persistent deduplication and strategy state. `state/latest_threads.txt` and `state/latest_sources.txt` are runtime outputs and are ignored by Git. The workflow uploads all three as an artifact for 14 days.

## Safety around leaks

The bot may discuss reported leaks and legal actions, but it does not distribute leaked files, stolen credentials, piracy links, or instructions for accessing stolen material.

## Local verification

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m py_compile bot.py strategy_runner.py main.py
```
