import os
import time
import logging
import requests
from googleapiclient.errors import HttpError

# =====================================================================
# PRODUCTION-GRADE LOGGING SETUP
# =====================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s",
    handlers=[
        logging.StreamHandler()  # Routes perfectly to GitHub Actions console logs
    ]
)
logger = logging.getLogger("VideoPipeline")

# =====================================================================
# STRICT SECRET HYGIENE & VALIDATION
# =====================================================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    logger.warning("Telegram alerting credentials missing in environment variables. Alerts will fall back to logs.")

# =====================================================================
# AUTOMATED ERROR ALERTING (Telegram Webhook)
# =====================================================================
def send_telegram_alert(message: str, context: str = "ERROR"):
    """Pushes a clean, structured alert directly to your phone via Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
        
    emoji = "🚨" if context == "ERROR" else "⚠️"
    # Format message safely for Telegram MarkdownV2
    safe_message = message.replace(".", "\\.").replace("-", "\\-").replace("!", "\\!")
    
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": f"{emoji} *Pipeline Alert \\[{context}\\]*\n\n`{safe_message}`",
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
# ROBUST EXCEPTION HANDLING & EXPONENTIAL BACKOFF
# =====================================================================
def execute_youtube_upload_with_backoff(youtube_client, body, media_file, max_retries=5):
    """Executes a YouTube upload utilizing exponential backoff for network/rate errors."""
    retries = 0
    delay = 5  # Baseline wait time in seconds
    
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
            # Retry on rate limits (429) or server errors (500, 502, 503)
            if e.resp.status in [429, 500, 502, 503]:
                logger.warning(f"Transient Google API Error {e.resp.status}. Applying backoff in {delay}s...")
                retries += 1
                time.sleep(delay)
                delay *= 2  # Progression: 5s, 10s, 20s, 40s...
            else:
                # Fatal errors (401 Unauthorized, Bad Metadata) should fail instantly
                error_msg = f"Fatal YouTube API Exception: {e.content.decode()}"
                logger.error(error_msg)
                send_telegram_alert(error_msg, context="ERROR")
                raise e
                
        except Exception as e:
            logger.warning(f"Standard connection or socket error: {e}. Retrying in {delay}s...")
            retries += 1
            time.sleep(delay)
            delay *= 2

    fatal_msg = f"Pipeline aborted. Max retries ({max_retries}) exhausted on video upload."
    logger.critical(fatal_msg)
    send_telegram_alert(fatal_msg, context="CRITICAL")
    raise TimeoutError(fatal_msg)
