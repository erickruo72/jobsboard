# Job Scraper → WordPress Auto-Poster

> Automated pipeline that scrapes jobs from target sites, rewrites job descriptions using AI to avoid verbatim duplication, and publishes posts to a WordPress site using the REST API + App Password authentication.

---

## Table of contents

1. [What it does](#what-it-does)
2. [Features](#features)
3. [Prerequisites](#prerequisites)
4. [Installation](#installation)
5. [Configuration](#configuration)
6. [How it works (high level)](#how-it-works-high-level)
7. [Usage](#usage)
8. [Scheduling / Deployment suggestions](#scheduling--deployment-suggestions)
9. [Security and ethical notes](#security-and-ethical-notes)
10. [Troubleshooting](#troubleshooting)
11. [Extending / Ideas](#extending--ideas)
12. [License](#license)

---

## What it does

This project collects job listings from one or more source websites, processes each listing through an AI-based rewriter so the published text is not a verbatim copy, and creates a WordPress post for each job via the WordPress REST API using a provided user email and App Password. It’s intended to automate content flow into a WordPress jobs board while reducing duplicate-content risk.

## Features

* Scrapes job listings (configurable selectors / patterns)
* Normalizes and extracts structured fields: title, company, location, salary, description, apply link, date
* Rewrites job descriptions with an AI rewriter (configurable prompt/templates)
* Publishes as WordPress posts using the REST API with App Password authentication (user email + app password)
* Deduplication checks (by job URL or fingerprint)
* Optional dry-run mode for testing

## Prerequisites

* Python 3.10+ (or your preferred runtime — instructions use Python)
* Basic familiarity with virtual environments and `pip`
* WordPress site with REST API enabled (most modern WP installs are ready)
* WordPress user with an App Password (user email + App Password used for Basic Auth)
* An API key or access to an AI rewrite service (OpenAI, Anthropic, or a local model) — optional but recommended

## Installation

1. Clone the repo:

```bash
git clone https://github.com/<your-user>/<repo>.git
cd <repo>
```

2. Create and activate a virtual environment (recommended):

```bash
python -m venv venv
# macOS / Linux
source venv/bin/activate
# Windows (PowerShell)
venv\Scripts\Activate.ps1
```

3. Install requirements:

```bash
pip install -r requirements.txt
```

## Configuration

Create a `.env` file in the project root (or set environment variables). Example `.env`:

```
# WordPress
WP_SITE_URL=https://example.com
WP_USER_EMAIL=you@example.com
WP_APP_PASSWORD=abcd efgh ijkl mnop

# AI rewriter (example for OpenAI)
OPENAI_API_KEY=sk-...
AI_REWRITE_MODEL=gpt-4o-mini

# Scraper
SOURCE_URL=https://jobs.example-source.com
USER_AGENT=job-scraper-bot/1.0 (+https://yourdomain.com)

# Optional settings
DRY_RUN=true
POST_CATEGORY_ID=5
POST_AUTHOR_ID=2
SCHEDULE_CRON=@hourly

# Storage / DB
DATA_DIR=./data

```

**Important:** Keep the `.env` file out of version control (add to `.gitignore`).

## How it works (high level)

1. **Scrape**: the scraper uses requests/HTTP + BeautifulSoup (or a headless browser if required) to fetch pages and extract job fields.
2. **Normalize**: extracted fields are normalized (dates parsed, HTML cleaned, unwanted markup removed).
3. **Deduplicate**: each job is fingerprinted (hash of source URL + title + company) and checked against a local store to avoid reposting.
4. **Rewrite**: the job description is passed to an AI rewriter which returns a rephrased description. Use prompts and constraints to keep required facts (apply link, salary) intact.
5. **Publish**: the script prepares a WordPress post payload and sends a `POST /wp-json/wp/v2/posts` request authenticated via HTTP Basic with `WP_USER_EMAIL:WP_APP_PASSWORD` as the credentials.
6. **Record**: success/failure results are recorded in a local DB or CSV for audit.

## Usage

### CLI

Basic example:

```bash
# test run without publishing
python run_scraper.py --source https://jobs.example-source.com --dry-run

# real run (publishes)
python run_scraper.py --source https://jobs.example-source.com
```

### Example env-specific run (Linux):

```bash
export $(cat .env | xargs)
python run_scraper.py
```

### Common flags

* `--dry-run`: do everything but do not call WP API
* `--limit N`: limit to N jobs per run
* `--rebuild`: ignore dedupe store and reprocess

## WordPress POST payload (example)

The script sends a JSON payload like the following to `POST /wp-json/wp/v2/posts`:

```json
{
  "title": "Rewritten Job Title",
  "content": "<p>Rewritten job description ...</p>",
  "status": "publish",
  "categories": [5],
  "excerpt": "Short summary",
  "meta": {
    "source_url": "https://original-job-url",
    "company": "Acme Inc.",
    "apply_url": "https://original-job-url/apply"
  }
}
```

Authentication uses HTTP Basic auth. Username is the WordPress user email, and the password is the App Password (the string you created in WP Admin).

## Scheduling / Deployment suggestions

* Run as a cron job (Linux) or as a scheduled job in your cloud platform (AWS Lambda with EventBridge, Google Cloud Run + Cloud Scheduler, or a small VPS systemd timer).
* Keep runs frequent enough to stay fresh but not so frequent you overload source sites (e.g., every 30–60 minutes).
* Respect `robots.txt` and site rate limits; add delays between requests.

## Security and ethical notes

* **Do not publish copyrighted content verbatim.** The AI rewriter lowers the risk but doesn’t absolve you of IP risks. Always ensure you have the right to republish content.
* **Protect secrets**: never commit `WP_APP_PASSWORD`, `OPENAI_API_KEY`, or other secrets into source control. Use `.env` files, secret managers, or cloud environment variables.
* **App Password permissions**: App Passwords inherit the permissions of the WordPress user who created them. Ideally use a dedicated user with limited permissions (e.g., `author`) and not an administrator account.
* **Rate limits and site policies**: scraping other sites may violate their terms of service. Prefer public job feeds, official APIs, or permissioned partnerships.

## Troubleshooting

* **401 Unauthorized** when posting to WP: check `WP_USER_EMAIL` and `WP_APP_PASSWORD` are correct and that the user has permission to create posts.
* **403 Forbidden**: server might block Basic Auth; ensure REST API is enabled and App Password support is available (WordPress 5.6+ or relevant plugin).
* **Connection resets / 429 Too Many Requests**: slow down requests, implement retries with exponential backoff, and add caching.
* **AI rewrite failures**: confirm your API key and rate limits with the AI provider.

## Extending / Ideas

* Add multiple source scrapers with per-source selectors.
* Use a small SQLite or Redis store for dedupe and job state.
* Extract structured metadata (position type, seniority, skills) and publish them in custom fields.
* Add image/company-logo fetching and attach media to the post via `POST /wp-json/wp/v2/media`.
* Add an admin dashboard to preview pending posts before publishing.

## Example `.gitignore`

```
.env
venv/
__pycache__/
data/
```

## License

This project is provided under the MIT License — see `LICENSE` for details.


