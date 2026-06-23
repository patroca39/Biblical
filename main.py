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
import random
import numpy as np
from pydantic import BaseModel 

from oauth2client.service_account import ServiceAccountCredentials

# 🚨 RUNNER SYSTEM PATH FIX: Forces Python to recognize the local directory workspace
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# --- IMPORT PRODUCTION PLUMBING FROM UTILS & MOTION ENGINE ---
from utils import logger, send_telegram_alert, execute_youtube_upload_with_backoff
from motion_engine import apply_motion

# --- PILLOW COMPATIBILITY FIX ---
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

from google import genai
from google.genai import types 
from moviepy.config import change_settings
from moviepy.editor import ImageClip, TextClip, CompositeVideoClip, AudioFileClip, CompositeAudioClip, VideoFileClip, ColorClip, concatenate_videoclips, concatenate_audioclips
from moviepy.audio.fx.all import audio_loop
from moviepy.audio.AudioClip import AudioArrayClip

# --- 1. SYSTEM CONFIG ---
change_settings({"IMAGEMAGICK_BINARY": "/usr/bin/convert"})

gen_client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))
ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY')
LEO_API_KEY = os.getenv('LEONARDO_API_KEY')
SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')

FONT_FILE = "THEBOLDFONT-FREEVERSION.ttf"
DEFAULT_VOICE_ID = "dPah2VEoifKnZT37774q" 

ANIME_STYLES = [
    "Ufotable (Fate/Series style, high-contrast, dynamic digital effects)",
    "Lupin III: The First (3D-CGI anime style, expressive, vibrant)",
    "Studio Ghibli (Hand-drawn, soft watercolors, lush nature)",
    "Wit Studio (Attack on Titan style, heavy lines, gritty cinematic)",
    "Makoto Shinkai (Your Name style, gorgeous skies, lens flares)",
    "90s Retro Anime (Cowboy Bebop style, cel-shaded, film grain)"
]

# --- UPGRADED BIBLICAL SFX MAP ---
SFX_PROMPT_MAP = {
    "THUNDER": "Deep, distant, terrifying thunder rolling across an ancient desert valley, cinematic",
    "DESERT_WIND": "Howling, desolate wind blowing sand across a barren wasteland",
    "STONE_GRIND": "Massive, heavy ancient stone slab grinding slowly against rock, tomb opening",
    "SWORD_DRAW": "Sharp, metallic shing of a heavy bronze sword being drawn from a scabbard",
    "ANGELIC_CHOIR": "Ethereal, distant angelic choir humming a single, resonant, holy chord",
    "FIRE_CRACKLE": "Intense, roaring flames burning like a massive bonfire or burning bush",
    "HEARTBEAT": "Slow, deep, terrifying cinematic heartbeat, heavy bass",
    "SAND_STEPS": "Slow, deliberate footsteps crunching loudly on dry desert sand",
    "NORMAL": ""
}

# --- RHYTHM & BACKOFF ENGINES ---
def make_silence(duration):
    """Generates pure silence array for organic human-paced breathing gaps."""
    return AudioArrayClip(np.zeros((int(44100 * duration), 2)), fps=44100).set_duration(duration)

def generate_content_with_retry(model_name, prompt, config, max_retries=5):
    delay = 2
    for attempt in range(max_retries):
        try:
            return gen_client.models.generate_content(model=model_name, contents=prompt, config=config)
        except Exception as e:
            error_str = str(e)
            if "503" in error_str or "429" in error_str or "UNAVAILABLE" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                if attempt == max_retries - 1:
                    logger.warning(f"Primary model {model_name} failed. Attempting fallback...")
                    return gen_client.models.generate_content(model='gemini-1.5-flash', contents=prompt, config=config)
                logger.warning(f"Gemini server overloaded. Retrying in {delay}s... (Attempt {attempt+1}/{max_retries})")
                time.sleep(delay)
                delay *= 2
            else:
                raise e

