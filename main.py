import os
import sys
import re
import json
import datetime
import time
import requests
import base64
import PIL.Image
import gspread

from oauth2client.service_account import ServiceAccountCredentials

# 🚨 RUNNER SYSTEM PATH FIX: Forces Python to recognize the local directory workspace
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# --- IMPORT PRODUCTION PLUMBING FROM UTILS ---
# Notice we removed trigger_n8n_omnichannel_webhook to handle it natively with binary data below
from utils import logger, send_telegram_alert, execute_youtube_upload_with_backoff

# --- PILLOW COMPATIBILITY FIX ---
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

from google import genai
from google.genai import types 
from moviepy.config import change_settings
from moviepy.editor import ImageClip, TextClip, CompositeVideoClip, AudioFileClip, CompositeAudioClip, VideoFileClip, ColorClip, concatenate_videoclips
from moviepy.audio.fx.all import audio_loop

# --- 1. SYSTEM CONFIG ---
change_settings({"IMAGEMAGICK_BINARY": "/usr/bin/convert"})

gen_client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'), http_options={'api_version': 'v1beta'})
ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY')
LEO_API_KEY = os.getenv('LEONARDO_API_KEY')
SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')

# --- ANIME STYLE LIBRARY ---
ANIME_STYLES = [
    "Ufotable (Fate/Series style, high-contrast, dynamic digital effects)",
    "Lupin III: The First (3D-CGI anime style, expressive, vibrant)",
    "Studio Ghibli (Hand-drawn, soft watercolors, lush nature)",
    "Wit Studio (Attack on Titan style, heavy lines, gritty cinematic)",
    "Makoto Shinkai (Your Name style, gorgeous skies, lens flares)",
    "90s Retro Anime (Cowboy Bebop style, cel-shaded, film grain)"
]

def check_idempotency_state(sheet):
    try:
        logger.info("Verifying global pipeline idempotency execution state...")
        records = sheet.get_all_records()
        if not records:
            return False
            
        today_str = str(datetime.date.today())
        for row in records:
            if any(str(val) == today_str for val in row.values()):
                logger.warning(f"🛑 Idempotency Barrier Triggered: Content already generated & logged for {today_str}. Exiting runner cleanly.")
                return True
                
        logger.info("Idempotency Validation: PASS. Ready to begin production run.")
        return False
    except Exception as e:
        logger.error(f"Idempotency validation engine failed: {e}. Defaulting to run for safety.")
        return False

def get_next_style(sheet):
    logger.info("Art Direction: Cycling historical anime art profiles...")
    try:
        records = sheet.get_all_records()
        if not records: return ANIME_STYLES[0]
        last_style_name = records[-1].get('Art_Style', '')
        try:
            current_idx = [s.split(' (')[0] for s in ANIME_STYLES].index(last_style_name)
            next_idx = (current_idx + 1) % len(ANIME_STYLES)
        except: next_idx = 0
        return ANIME_STYLES[next_idx]
    except Exception as e:
        logger.error(f"Style engine failure: {e}. Defaulting to primary asset template.")
        return ANIME_STYLES[0]

def get_memory():
    logger.info("Database: Initializing remote Google Sheets persistence client...")
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = json.loads(os.getenv('GOOGLE_SHEETS_JSON'))
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SPREADSHEET_ID).sheet1
        return sheet
    except Exception as e:
        logger.error(f"Failed to securely tie into Google Sheets persistence: {e}")
        return None

