"""
CBC India Vendor Empanelment Monitor
-------------------------------------
Checks the CBC "Fresh Empanelment Registration" vendor signup page daily
to see if "Print Media" has appeared as an option in the
"Select Vendor/Partner Category" dropdown. Sends an Email and/or Telegram
alert the moment it does.

Designed to run unattended on GitHub Actions. All secrets are read from
environment variables (populated from GitHub Secrets in the workflow).
"""

import os
import sys
import logging
import smtplib
from email.mime.text import MIMEText

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

# TODO: Replace with the real CBC vendor signup URL once you confirm it.
TARGET_URL = os.environ.get("TARGET_URL", "https://example-cbc-url.com/signup")

# The visible label text of the dropdown we're targeting. Used as a fallback
# / sanity check if the dropdown has no reliable id/name attribute.
DROPDOWN_LABEL_TEXT = "Select Vendor/Partner Category"

# The option text we are watching for.
TARGET_OPTION_TEXT = "Print Media"

# How the script identifies the dropdown element. Update these once you
# inspect the real page's HTML (view-source or browser DevTools).
# Common patterns: {"name": "vendor_category"} or {"id": "vendorCategory"}.
DROPDOWN_SELECTOR_ATTRS = {
    # "id": "vendorCategory",      # <- uncomment/edit once you know the real id
    # "name": "vendor_category",   # <- or the real name attribute
}

REQUEST_TIMEOUT = 20  # seconds
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CORE SCRAPING LOGIC
# ---------------------------------------------------------------------------

def fetch_page(url: str) -> str:
    """Fetch page HTML with a browser-like User-Agent and proper error handling."""
    headers = {"User-Agent": USER_AGENT}
    try:
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.text
    except requests.exceptions.Timeout:
        logger.error("Request timed out while fetching %s", url)
    except requests.exceptions.ConnectionError:
        logger.error("Connection error while reaching %s (site may be down)", url)
    except requests.exceptions.HTTPError as e:
        logger.error("HTTP error %s while fetching %s", e, url)
    except requests.exceptions.RequestException as e:
        logger.error("Unexpected request error: %s", e)
    return ""


def find_dropdown(soup: BeautifulSoup):
    """
    Locate the target <select> element.

    Strategy (in order):
    1. Use explicit attrs in DROPDOWN_SELECTOR_ATTRS if provided (most reliable).
    2. Fall back to searching for a <select> near a <label>/text matching
       DROPDOWN_LABEL_TEXT (best-effort, since real markup is unknown for now).
    3. Fall back to scanning ALL <select> tags and returning the first one
       whose options look plausible (contains at least one of the known
       current categories: AV, Outdoor Media, New Media).
    """
    # Strategy 1: direct attribute match
    if DROPDOWN_SELECTOR_ATTRS:
        select_tag = soup.find("select", attrs=DROPDOWN_SELECTOR_ATTRS)
        if select_tag:
            return select_tag

    # Strategy 2: find a label containing the target text, then find the
    # <select> it's associated with (via 'for' attribute or nearby sibling).
    label = soup.find(
        lambda tag: tag.name in ("label", "span", "div", "th", "td")
        and tag.string
        and DROPDOWN_LABEL_TEXT.lower() in tag.get_text(strip=True).lower()
    )
    if label:
        # Try 'for' attribute linking to an id
        for_attr = label.get("for")
        if for_attr:
            select_tag = soup.find("select", id=for_attr)
            if select_tag:
                return select_tag
        # Try nearby <select> in the same parent container
        parent = label.find_parent()
        if parent:
            select_tag = parent.find("select")
            if select_tag:
                return select_tag

    # Strategy 3: brute-force scan for a plausible dropdown
    known_current_options = {"av", "outdoor media", "new media"}
    for select_tag in soup.find_all("select"):
        option_texts = {
            opt.get_text(strip=True).lower() for opt in select_tag.find_all("option")
        }
        if option_texts & known_current_options:
            return select_tag

    return None