# --- ELEVENLABS & LEONARDO APIs ---
def generate_elevenlabs_sfx(prompt, filename):
    if not prompt: return False
    logger.info(f"🔊 Generating dynamic SFX: {prompt}")
    url = "https://api.elevenlabs.io/v1/sound-generation"
    headers = {"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"}
    try:
        response = requests.post(url, json={"text": prompt, "duration_seconds": 2.5}, headers=headers)
        if response.status_code == 200:
            with open(filename, 'wb') as f: f.write(response.content)
            return True
        return False
    except: return False

def generate_leonardo_image(prompt, filename, char_ref_id=None):
    logger.info(f"Leonardo AI: Dispensing render compute call for {filename}...")
    url = "https://cloud.leonardo.ai/api/rest/v1/generations"
    headers = {"accept": "application/json", "content-type": "application/json", "authorization": f"Bearer {LEO_API_KEY}"}
    
    hardened_prompt = f"{prompt}, professional anime style, highly expressive human emotions, clean lines"
    payload = {
        "height": 1024, "width": 576, 
        "prompt": hardened_prompt, 
        "modelId": "aa77f04e-3eec-4034-9c07-d0f619684628",
        "alchemy": True, "contrastRatio": 0.8
    }

    if char_ref_id:
        payload["controlnets"] = [{"initImageId": char_ref_id, "initImageType": "GENERATED", "preprocessorId": 133, "strengthType": "Mid"}]

    try:
        response = requests.post(url, json=payload, headers=headers).json()
        if 'sdGenerationJob' not in response: return None
            
        gen_id = response['sdGenerationJob']['generationId']
        for _ in range(15):
            time.sleep(7)
            status = requests.get(f"https://cloud.leonardo.ai/api/rest/v1/generations/{gen_id}", headers=headers).json()
            images = status.get('generations_by_pk', {}).get('generated_images', [])
            if images:
                with open(filename, 'wb') as f: f.write(requests.get(images[0]['url']).content)
                return images[0]['id']
    except Exception as e:
        logger.error(f"Leonardo image engine failure: {e}")
        return None
    return None

def animate_with_leonardo(image_id, filename):
    logger.info(f"Leonardo Motion SVD: Rendering video dynamics for Frame ID: {image_id}...")
    url = "https://cloud.leonardo.ai/api/rest/v1/generations/motion-svd"
    headers = {"accept": "application/json", "content-type": "application/json", "authorization": f"Bearer {LEO_API_KEY}"}
    try:
        res = requests.post(url, json={"imageId": image_id, "motionStrength": 4}, headers=headers).json()
        gen_id = res['motionSvdGenerationJob']['generationId']
        
        for _ in range(25):
            time.sleep(10)
            status = requests.get(f"https://cloud.leonardo.ai/api/rest/v1/generations/{gen_id}", headers=headers).json()
            images = status.get('generations_by_pk', {}).get('generated_images', [])
            if images and images[0].get('motionMP4URL'):
                with open(filename, "wb") as f: f.write(requests.get(images[0]['motionMP4URL']).content)
                return filename
    except Exception as e:
        logger.warning(f"Leonardo SVD motion processing timed out: {e}")
        return None

# --- MEMORY & IDEMPOTENCY ---
def get_memory():
    logger.info("Database: Initializing remote Google Sheets persistence client...")
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = json.loads(os.getenv('GOOGLE_SHEETS_JSON'))
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client.open_by_key(SPREADSHEET_ID).sheet1
    except Exception as e:
        logger.error(f"Failed to securely tie into Google Sheets persistence: {e}")
        return None

def check_idempotency_state(sheet):
    try:
        records = sheet.get_all_records()
        if not records: return False
        today_str = str(datetime.date.today())
        for row in records:
            if any(str(val) == today_str for val in row.values()):
                logger.warning(f"🛑 Idempotency Barrier Triggered: Content already generated & logged for {today_str}.")
                return True
        return False
    except: return False

def get_next_style(sheet):
    try:
        records = sheet.get_all_records()
        if not records: return ANIME_STYLES[0]
        last_style_name = records[-1].get('Art_Style', '')
        current_idx = [s.split(' (')[0] for s in ANIME_STYLES].index(last_style_name)
        return ANIME_STYLES[(current_idx + 1) % len(ANIME_STYLES)]
    except: return ANIME_STYLES[0]