def scout_daily_gospel(art_style):
    logger.info(f"Intelligence: Scouting daily Gospel liturgical data with style target: {art_style}...")
    
    prompt = f"""
    Today is {datetime.date.today()}. Find the official Daily Gospel.
    
    1. SCRIPTURE: The exact book, chapter, and verse (e.g., John 3:16).
    2. TITLE: Create a "Curiosity Gap" title.
    3. HOOK: Must strictly follow this format: "[audio tag] Book Chapter:Verse — TITLE". (Example: "[warm] John 3:16 — The Ultimate Promise.")
    4. VERBATIM_VERSE: Provide the STRICTLY verbatim Bible text (60-80 words). Do not paraphrase or summarize a single word.
    5. CLIFFHANGER: A positive, highly encouraging, and intriguing closing thought. NEVER use doubtful, questioning, or pessimistic phrasing. Instead, build faith, affirmation, and wonder (Example: "[hopeful] His promise is already moving in your life today... will you step into the light?").

    🚨 NATIVE ELEVENLABS EMOTION TAGGING RULE:
    You must format the narration text for HOOK, VERBATIM_VERSE, and CLIFFHANGER using explicit ElevenLabs audio tags to inject powerful emotional connection.
    - Preface highly dramatic, intense, or critical moments with an appropriate delivery tag wrapped in SQUARE BRACKETS like [whispers], [grave], [emotional], or [intense].
    - Use transitions like [warm], [uplifting], or [hopeful] when moving from structural descriptions or solemn moments into bright, spiritual promises.
    - Keep sentence syntax rhythmic, utilizing ellipses (...) and em-dashes (—) alongside the voice tags for ultimate immersion.

    ART STYLE: Render every image in the style of {art_style}.
    SETTING: Strictly 1st-century Middle East.

    FORMAT:
    TITLE: [text]
    SCRIPTURE: [text]
    HOOK: [text]
    VERBATIM_VERSE: [text]
    CLIFFHANGER: [text]
    VISUAL_SUBJECT: [3-word description]
    IMAGE_A: [Atmospheric environment, {art_style}, 1st-century...]
    IMAGE_B: [Macro detail, {art_style}, 1st-century...]
    IMAGE_C: [Character emotion, {art_style}, 1st-century...]
    IMAGE_D: [Epic wide shot, {art_style}, 1st-century...]
    """
    try:
        res = gen_client.models.generate_content(model='gemini-2.5-flash', contents=prompt, config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())]))
        cleaned = res.text.replace('**', '')
        return {line.split(':', 1)[0].strip(): line.split(':', 1)[1].strip() for line in cleaned.split('\n') if ':' in line}
    except Exception as e:
        logger.error(f"Gemini Liturgical Scouting Model failure: {e}")
        return None

def generate_leonardo_image(prompt, filename):
    logger.info(f"Leonardo AI: Dispensing render compute call for {filename}...")
    url = "https://cloud.leonardo.ai/api/rest/v1/generations"
    headers = {"accept": "application/json", "content-type": "application/json", "authorization": f"Bearer {LEO_API_KEY}"}
    payload = {
        "height": 1024, "width": 576, 
        "prompt": f"{prompt}, professional anime style, clean lines", 
        "modelId": "6b645e3a-d64f-4341-a6d8-7a3690fbf042",
        "alchemy": True,
        "contrastRatio": 0.8
    }
    try:
        response = requests.post(url, json=payload, headers=headers).json()
        gen_id = response['sdGenerationJob']['generationId']
        for _ in range(15):
            time.sleep(7)
            status = requests.get(f"https://cloud.leonardo.ai/api/rest/v1/generations/{gen_id}", headers=headers).json()
            images = status.get('generations_by_pk', {}).get('generated_images', [])
            if images:
                with open(filename, 'wb') as f: f.write(requests.get(images[0]['url']).content)
                logger.info(f"✅ Asset saved to storage filesystem: {filename}")
                return images[0]['id']
    except Exception as e:
        logger.error(f"Leonardo image engine failure on prompt: {e}")
        return None

def animate_with_leonardo(image_id, filename):
    logger.info(f"Leonardo Motion SVD: Rendering video dynamics for Frame ID: {image_id}...")
    url = "https://cloud.leonardo.ai/api/rest/v1/generations/motion-svd"
    headers = {"accept": "application/json", "content-type": "application/json", "authorization": f"Bearer {LEO_API_KEY}"}
    try:
        res = requests.post(url, json={"imageId": image_id, "motionStrength": 4}, headers=headers).json()
        gen_id = res['sdGenerationJob']['generationId']
        for _ in range(25):
            time.sleep(10)
            status = requests.get(f"https://cloud.leonardo.ai/api/rest/v1/generations/{gen_id}", headers=headers).json()
            images = status.get('generations_by_pk', {}).get('generated_images', [])
            if images and images[0].get('motionMP4URL'):
                with open(filename, "wb") as f: f.write(requests.get(images[0]['motionMP4URL']).content)
                return filename
    except Exception as e:
        logger.warning(f"Leonardo SVD motion processing timed out: {e}. Falling back to standard panning.")
        return None

