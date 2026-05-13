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

def get_memory():
    """Reads the last 10 visual subjects from Google Sheets to avoid repetition."""
    print("🧠 Accessing Channel Memory...")
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = json.loads(os.getenv('GOOGLE_SHEETS_JSON'))
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SPREADSHEET_ID).sheet1
        records = sheet.get_all_records()
        last_visuals = [r['Visual_Subject'] for r in records[-10:]] if records else []
        return last_visuals, sheet
    except Exception as e:
        print(f"⚠️ Memory Access Failed: {e}")
        return [], None

def scout_daily_gospel(past_visuals):
    print("📖 Scouting Gospel with Verbatim Logic & Memory...")
    banned_list = ", ".join(past_visuals) if past_visuals else "None"
    
    prompt = f"""
    Today is {datetime.date.today()}. 
    1. Search for today's official Daily Gospel reading.
    2. TITLE: Create a "Curiosity Gap" title (e.g., "The Mystery of the Seed").
    3. SCRIPTURE: Provide the Book, Chapter, and Verse.
    4. MONOLOGUE: Provide the VERBATIM text of the most powerful 60-80 words of that Gospel reading. DO NOT CHANGE A SINGLE WORD OF THE BIBLE VERSE.
    5. HOOK: A 5-word dramatic intro BEFORE the verse starts.
    6. CLIFFHANGER: A bright, hopeful question AFTER the verse ends.
    7. VISUAL_SUBJECT: A 3-word description of the primary visual style (e.g., "Fisherman at Sea").

    CRITICAL MEMORY RULE:
    You have recently used these visual subjects: [{banned_list}]. 
    DO NOT repeat these. Create a unique 1st-century visual style.

    FORMAT (Single lines):
    TITLE: [text]
    SCRIPTURE: [text]
    HOOK: [text]
    VERBATIM_VERSE: [text]
    CLIFFHANGER: [text]
    VISUAL_SUBJECT: [text]
    IMAGE_A: [Atmospheric environment, 1st-century, 8k...]
    IMAGE_B: [Macro detail, 1st-century, 8k...]
    IMAGE_C: [Character emotion, 1st-century, 8k...]
    IMAGE_D: [Epic wide shot, 1st-century, 8k...]
    """
    for attempt in range(4):
        try:
            res = gen_client.models.generate_content(
                model='gemini-2.5-flash', contents=prompt,
                config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())])
            )
            cleaned = res.text.replace('**', '')
            return {line.split(':', 1)[0].strip(): line.split(':', 1)[1].strip() for line in cleaned.split('\n') if ':' in line}
        except: time.sleep(10)
    return None

def generate_leonardo_image(prompt, filename):
    print(f"🎨 Rendering: {filename}...")
    url = "https://cloud.leonardo.ai/api/rest/v1/generations"
    headers = {"accept": "application/json", "content-type": "application/json", "authorization": f"Bearer {LEO_API_KEY}"}
    payload = {"height": 1024, "width": 576, "prompt": f"Hyper-realistic cinematic photography, 1st-century biblical setting, 8k, majestic lighting. {prompt}", "modelId": "aa77f04e-3eec-4034-9c07-d0f619684628", "alchemy": True}
    try:
        response = requests.post(url, json=payload, headers=headers).json()
        gen_id = response['sdGenerationJob']['generationId']
        for _ in range(20):
            time.sleep(4)
            status = requests.get(f"https://cloud.leonardo.ai/api/rest/v1/generations/{gen_id}", headers=headers).json()
            images = status.get('generations_by_pk', {}).get('generated_images', [])
            if images:
                image_id = images[0]['id'] 
                with open(filename, 'wb') as f: f.write(requests.get(images[0]['url']).content)
                return image_id 
    except: pass
    return None

def animate_with_leonardo(image_id, filename):
    print(f"🎥 Animating ID {image_id}...")
    url = "https://cloud.leonardo.ai/api/rest/v1/generations/motion-svd"
    headers = {"accept": "application/json", "content-type": "application/json", "authorization": f"Bearer {LEO_API_KEY}"}
    payload = {"imageId": image_id, "motionStrength": 5}
    try:
        res = requests.post(url, json=payload, headers=headers).json()
        if 'sdGenerationJob' not in res: return None
        gen_id = res['sdGenerationJob']['generationId']
        for _ in range(30): 
            time.sleep(9)
            status = requests.get(f"https://cloud.leonardo.ai/api/rest/v1/generations/{gen_id}", headers=headers).json()
            images = status.get('generations_by_pk', {}).get('generated_images', [])
            if images and images[0].get('motionMP4URL'):
                with open(filename, "wb") as f: f.write(requests.get(images[0]['motionMP4URL']).content)
                return filename
    except: pass
    return None