def push_to_n8n_webhook(video_path, title, description):
    webhook_url = os.getenv('N8N_WEBHOOK_URL')
    if not webhook_url: return
        
    logger.info("Transmitting video binary payload to n8n webhook...")
    try:
        with open(video_path, 'rb') as f:
            files = {'file': (os.path.basename(video_path), f, 'video/mp4')}
            response = requests.post(webhook_url, files=files, data={'title': title, 'description': description}, timeout=60)
        if response.status_code == 200: logger.info("✅ Successfully transferred binary payload to n8n pipeline!")
        else: logger.warning(f"⚠️ n8n Webhook returned status {response.status_code}: {response.text}")
    except Exception as e: logger.error(f"Failed to push binary data to n8n webhook: {e}")

# --- INTELLIGENCE ENGINE ---
def scout_daily_gospel(art_style):
    logger.info(f"Intelligence: Scouting daily Gospel liturgical data with style target: {art_style}...")
    
    class GospelSchema(BaseModel):
        TITLE: str
        SCRIPTURE: str
        VISUAL_SUBJECT: str
        IMAGE_A: str
        IMAGE_B: str
        IMAGE_C: str
        IMAGE_D: str
        IMAGE_E: str
        IMAGE_F: str
        MONOLOGUE: str
        ENGAGEMENT: str

    search_prompt = f"What is the official Catholic Daily Gospel reading for today, {datetime.date.today()}? Return the scripture reference and the verbatim text."
    try:
        search_res = generate_content_with_retry(
            model_name='gemini-2.5-flash', prompt=search_prompt, 
            config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())], temperature=0.3)
        )
        raw_gospel_data = search_res.text
    except Exception as e:
        logger.error(f"Gemini Grounding Search failure: {e}")
        return None

    formatting_prompt = f"""
    Based on the following Daily Gospel reading:
    {raw_gospel_data}
    
    AUDIO SYNCHRONIZATION MANDATE (CRITICAL): 
    Your MONOLOGUE must be broken down into sequentially tagged segments. Do not provide separate Hook/Verse/Cliffhanger fields; compile them ALL into the unified MONOLOGUE string using this exact syntax:
    [NARRATOR|MOTION_PROFILE|SFX_TRIGGER]: "[vocal emotion tag] The dialogue text here."
    
    Available MOTION_PROFILES: REVERENT_ZOOM, DIVINE_ASCENSION, WRATH_TREMOR, HOLY_FLASH, ABYSSAL_SHADOW, ORGANIC_DRIFT
    Available SFX_TRIGGERS: NORMAL, THUNDER, DESERT_WIND, STONE_GRIND, SWORD_DRAW, ANGELIC_CHOIR, FIRE_CRACKLE, HEARTBEAT, SAND_STEPS
    
    Example MONOLOGUE Output:
    "[NARRATOR|ORGANIC_DRIFT|NORMAL]: [warm] John 3:16 — The Ultimate Promise. [NARRATOR|REVERENT_ZOOM|THUNDER]: [intense] For God so loved the world..."
    
    VISUAL ACTION MANDATE:
    ART STYLE: Render every image in the style of {art_style}. You must generate 6 chronological scenes.
    IMAGE_A: Atmospheric environment establishing the scene. First-person POV.
    IMAGE_B: Character emotion and action, guided strictly by script verbs. First-person POV.
    IMAGE_C: Macro detail of the physical action or divine element. First-person POV.
    IMAGE_D: Epic wide shot of the central action escalating.
    IMAGE_E: Close up reaction shot or miraculous moment.
    IMAGE_F: Epic wide shot of the aftermath or miracle. First-person POV.
    """
    
    for attempt in range(4):
        try:
            format_res = generate_content_with_retry(
                model_name='gemini-2.5-flash', prompt=formatting_prompt, 
                config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=GospelSchema, temperature=0.65)
            )
            return json.loads(format_res.text)
        except Exception as e:
            logger.warning(f"Formatting attempt {attempt + 1} failed: {e}. Cooldown...")
            time.sleep(10)
    return None

