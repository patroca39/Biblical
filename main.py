import os
import json
import datetime
import time
import requests
import base64
import PIL.Image
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- IMPORT PRODUCTION PLUMBING FROM UTILS ---
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
    """
    Idempotency Layer: Inspects Google Sheets to confirm if today's date
    has already been registered. Prevents costly API generation loops.
    """
    try:
        logger.info("Verifying global pipeline idempotency execution state...")
        records = sheet.get_all_records()
        if not records:
            return False
            
        today_str = str(datetime.date.today())
        # Iterate through the sheet to look for today's date row
        for row in records:
            # Assumes your first column tracks dates as strings or matching headers
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
    1. TITLE: Create a "Curiosity Gap" title.
    2. VERBATIM_VERSE: Provide the verbatim Bible text (60-80 words).
    3. HOOK: 5-word dramatic intro.
    4. CLIFFHANGER: Bright, hopeful question.
    	
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
        logger.error(f"Leonardo image generation engine failure on prompt ({prompt[:30]}): {e}")
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
        logger.warning(f"Leonardo SVD motion processing timed out or failed for asset {image_id}: {e}. Falling back to standard panning.")
        return None

def produce():
    sheet = get_memory()
    if not sheet: 
        logger.critical("Aborting sequence. Google Sheet infrastructure unreachable.")
        return
        
    # 🛑 INTEGRATED LAYER 5 STATE TRACKING
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
        res_api = requests.post("https://api.elevenlabs.io/v1/text-to-speech/SAxJUlDKRc79XAyeWyMu/with-timestamps", 
                                json={"text": full_text, "model_id": "eleven_multilingual_v2"}, 
                                headers={"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"}).json()
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
        img_id = generate_leonardo_image(data.get(f'IMAGE_{char}'), img_fn)
        animated = animate_with_leonardo(img_id, vid_fn) if img_id else None
        
        if animated and os.path.exists(animated):
            video_clips.append(VideoFileClip(animated).resize(height=1920).crop(width=1080, height=1920).without_audio().loop(duration=seg_dur).subclip(0, seg_dur))
        elif os.path.exists(img_fn):
            video_clips.append(ImageClip(img_fn).set_duration(seg_dur).resize(height=1920).crop(width=1080, height=1920).resize(lambda t: 1 + 0.03 * t))
        else:
            video_clips.append(ColorClip(size=(1080, 1920), color=(20, 20, 30)).set_duration(seg_dur))

    main_v = concatenate_videoclips(video_clips, method="compose")

    # 📝 SUBTITLES
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
            s, e = chunk[0]["start"], (words[j+2]["start"] if j+2 < len(words) else duration)
            subs.append(TextClip(txt_str, font="THEBOLDFONT-FREEVERSION.ttf", fontsize=95, color='yellow', stroke_color='black', stroke_width=4, method='caption', size=(900, None)).set_duration(e-s).set_start(s).set_position(('center', 1300)).resize(lambda t: min(1.0, 0.8 + 5*t)))

    # 🚀 EXPORT
    logger.info("MoviePy: Compiling timeline matrices, exporting h.264 wrapper allocation map...")
    final_video = CompositeVideoClip([main_v] + subs).set_audio(voice).set_duration(duration)
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
            body = {
                'snippet': {
                    'title': f"{data.get('TITLE')} | {data.get('SCRIPTURE')}", 
                    'description': data.get('VERBATIM_VERSE'), 
                    'categoryId': '22'
                }, 
                'status': {'privacyStatus': 'public'}
            }
            media_file = MediaFileUpload("biblical_export.mp4", chunksize=-1, resumable=True)
            
            # Executing our robust backoff/retry engine loop from utils.py
            resp = execute_youtube_upload_with_backoff(youtube, body, media_file)
            
            # Log back to Google Sheet database for history integrity
            sheet.append_row([str(datetime.date.today()), data.get('SCRIPTURE'), data.get('TITLE'), data.get('VISUAL_SUBJECT'), resp.get('id'), style.split(' (')[0]])
            logger.info("Successfully registered transaction to Google sheet database registry.")
            
        except Exception as e:
            upload_err = f"Pipeline upload sequence crashed completely: {e}"
            logger.error(upload_err)
            send_telegram_alert(upload_err, context="ERROR")

if __name__ == "__main__":
    produce()
