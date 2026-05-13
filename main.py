import os
import json
import datetime
import time
import requests
import base64
import PIL.Image
import gspread
from oauth2client.service_account import ServiceAccountCredentials

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

def get_next_style(sheet):
    print("🎨 Cycling Art Styles...")
    try:
        records = sheet.get_all_records()
        if not records: return ANIME_STYLES[0]
        last_style_name = records[-1].get('Art_Style', '')
        try:
            current_idx = [s.split(' (')[0] for s in ANIME_STYLES].index(last_style_name)
            next_idx = (current_idx + 1) % len(ANIME_STYLES)
        except: next_idx = 0
        return ANIME_STYLES[next_idx]
    except: return ANIME_STYLES[0]

def get_memory():
    print("🧠 Reading Sheet Memory...")
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = json.loads(os.getenv('GOOGLE_SHEETS_JSON'))
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SPREADSHEET_ID).sheet1
        return sheet
    except: return None

def scout_daily_gospel(art_style):
    print(f"📖 Scouting Gospel with {art_style}...")
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
    except: return None

def generate_leonardo_image(prompt, filename):
    print(f"🎨 Rendering: {filename}...")
    url = "https://cloud.leonardo.ai/api/rest/v1/generations"
    headers = {"accept": "application/json", "content-type": "application/json", "authorization": f"Bearer {LEO_API_KEY}"}
    
    # 🚨 SWITCHED TO VISION XL FOR STABILITY
    payload = {
        "height": 1024, "width": 576, 
        "prompt": f"{prompt}, high quality anime art style, vibrant colors", 
        "modelId": "5c232a9e-9b42-42c4-ad6c-60d95074f07e", 
        "alchemy": True,
        "presetStyle": "ANIME"
    }
    try:
        response = requests.post(url, json=payload, headers=headers).json()
        if 'sdGenerationJob' not in response:
            print(f"❌ API Error Response: {response}")
            return None
            
        gen_id = response['sdGenerationJob']['generationId']
        for _ in range(15):
            time.sleep(7)
            status = requests.get(f"https://cloud.leonardo.ai/api/rest/v1/generations/{gen_id}", headers=headers).json()
            images = status.get('generations_by_pk', {}).get('generated_images', [])
            if images:
                with open(filename, 'wb') as f: f.write(requests.get(images[0]['url']).content)
                print(f"✅ Saved {filename}")
                return images[0]['id']
    except Exception as e: print(f"❌ Image Error: {e}")
    return None

def animate_with_leonardo(image_id, filename):
    print(f"🎥 Animating Frame {image_id}...")
    url = "https://cloud.leonardo.ai/api/rest/v1/generations/motion-svd"
    headers = {"accept": "application/json", "content-type": "application/json", "authorization": f"Bearer {LEO_API_KEY}"}
    try:
        res = requests.post(url, json={"imageId": image_id, "motionStrength": 4}, headers=headers).json()
        if 'sdGenerationJob' not in res: return None
        gen_id = res['sdGenerationJob']['generationId']
        for _ in range(25):
            time.sleep(10)
            status = requests.get(f"https://cloud.leonardo.ai/api/rest/v1/generations/{gen_id}", headers=headers).json()
            images = status.get('generations_by_pk', {}).get('generated_images', [])
            if images and images[0].get('motionMP4URL'):
                with open(filename, "wb") as f: f.write(requests.get(images[0]['motionMP4URL']).content)
                return filename
    except: return None

def produce():
    sheet = get_memory()
    if not sheet: return
    style = get_next_style(sheet)
    data = scout_daily_gospel(style)
    if not data: return

    # 🎬 VIDEO PIPELINE FIRST (To prevent wasting Audio credits if images fail)
    print("⚙️ Checking Image API Health...")
    duration_approx = 35.0
    seg_dur = duration_approx / 4 
    video_clips = []
    
    images_captured = 0
    for char in ['A', 'B', 'C', 'D']:
        img_fn, vid_fn = f"scene_{char}.png", f"scene_{char}.mp4"
        img_id = generate_leonardo_image(data.get(f'IMAGE_{char}'), img_fn)
        
        if img_id:
            images_captured += 1
            animated = animate_with_leonardo(img_id, vid_fn)
            if animated and os.path.exists(animated):
                video_clips.append(VideoFileClip(animated).resize(height=1920).crop(width=1080, height=1920).without_audio().loop(duration=seg_dur).subclip(0, seg_dur))
            else:
                video_clips.append(ImageClip(img_fn).set_duration(seg_dur).resize(height=1920).crop(width=1080, height=1920).resize(lambda t: 1 + 0.03 * t))
        else:
            print(f"⚠️ Scene {char} failed.")

    # 🚨 KILL SWITCH: If 0 images were generated, stop the script.
    if images_captured == 0:
        print("❌ CRITICAL: No images were generated. Check Leonardo credits/API status. Stopping production.")
        return

    # 🎙️ AUDIO GENERATION (Only happens if images are actually there)
    print("🎙️ Images Secured. Generating Voice...")
    full_text = f"{data.get('HOOK')} {data.get('VERBATIM_VERSE')} {data.get('CLIFFHANGER')}"
    try:
        res_api = requests.post("https://api.elevenlabs.io/v1/text-to-speech/SAxJUlDKRc79XAyeWyMu/with-timestamps", 
                                json={"text": full_text, "model_id": "eleven_multilingual_v2"}, 
                                headers={"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"}).json()
        with open("voice.mp3", "wb") as f: f.write(base64.b64decode(res_api['audio_base64']))
        voice = AudioFileClip("voice.mp3")
        duration = voice.duration
    except: return

    # 🚀 EXPORT
    final_video = concatenate_videoclips(video_clips, method="compose").set_audio(voice).set_duration(duration)
    final_video.write_videofile("biblical_export.mp4", fps=24, codec="libx264", preset="ultrafast")

    if os.path.exists("biblical_export.mp4"):
        try:
            creds_data = json.loads(os.getenv('YOUTUBE_CREDENTIALS'))
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload
            youtube = build("youtube", "v3", credentials=Credentials(**creds_data))
            body = {'snippet': {'title': f"{data.get('TITLE')} | {data.get('SCRIPTURE')}", 'description': data.get('VERBATIM_VERSE'), 'categoryId': '22'}, 'status': {'privacyStatus': 'public'}}
            youtube.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload("biblical_export.mp4", chunksize=-1, resumable=True)).execute()
            sheet.append_row([str(datetime.date.today()), data.get('SCRIPTURE'), data.get('TITLE'), data.get('VISUAL_SUBJECT'), response.get('id'), style.split(' (')[0]])
        except Exception as e: print(f"❌ Upload Failed: {e}")

if __name__ == "__main__":
    produce()