# --- PRODUCTION PIPELINE ---
def produce():
    sheet = get_memory()
    if not sheet or check_idempotency_state(sheet): return

    style = get_next_style(sheet)
    data = scout_daily_gospel(style)
    if not data:
        send_telegram_alert("Gospel tracking module could not parse data entries today.", context="ERROR")
        return

    logger.info("🎨 Commencing Dual-Render Asset Pipeline (Images + SVD)...")
    base_character_id = None 
    asset_sequence = [] # Stores dicts of {'img': path, 'vid': path}

    # Increased to 6 scenes for better pacing
    for char in ['A', 'B', 'C', 'D', 'E', 'F']:
        img_fn, vid_fn = f"scene_{char}.png", f"scene_{char}.mp4"
        safe_prompt = data.get(f'IMAGE_{char}') or f"1st-century biblical scene, {style}"
        
        img_id = generate_leonardo_image(safe_prompt, img_fn, char_ref_id=base_character_id)
        if img_id and not base_character_id: base_character_id = img_id
        
        animated = animate_with_leonardo(img_id, vid_fn) if img_id else None
        asset_sequence.append({'img': img_fn, 'vid': animated})

    logger.info("🎙️ Parsing Audio Alignment & Rhythm...")
    monologue = data.get('MONOLOGUE', '')
    segments = re.findall(r'\[([A-Za-z0-9_|\s]+)\]:?\s*([^\[]+)', monologue)
    if not segments: segments = [("NARRATOR|ORGANIC_DRIFT|NORMAL", monologue)]

    audio_clips = []
    dynamic_sfx_clips = []
    word_timestamps_master = []
    elapsed_time_offset = 0.0
    gap_durations = []

    for idx, (full_tag, text) in enumerate(segments):
        phrase_text = text.strip()
        tag_parts = full_tag.upper().split('|')
        intensity_action = tag_parts[1].strip() if len(tag_parts) > 1 else "ORGANIC_DRIFT"
        sfx_trigger = tag_parts[2].strip() if len(tag_parts) > 2 else "NORMAL"
        
        # --- NEW TIGHT PACING LOGIC ---
        if idx < len(segments) - 1:
            if "WRATH" in intensity_action or "RUNNING" in full_tag: gap = random.uniform(0.05, 0.15)
            elif "REVERENT" in intensity_action or "REVELATION" in full_tag: gap = random.uniform(0.1, 0.3)
            else: gap = random.uniform(0.05, 0.2)
        else: gap = 0.0
        gap_durations.append(gap)
        
        temp_voice_fn = f"temp_voice_{idx}.mp3"
        try:
            res_api = requests.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{DEFAULT_VOICE_ID}/with-timestamps", 
                json={"text": phrase_text, "model_id": "eleven_multilingual_v2"}, 
                headers={"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"}
            ).json()
            
            if 'audio_base64' not in res_api: continue
            with open(temp_voice_fn, "wb") as f: f.write(base64.b64decode(res_api['audio_base64']))
            
            voice_segment = AudioFileClip(temp_voice_fn)
            seg_dur = voice_segment.duration
            
            sfx_api_prompt = SFX_PROMPT_MAP.get(sfx_trigger)
            temp_sfx_fn = f"temp_sfx_{idx}.mp3"
            
            # --- NEW AUDIO MIXING LOGIC (Offset & Volume control) ---
            if sfx_api_prompt and generate_elevenlabs_sfx(sfx_api_prompt, temp_sfx_fn):
                try:
                    sfx_clip = AudioFileClip(temp_sfx_fn).volumex(0.25)
                    dynamic_sfx_clips.append(sfx_clip)
                    
                    if sfx_clip.duration > (seg_dur + 0.2): 
                        sfx_clip = sfx_clip.subclip(0, seg_dur + 0.2)
                    
                    # Voice starts 0.2s AFTER SFX
                    voice_segment = voice_segment.set_start(0.2)
                    mixed_segment = CompositeAudioClip([sfx_clip.set_start(0), voice_segment]).set_duration(max(sfx_clip.duration, voice_segment.end))
                    seg_dur = mixed_segment.duration
                except: mixed_segment = voice_segment
            else: mixed_segment = voice_segment

            audio_clips.append(mixed_segment)
            
            chars = res_api['alignment']['characters']
            starts = res_api['alignment']['character_start_times_seconds']
            ends = res_api['alignment']['character_end_times_seconds']
            
            curr_w = ""; s_t = None
            for c_idx, char in enumerate(chars):
                if char.strip() == "":
                    if curr_w:
                        # Offset words by 0.2s if SFX shifted the voice track
                        offset = 0.2 if (sfx_api_prompt and os.path.exists(temp_sfx_fn)) else 0.0
                        word_timestamps_master.append({"text": curr_w, "start": s_t + elapsed_time_offset + offset, "end": ends[c_idx-1] + elapsed_time_offset + offset})
                        curr_w = ""; s_t = None
                else:
                    if not curr_w: s_t = starts[c_idx]
                    curr_w += char
            if curr_w:
                offset = 0.2 if (sfx_api_prompt and os.path.exists(temp_sfx_fn)) else 0.0
                word_timestamps_master.append({"text": curr_w, "start": s_t + elapsed_time_offset + offset, "end": ends[-1] + elapsed_time_offset + offset})
                
            elapsed_time_offset += (seg_dur + gap)
        except Exception as e: 
            logger.error(f"🛑 Fatal Sync Exception: {e}")
            return

    spaced_audio_clips = []
    for idx, clip in enumerate(audio_clips):
        spaced_audio_clips.append(clip)
        if gap_durations[idx] > 0: spaced_audio_clips.append(make_silence(gap_durations[idx]))
            
    voice = concatenate_audioclips(spaced_audio_clips)
    voice.write_audiofile("voice.mp3")
    duration = voice.duration

    logger.info("🎬 Hybrid Video Assembly (SVD + Motion Engine)...")
    video_clips = []
    for idx, (full_tag, _) in enumerate(segments):
        mapped_asset = asset_sequence[int((idx / len(segments)) * len(asset_sequence))]
        total_scene_dur = audio_clips[idx].duration + gap_durations[idx] 
        tag_parts = full_tag.upper().split('|')
        intensity_action = tag_parts[1].strip() if len(tag_parts) > 1 else "ORGANIC_DRIFT"
        
        # HYBRID ROUTING: If normal drift and SVD video exists, use SVD. Otherwise, use Motion Engine math.
        if intensity_action == "ORGANIC_DRIFT" and mapped_asset['vid'] and os.path.exists(mapped_asset['vid']):
            c = VideoFileClip(mapped_asset['vid']).resize(height=1920).crop(width=1080, height=1920).without_audio().loop(duration=total_scene_dur).subclip(0, total_scene_dur)
            video_clips.append(c)
        else:
            c = apply_motion(mapped_asset['img'], total_scene_dur, intensity_action, idx)
            if c is None: c = ColorClip(size=(1080, 1920), color=(20, 20, 30)).set_duration(total_scene_dur)
            video_clips.append(c)

    # --- NEW CROSSFADE COMPOSITING LOGIC ---
    transitions = []
    for i, clip in enumerate(video_clips):
        if i > 0: transitions.append(clip.crossfadein(0.5))
        else: transitions.append(clip)
            
    main_v = concatenate_videoclips(transitions, padding=-0.5, method="compose")

    logger.info("📝 Applying Kinetic Typography & Scrubbers...")
    subs = []
    IMPACT_WORDS = ["GOD", "BLOOD", "FIRE", "HEAVEN", "DEATH", "ANGEL", "HOLY", "DEMON", "SWORD", "WRATH", "MIRACLE", "JESUS", "CHRIST", "LORD", "SPIRIT", "TRUTH"]
    
    for i, word_data in enumerate(word_timestamps_master):
        raw_txt = word_data["text"]
        clean_txt = re.sub(r'\[.*?\]', '', raw_txt).strip().upper()
        if not clean_txt: continue 
        
        s = word_data["start"]
        e = word_data["end"]
        next_s = word_timestamps_master[i+1]["start"] if i + 1 < len(word_timestamps_master) else duration
        duration_on_screen = max(0.15, min(e - s, next_s - s))

        is_impact = any(impact in clean_txt for impact in IMPACT_WORDS)
        text_color = '#FFD700' if is_impact else '#FFFFFF'
        base_size = 110 if is_impact else 95
        
        word_clip = (TextClip(clean_txt, font=FONT_FILE, fontsize=base_size, color=text_color, stroke_color='black', stroke_width=6, method='caption', size=(900, None))
                     .set_duration(duration_on_screen).set_start(s).set_position(('center', 1300)))
        
        if is_impact: word_clip = word_clip.resize(lambda t: min(1.0, 0.7 + 8*t))
        else: word_clip = word_clip.resize(lambda t: min(1.0, 0.8 + 5*t))
        subs.append(word_clip)

    source_text = f"EDITORIAL: DAILY GOSPEL / VISUALS: LEONARDO AI"
    source_clip = (TextClip(source_text, font="Impact", fontsize=28, color='white', stroke_color='black', stroke_width=1, method='caption', size=(750, None))
                   .set_duration(duration).set_start(0).set_opacity(0.5).set_position((50, 80)))

    logger.info("🎛️ Rendering Final Video Timeline...")
    try: 
        music = audio_loop(AudioFileClip("bible_bgm.m4a"), duration=duration).volumex(0.12)
        final_audio = CompositeAudioClip([voice, music])
    except: final_audio = voice
        
    final_video = CompositeVideoClip([main_v, source_clip] + subs).set_audio(final_audio).set_duration(duration)
    final_video.write_videofile("biblical_export.mp4", fps=24, codec="libx264", preset="ultrafast", threads=4)

    if os.path.exists("biblical_export.mp4"):
        logger.info("🚀 Uploading to YouTube...")
        try:
            creds_data = json.loads(os.getenv('YOUTUBE_CREDENTIALS'))
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload
            youtube = build("youtube", "v3", credentials=Credentials(**creds_data))
            
            safe_title = re.sub(r'[\[\]<>]', '', f"{data.get('TITLE')} | {data.get('SCRIPTURE')}").strip()
            clean_prose = re.sub(r'\[.*?\]:?\s*', ' ', monologue).strip()
            clean_prose = re.sub(r'\s+', ' ', clean_prose)
            
            fair_use_desc = (
                f"{clean_prose}\n\n"
                f"📖 Content & Media Citations:\n"
                f"- Scripture Data: Official Daily Gospel\n"
                f"- Visual Elements: Managed via Leonardo AI / Historical Recreation\n\n"
                f"⚖️ COPYRIGHT SAFE HARBOR & FAIR USE STATEMENT:\n"
                f"This video contains transformative, commentary, and educational analysis. "
                f"All assets are utilized under Fair Use guidelines for religious review purposes.\n\n"
                f"#dailygospel #faith #shorts #AI"
            )
            
            body = {
                'snippet': {'title': safe_title, 'description': fair_use_desc, 'categoryId': '22', 'tags': ['bible', 'gospel', 'AI']}, 
                'status': {'privacyStatus': 'public'}
            }
            media_file = MediaFileUpload("biblical_export.mp4", chunksize=-1, resumable=True)
            
            resp = execute_youtube_upload_with_backoff(youtube, body, media_file)
            final_video_id = resp if isinstance(resp, str) else resp.get('id', 'UPLOAD_SUCCESS')
            
            sheet.append_row([str(datetime.date.today()), data.get('SCRIPTURE'), safe_title, data.get('VISUAL_SUBJECT'), final_video_id, style.split(' (')[0]])
            push_to_n8n_webhook("biblical_export.mp4", safe_title, fair_use_desc)
            logger.info("✅ Pipeline execution completely finished.")
        except Exception as e:
            upload_err = f"Pipeline upload sequence crashed: {e}"
            logger.error(upload_err)
            send_telegram_alert(upload_err, context="ERROR")

    logger.info("🧹 Sweeping up file descriptors and clearing runner memory...")
    try:
        final_video.close(); main_v.close(); source_clip.close(); voice.close()
        if 'music' in locals(): music.close()
        for c in video_clips: c.close()
        for ac in audio_clips: ac.close()
        for sc in dynamic_sfx_clips: sc.close()
        for s in subs: s.close()
    except Exception as e: logger.warning(f"Non-blocking cleanup alert: {e}")

if __name__ == "__main__":
    produce()