def check_print_media_option(html: str) -> tuple[bool, list[str]]:
    """
    Parse the HTML and check whether 'Print Media' is present in the
    target dropdown's options.

    Returns:
        (found: bool, current_options: list[str])
    """
    soup = BeautifulSoup(html, "html.parser")
    dropdown = find_dropdown(soup)

    if dropdown is None:
        raise ValueError(
            "Could not locate the vendor category dropdown. "
            "The page structure may have changed, or it may be rendered "
            "dynamically via JavaScript (in which case, switch to Playwright)."
        )

    options = [opt.get_text(strip=True) for opt in dropdown.find_all("option")]
    options = [o for o in options if o]  # drop blank/placeholder options

    found = any(TARGET_OPTION_TEXT.lower() == o.lower() for o in options)
    return found, options


# ---------------------------------------------------------------------------
# NOTIFICATION LOGIC
# ---------------------------------------------------------------------------

def send_email_alert(subject: str, body: str) -> bool:
    """
    Send an email alert via SMTP.

    Required environment variables:
        SMTP_HOST       e.g. smtp.gmail.com
        SMTP_PORT       e.g. 587
        SMTP_USER       your sending email address
        SMTP_PASSWORD   app password / SMTP password (NOT your normal login password)
        ALERT_EMAIL_TO  recipient email address (can be same as SMTP_USER)
    """
    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = os.environ.get("SMTP_PORT")
    smtp_user = os.environ.get("SMTP_USER")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    to_email = os.environ.get("ALERT_EMAIL_TO")

    if not all([smtp_host, smtp_port, smtp_user, smtp_password, to_email]):
        logger.info("Email alert skipped: SMTP environment variables not fully set.")
        return False

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = to_email

    try:
        with smtplib.SMTP(smtp_host, int(smtp_port), timeout=REQUEST_TIMEOUT) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, [to_email], msg.as_string())
        logger.info("Email alert sent successfully to %s", to_email)
        return True
    except smtplib.SMTPAuthenticationError:
        logger.error("Email alert failed: SMTP authentication error (check user/password).")
    except (smtplib.SMTPException, OSError) as e:
        logger.error("Email alert failed: %s", e)
    return False


def send_telegram_alert(message: str) -> bool:
    """
    Send an alert via Telegram Bot API.

    Required environment variables:
        TELEGRAM_BOT_TOKEN   token from @BotFather
        TELEGRAM_CHAT_ID     your personal or group chat id
    """
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        logger.info("Telegram alert skipped: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set.")
        return False

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}

    try:
        response = requests.post(url, data=payload, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        logger.info("Telegram alert sent successfully.")
        return True
    except requests.exceptions.RequestException as e:
        logger.error("Telegram alert failed: %s", e)
    return False


def send_alerts(current_options: list[str]) -> None:
    """Fire both notification channels; either can be configured independently."""
    subject = "🚨 CBC Print Media Empanelment is OPEN!"
    body = (
        "Good news! 'Print Media' now appears in the CBC vendor category dropdown.\n\n"
        f"URL: {TARGET_URL}\n"
        f"Current dropdown options: {', '.join(current_options)}\n\n"
        "Go register now before the window closes."
    )

    # Email alerts disabled — using Telegram only. To re-enable, uncomment
    # the two lines below and add the SMTP_* secrets back in GitHub.
    # email_sent = send_email_alert(subject, body)
    email_sent = False
    telegram_sent = send_telegram_alert(f"*{subject}*\n\n{body}")

    if not email_sent and not telegram_sent:
        logger.warning(
            "No alert channel is configured or all failed. "
            "Set up SMTP_* or TELEGRAM_* secrets to receive notifications."
        )


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main() -> int:
    logger.info("Starting CBC Print Media check for URL: %s", TARGET_URL)

    html = fetch_page(TARGET_URL)
    if not html:
        logger.error("No HTML retrieved. Aborting this run (will retry on next schedule).")
        return 1

    try:
        found, options = check_print_media_option(html)
    except ValueError as e:
        # Structure changed / dropdown not found — log clearly, don't crash the workflow.
        logger.error("Parsing error: %s", e)
        return 1

    logger.info("Current dropdown options: %s", options)

    if found:
        logger.info("🎉 'Print Media' FOUND in dropdown! Sending alerts...")
        send_alerts(options)
    else:
        logger.info("'Print Media' not yet available. No alert sent.")

    return 0


if __name__ == "__main__":
    sys.exit(main())