def produce():
    past_visuals, sheet = get_memory()
    data = scout_daily_gospel(past_visuals)
    if not data: return

    full_text = f"{data.get('HOOK')} {data.get('VERBATIM_VERSE')} {data.get('CLIFFHANGER')}"

    # 🎙️ AUDIO
    print("🎙️ Generating Verbatim Audio...")
    duration = 30.0
    voice, alignment_data = None, None
    try:
        res_api = requests.post("https://api.elevenlabs.io/v1/text-to-speech/SAxJUlDKRc79XAyeWyMu/with-timestamps", 
                                json={"text": full_text, "model_id": "eleven_multilingual_v2"}, 
                                headers={"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"}).json()
        with open("voice.mp3", "wb") as f: f.write(base64.b64decode(res_api['audio_base64']))
        alignment_data = res_api.get('alignment', {})
        voice = AudioFileClip("voice.mp3")
        duration = voice.duration
    except: return

    # 🎬 VIDEO PIPELINE
    seg_dur = duration / 4 
    video_clips = []
    for char in ['A', 'B', 'C', 'D']:
        img_name, vid_name = f"scene_{char}.png", f"scene_{char}.mp4"
        image_id = generate_leonardo_image(data.get(f'IMAGE_{char}'), img_name)
        animated_path = animate_with_leonardo(image_id, vid_name) if image_id else None
        try:
            if animated_path:
                clip = VideoFileClip(animated_path).resize(height=1920).crop(width=1080, height=1920).without_audio().loop(duration=seg_dur).subclip(0, seg_dur)
            elif image_id:
                clip = ImageClip(img_name).set_duration(seg_dur).resize(height=1920).crop(width=1080, height=1920).resize(lambda t: 1 + 0.03 * t)
            else:
                clip = ColorClip(size=(1080, 1920), color=(20, 20, 30)).set_duration(seg_dur)
            video_clips.append(clip)
        except: video_clips.append(ColorClip(size=(1080, 1920), color=(20, 20, 30)).set_duration(seg_dur))

    # 📝 SUBS & EXPORT
    main_v = concatenate_videoclips(video_clips, method="compose")
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
            subs.append(TextClip(txt_str, font="THEBOLDFONT-FREEVERSION.ttf", fontsize=100, color='yellow', stroke_color='black', stroke_width=5, method='caption', size=(950, None)).set_duration(e-s).set_start(s).set_position(('center', 1300)).resize(lambda t: min(1.0, 0.8 + 5*t)))

    final_video = CompositeVideoClip([main_v] + subs).set_audio(voice).set_duration(duration)
    final_video.write_videofile("biblical_export.mp4", fps=24, codec="libx264", preset="ultrafast")

    # 🚀 UPLOAD & LOG TO MEMORY
    if os.path.exists("biblical_export.mp4"):
        try:
            # Upload to YouTube (Mapping logic remains same)
            creds_data = json.loads(os.getenv('YOUTUBE_CREDENTIALS'))
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload
            youtube = build("youtube", "v3", credentials=Credentials(**creds_data))
            title = f"{data.get('TITLE')} | {data.get('SCRIPTURE')}"
            body = {'snippet': {'title': title, 'description': data.get('VERBATIM_VERSE'), 'categoryId': '22'}, 'status': {'privacyStatus': 'public'}}
            response = youtube.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload("biblical_export.mp4", chunksize=-1, resumable=True)).execute()
            
            # Log to Google Sheets Memory
            if sheet:
                sheet.append_row([str(datetime.date.today()), data.get('SCRIPTURE'), data.get('TITLE'), data.get('VISUAL_SUBJECT'), response.get('id')])
                print("✅ Video Uploaded and Logged to Memory!")
        except Exception as e: print(f"❌ Upload/Log failed: {e}")

if __name__ == "__main__":
    produce()