def push_to_n8n_webhook(video_path, title, description):
    """
    Sends the video file natively via multipart/form-data so n8n can directly 
    upload the binary file to Facebook without needing file path access.
    """
    webhook_url = os.getenv('N8N_WEBHOOK_URL')
    if not webhook_url:
        logger.warning("No N8N_WEBHOOK_URL found. Skipping omnichannel push.")
        return
        
    logger.info("Transmitting video binary payload to n8n omnichannel webhook for Facebook...")
    try:
        with open(video_path, 'rb') as f:
            # Package as standard multipart form data
            files = {'file': (os.path.basename(video_path), f, 'video/mp4')}
            data = {'title': title, 'description': description}
            
            response = requests.post(webhook_url, files=files, data=data)
            
        if response.status_code == 200:
            logger.info("✅ Successfully transferred binary payload to n8n pipeline!")
        else:
            logger.warning(f"⚠️ n8n Webhook returned status {response.status_code}: {response.text}")
    except Exception as e:
        logger.error(f"Failed to push binary data to n8n webhook: {e}")

def produce():
    sheet = get_memory()
    if not sheet: 
        logger.critical("Aborting sequence. Google Sheet infrastructure unreachable.")
        return
        
    # 🛑 LAYER 5 STATE TRACKING
    if check_idempotency_state(sheet):
        return

    style = get_next_style(sheet)
    data = scout_daily_gospel(style)
    if not data:
        send_telegram_alert("Gospel tracking module could not parse data entries today.", context="ERROR")
        return

    # 🎙️ AUDIO & ALIGNMENT
    logger.info("ElevenLabs: Communicating text-to-speech rendering pipeline request...")
    full_text = f"{data.get('HOOK')} {data.get('VERBATIM_VERSE')} {data.get('CLIFFHANGER')}"
    try:
        res_api = requests.post("https://api.elevenlabs.io/v1/text-to-speech/VCgLBmBjldJmfphyB8sZ/with-timestamps", 
                                json={"text": full_text, "model_id": "eleven_v3"}, 
                                headers={"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"}).json()
        
        # Explicit Quota Catch
        if 'audio_base64' not in res_api:
            raise KeyError(f"Missing audio data (Quota Exceeded or API Error). Response: {res_api}")
            
        with open("voice.mp3", "wb") as f: f.write(base64.b64decode(res_api['audio_base64']))
        alignment_data = res_api.get('alignment', {})
        voice = AudioFileClip("voice.mp3")
        duration = voice.duration
    except Exception as e:
        err_msg = f"ElevenLabs infrastructure engine connection failure: {e}"
        logger.error(err_msg)
        send_telegram_alert(err_msg, context="ERROR")
        return

    # 🎬 VIDEO ASSEMBLY
    seg_dur = duration / 4 
    video_clips = []
    for char in ['A', 'B', 'C', 'D']:
        img_fn, vid_fn = f"scene_{char}.png", f"scene_{char}.mp4"
        
        # Fallback safeguard in case Gemini drops an image tag
        safe_prompt = data.get(f'IMAGE_{char}') or f"1st-century biblical scene, {style}"
        img_id = generate_leonardo_image(safe_prompt, img_fn)
        
        animated = animate_with_leonardo(img_id, vid_fn) if img_id else None
        
        if animated and os.path.exists(animated):
            video_clips.append(VideoFileClip(animated).resize(height=1920).crop(width=1080, height=1920).without_audio().loop(duration=seg_dur).subclip(0, seg_dur))
        elif os.path.exists(img_fn):
            video_clips.append(ImageClip(img_fn).set_duration(seg_dur).resize(height=1920).crop(width=1080, height=1920).resize(lambda t: 1 + 0.03 * t))
        else:
            video_clips.append(ColorClip(size=(1080, 1920), color=(20, 20, 30)).set_duration(seg_dur))

    main_v = concatenate_videoclips(video_clips, method="compose")

    # 📝 SUBTITLES WITH REGEX CLEANUP
    subs = []
    if alignment_data:
        chars, starts, ends = alignment_data['characters'], alignment_data['character_start_times_seconds'], alignment_data['character_end_times_seconds']
        words, curr, s_t = [], "", None
        for idx, char in enumerate(chars):
            if char.strip() == "": 
                if curr: words.append({"text": curr, "start": s_t, "end": ends[idx-1]}); curr, s_t = "", None
            else:
                if not curr: s_t = starts[idx]
                curr += char
        if curr: words.append({"text": curr, "start": s_t, "end": ends[-1]})
        
        for j in range(0, len(words), 2):
            chunk = words[j:j+2]; txt_str = " ".join([w["text"] for w in chunk]).upper()
            
            # 🚨 Automatically strips out any [tags] so they don't appear on screen
            txt_str = re.sub(r'\[.*?\]', '', txt_str).strip()
            if not txt_str:
                continue
                
            s, e = chunk[0]["start"], (words[j+2]["start"] if j+2 < len(words) else duration)
            
            # Note: Ensure "THEBOLDFONT-FREEVERSION.ttf" is committed to your GitHub repo root!
            try:
                subs.append(TextClip(txt_str, font="THEBOLDFONT-FREEVERSION.ttf", fontsize=95, color='yellow', stroke_color='black', stroke_width=4, method='caption', size=(900, None)).set_duration(e-s).set_start(s).set_position(('center', 1300)).resize(lambda t: min(1.0, 0.8 + 5*t)))
            except:
                # Fallback to Impact if the custom TTF is missing from the runner environment
                subs.append(TextClip(txt_str, font="Impact", fontsize=95, color='yellow', stroke_color='black', stroke_width=4, method='caption', size=(900, None)).set_duration(e-s).set_start(s).set_position(('center', 1300)).resize(lambda t: min(1.0, 0.8 + 5*t)))

    # 🚀 LEGAL JOURNALISTIC SOURCE WATERMARK OVERLAY
    source_text = f"EDITORIAL: DAILY GOSPEL / VISUALS: LEONARDO AI"
    source_clip = (TextClip(source_text, font="Impact", fontsize=28, 
                            color='white', stroke_color='black', stroke_width=1, method='caption', size=(750, None))
                   .set_duration(duration)
                   .set_start(0)
                   .set_opacity(0.5) 
                   .set_position((50, 80)))

    # 🚀 EXPORT
    logger.info("MoviePy: Compiling timeline matrices, exporting h.264 wrapper allocation map...")
    final_video = CompositeVideoClip([main_v, source_clip] + subs).set_audio(voice).set_duration(duration)
    final_video.write_videofile("biblical_export.mp4", fps=24, codec="libx264", preset="ultrafast")

    # 🚀 ROBUST DEPLOYMENT WITH LOGGING & BACKOFF RETRIES
    if os.path.exists("biblical_export.mp4"):
        logger.info("Export file generated. Initializing production upload sequence...")
        try:
            creds_data = json.loads(os.getenv('YOUTUBE_CREDENTIALS'))
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload
            
            youtube = build("youtube", "v3", credentials=Credentials(**creds_data))
            
            # 🚨 BULLETPROOF CLEANER: Strips all brackets < > [ ] from metadata
            raw_title = f"{data.get('TITLE')} | {data.get('SCRIPTURE')}"
            safe_title = re.sub(r'[\[\]<>]', '', raw_title).strip()
            
            raw_verse = data.get('VERBATIM_VERSE', '')
            safe_verse = re.sub(r'[\[\]<>]', '', raw_verse).strip()
            
            fair_use_desc = (
                f"{safe_verse}\n\n"
                f"📖 Content & Media Citations:\n"
                f"- Scripture Data: Official Daily Gospel\n"
                f"- Visual Elements: Managed via Leonardo AI / Historical Recreation\n\n"
                f"⚖️ COPYRIGHT SAFE HARBOR & FAIR USE STATEMENT:\n"
                f"This video contains transformative, commentary, and educational analysis. "
                f"All assets are utilized under Fair Use guidelines for religious review purposes.\n\n"
                f"#dailygospel #faith #shorts"
            )
            
            body = {
                'snippet': {
                    'title': safe_title, 
                    'description': fair_use_desc, 
                    'categoryId': '22'
                }, 
                'status': {'privacyStatus': 'public'}
            }
            media_file = MediaFileUpload("biblical_export.mp4", chunksize=-1, resumable=True)
            
            # Executing our robust backoff/retry engine loop from utils.py
            resp = execute_youtube_upload_with_backoff(youtube, body, media_file)
            
            # 🚨 FIXED: Handle dictionary vs string outputs from your YouTube module
            final_video_id = resp if isinstance(resp, str) else resp.get('id', 'UPLOAD_SUCCESS')
            
            # Log back to Google Sheet database for history integrity
            sheet.append_row([str(datetime.date.today()), data.get('SCRIPTURE'), data.get('TITLE'), data.get('VISUAL_SUBJECT'), final_video_id, style.split(' (')[0]])
            logger.info("Successfully registered transaction to Google sheet database registry.")

            # =====================================================================
            # 5. OMNICHANNEL DISTRIBUTION (n8n Webhook)
            # =====================================================================
            push_to_n8n_webhook("biblical_export.mp4", safe_title, fair_use_desc)
            logger.info("Pipeline execution completely finished.")
            
        except Exception as e:
            upload_err = f"Pipeline upload sequence crashed completely: {e}"
            logger.error(upload_err)
            send_telegram_alert(upload_err, context="ERROR")

if __name__ == "__main__":
    produce()
