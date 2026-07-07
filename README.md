# CBC Print Media Monitor

Automated daily checker for the CBC India vendor signup page. Watches the
"Select Vendor/Partner Category" dropdown and sends a **Telegram alert** the
moment "Print Media" appears as an option (currently only AV, Outdoor Media,
and New Media are listed).

Runs entirely on **GitHub Actions** — no server, no local machine needed.

## How it works

1. A scheduled GitHub Actions workflow runs `scraper.py` daily at **10:00 AM IST**.
2. The script fetches the CBC vendor signup page and parses the category dropdown.
3. If "Print Media" is found in the options, it sends a Telegram message immediately.
4. If not found, it logs the current options and exits quietly — no spam.

## Files

| File | Purpose |
|---|---|
| `scraper.py` | Fetches the page, parses the dropdown, sends alerts |
| `requirements.txt` | Python dependencies (`requests`, `beautifulsoup4`) |
| `.github/workflows/monitor.yml` | Daily cron schedule + secret wiring |

## Setup

### 1. Clone / use this repo
```bash
git clone https://github.com/omtiwari17/cbc-monitor.git
cd cbc-monitor
```

### 2. Add GitHub Secrets
Repo → **Settings → Secrets and variables → Actions → New repository secret**

| Secret | Description |
|---|---|
| `TARGET_URL` | The real CBC vendor signup page URL |
| `TELEGRAM_BOT_TOKEN` | Token from [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_CHAT_ID` | Your Telegram chat ID (get via [@userinfobot](https://t.me/userinfobot)) |

### 3. Test manually
Go to **Actions** tab → **CBC Print Media Monitor** → **Run workflow**.
Check the logs under the "Run CBC monitor script" step to confirm it fetched
the page and read the dropdown options correctly.

### 4. Let it run
Once secrets are set and a manual test passes, no further action is needed —
GitHub Actions fires the check automatically every day at 10:00 AM IST
(`cron: "30 4 * * *"` in UTC).

## Notes

- Email alerting is implemented in `scraper.py` (`send_email_alert`) but
  currently disabled in favor of Telegram-only. Re-enable by uncommenting
  the relevant line in `send_alerts()` and adding `SMTP_*` secrets back.
- The dropdown-finding logic uses a 3-tier fallback (explicit selector →
  label proximity → brute-force scan) since the real page's exact HTML
  structure hasn't been confirmed yet. Once the real `TARGET_URL` is set,
  `DROPDOWN_SELECTOR_ATTRS` in `scraper.py` should be tightened for a more
  reliable match.
- If the dropdown turns out to be JavaScript-rendered (not present in raw
  HTML), this script will need to be swapped from `requests`/`BeautifulSoup`
  to Playwright.