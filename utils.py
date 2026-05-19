import os
import time
import logging
import requests
from googleapiclient.errors import HttpError

# =====================================================================
# 2. PRODUCTION-GRADE LOGGING SETUP
# =====================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s",
    handlers=[
        logging.StreamHandler() # Routes perfectly to GitHub Actions console logs
    ]
)
logger = logging.getLogger("VideoPipeline")

# =====================================================================
# 1. STRICT SECRET HYGIENE
# =====================================================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
# Fallback validation to crash early before executing costly tasks
if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    logger.warning("Telegram alerting credentials missing. Alerts will fall back to standard logging.")

# =====================================================================
# 3. AUTOMATED ERROR ALERTING (Telegram Webhook)
# =====================================================================
def send_telegram_alert(message: str, context: str = "ERROR"):
    """Pushes a structured alert directly to your phone via Telegram Bot API."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
        
    emoji = "🚨" if context == "ERROR" else "⚠️"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": f"{emoji} *Pipeline Alert [{context}]*\n\n`{message}`",
        "parse_mode": "MarkdownV2"
    }
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code != 200:
            logger.error(f"Failed to push Telegram alert: {response.text}")
    except Exception as e:
        logger.error(f"Telegram webhook connection failure: {e}")

# =====================================================================
# 4. EXCEPTION HANDLING & EXPONENTIAL BACKOFF
# =====================================================================
def execute_youtube_upload_with_backoff(youtube_client, body, media_file, max_retries=5):
    """Executes a YouTube upload utilizing exponential backoff for network/rate errors."""
    retries = 0
    delay = 5  # Start with a 5-second baseline wait
    
    while retries < max_retries:
        try:
            logger.info(f"Initiating upload chunk stream (Attempt {retries + 1}/{max_retries})...")
            request = youtube_client.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media_file
            )
            response = request.execute()
            logger.info(f"✅ Success! Asset deployed. Video ID: {response.get('id')}")
            return response
            
        except HttpError as e:
            # Handle rate limits (429) or transient backend server errors (500, 503)
            if e.resp.status in [429, 500, 502, 503]:
                logger.warning(f"Transient Google API Error {e.resp.status}. Applying backoff...")
                retries += 1
                time.sleep(delay)
                delay *= 2  # Exponential progression: 5s, 10s, 20s, 40s...
            else:
                # Fatal Client errors (e.g., 401 Unauthorized, Bad Metadata) should crash out immediately
                error_msg = f"Fatal YouTube API Exception: {e.content.decode()}"
                logger.error(error_msg)
                send_telegram_alert(error_msg, context="ERROR")
                raise e
                
        except Exception as e:
            logger.warning(f"Standard connection or socket error: {e}. Retrying...")
            retries += 1
            time.sleep(delay)
            delay *= 2

    # Out of retries
    fatal_msg = f"Pipeline aborted. Max retries ({max_retries}) exhausted on video file upload."
    logger.critical(fatal_msg)
    send_telegram_alert(fatal_msg, context="CRITICAL")
    raise TimeoutError(fatal_msg)
