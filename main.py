import os
import json
import datetime
import time
import requests
import base64
import PIL.Image
import jwt # 🚨 Required for Kling API

if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

from google import genai
from google.genai import types 
from moviepy.config import change_settings
from moviepy.editor import ImageClip, TextClip, CompositeVideoClip, AudioFileClip, CompositeAudioClip, VideoFileClip, ColorClip
from moviepy.audio.fx.all import audio_loop

# --- 1. SYSTEM CONFIG ---
change_settings({"IMAGEMAGICK_BINARY": "/usr/bin/convert"})

gen_client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'), http_options={'api_version': 'v1beta'})
ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY')
LEO_API_KEY = os.getenv('LEONARDO_API_KEY')

# 🚨 KLING KEYS
KLING_AK = os.getenv('KLING_AK')
KLING_SK = os.getenv('KLING_SK')

def get_kling_token():
    headers = {"alg": "HS256", "typ": "JWT"}
    payload = {"iss": KLING_AK, "exp": int(time.time()) + 1800, "nbf": int(time.time()) - 5}
    return jwt.encode(payload, KLING_SK, headers=headers)

def scout_daily_gospel():
    print("📖 Scouting the Gospel & Generating Kling Prompts...")
    prompt = f"""
    Today is {datetime.date.today()}. Find the official Daily Gospel reading for today's date.
    
    Write a 75-word narration.
    
    1. Write a KLING_PROMPT: Describe a continuous, 5-second cinematic moving background loop suitable for this reading (e.g., "Golden rays of light piercing through moving storm clouds, cinematic, 8k" or "A sweeping drone shot of an ancient middle eastern desert").
    2. Write a CHARACTER_DEF (max 15 words) describing the main character.
    3. Provide 4 highly detailed IMAGE PROMPTS (A, B, C, D) including the CHARACTER_DEF in each.

    FORMAT: 
    TITLE: [Daily Gospel]
    SCRIPTURE: [Book Chapter:Verse] 
    MONOLOGUE: [text] 
    KLING_PROMPT: [Describe moving background, no text]
    CHARACTER_DEF: [facial details, clothing]
    PART_A: [text] 
    PROMPT_A: [Include CHARACTER_DEF]
    PART_B: [text] 
    PROMPT_B: [Include CHARACTER_DEF]
    PART_C: [text] 
    PROMPT_C: [Include CHARACTER_DEF]
    PART_D: [text] 
    PROMPT_D: [Include CHARACTER_DEF]
    """
    for attempt in range(4):
        try:
            res = gen_client.models.generate_content(
                model='gemini-2.5-flash', contents=prompt,
                config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())])
            )
            cleaned = res.text.replace('**', '')
            return {line.split(':', 1)[0].strip(): line.split(':', 1)[1].strip() for line in cleaned.split('\n') if ':' in line}
        except Exception as e:
            if "503" in str(e) or "429" in str(e): time.sleep(30)
            else: break
    return None

def generate_kling_video(prompt, filename):
    print(f"🎥 Generating Kling Background: {prompt[:50]}...")
    url = "https://open.klingai.com/v1/videos/text2video"
    token = get_kling_token()
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    payload = {"model": "kling-v1", "prompt": f"Masterpiece, 8k. {prompt}", "duration": "5", "aspect_ratio": "9:16"}
    try:
        res = requests.post(url, json=payload, headers=headers).json()
        if res.get('code') != 0: return None
        task_id = res['data']['task_id']
        print(f"⏳ Kling Task started. Rendering...")
        for _ in range(30):
            time.sleep(10)
            status_res = requests.get(f"https://open.klingai.com/v1/videos/text2video/{task_id}", headers=headers).json()
            if status_res['data']['task_status'] == 'succeed':
                with open(filename, "wb") as f: f.write(requests.get(status_res['data']['task_result']['videos'][0]['url']).content)
                print("✅ Kling Background Saved!")
                return filename
            elif status_res['data']['task_status'] == 'failed': return None
    except Exception as e: print(f"⚠️ Kling Error: {e}")
    return None

def generate_leonardo_image(prompt, filename):
    print(f"🎨 Leonardo rendering: {filename}...")
    url = "https://cloud.leonardo.ai/api/rest/v1/generations"
    headers = {"accept": "application/json", "content-type": "application/json", "authorization": f"Bearer {LEO_API_KEY}"}
    payload = {
        "height": 768, "width": 768, 
        "prompt": f"Hyper-realistic cinematic photography, shot on 35mm lens, 8k resolution. {prompt}",
        "num_images": 1, "modelId": "aa77f04e-3eec-4034-9c07-d0f619684628", "alchemy": True
    }
    try:
        response = requests.post(url, json=payload, headers=headers).json()
        gen_id = response['sdGenerationJob']['generationId']
        for _ in range(20):
            time.sleep(3)
            status = requests.get(f"https://cloud.leonardo.ai/api/rest/v1/generations/{gen_id}", headers=headers).json()
            images = status.get('generations_by_pk', {}).get('generated_images', [])
            if images:
                with open(filename, 'wb') as f: f.write(requests.get(images[0]['url']).content)
                return True
    except Exception as e: print(f"❌ Leonardo error: {e}")
    return False

def produce():
    data = scout_daily_gospel()
    if not data: return

    # 1. GENERATE KLING BACKGROUND
    bg_path = generate_kling_video(data.get('KLING_PROMPT', 'Glowing heavenly clouds'), "kling_bg.mp4")
    
    # 2. GENERATE AUDIO
    print("🎙️ Generating Narration & Timestamps...")
    duration = 30.0
    voice, alignment_data = None, None
    for attempt in range(3):
        try:
            res_api = requests.post(
                "https://api.elevenlabs.io/v1/text-to-speech/SAxJUlDKRc79XAyeWyMu/with-timestamps", 
                json={"text": data.get('MONOLOGUE'), "model_id": "eleven_multilingual_v2"}, 
                headers={"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"}
            ).json()
            if "audio_base64" in res_api:
                with open("voice.mp3", "wb") as f: f.write(base64.b64decode(res_api['audio_base64']))
                alignment_data = res_api.get('alignment', {})
                if os.path.exists("voice.mp3"):
                    voice = AudioFileClip("voice.mp3")
                    duration = voice.duration
                    break
        except Exception as e: time.sleep(3)

    # 3. GENERATE THE 4 LEONARDO SCENES
    image_files = []
    for char in ['A', 'B', 'C', 'D']:
        fname = f"scene_{char}.png"
        if not generate_leonardo_image(data.get(f'PROMPT_{char}'), fname):
            PIL.Image.new('RGB', (768, 768), color=(20, 20, 30)).save(fname)
        image_files.append(fname)

    # 4. VIDEO ASSEMBLY
    print(f"🎬 Compiling Hybrid Video...")
    p_dur = duration / 4 
    
    if bg_path and os.path.exists(bg_path):
        main_v = VideoFileClip(bg_path).resize(height=1920).crop(width=1080, height=1920).without_audio().loop(duration=duration)
    else:
        main_v = ColorClip(size=(1080, 1920), color=(10, 15, 20)).set_duration(duration)

    final_clips = [main_v]
    
    # Create the drop shadow logic once
    shadow = ColorClip(size=(740, 740), color=(0,0,0)).set_opacity(0.5).set_duration(duration).set_position(('center', 245))
    final_clips.append(shadow)

    # Overlay your 4 original scenes sequentially into the hybrid box
    for i, img in enumerate(image_files):
        try:
            pic = (ImageClip(img).set_duration(p_dur).set_start(i * p_dur)
                   .resize(width=720).margin(8, color=(255, 255, 0))
                   .set_position(('center', 250)))
            final_clips.append(pic)
        except Exception as e: pass

    # 5. SUBTITLES
    subs = []
    font_p = "THEBOLDFONT-FREEVERSION.ttf"
    if alignment_data and 'characters' in alignment_data:
        chars = alignment_data['characters']; starts = alignment_data['character_start_times_seconds']; ends = alignment_data['character_end_times_seconds']
        words, current_word, start_time = [], "", None
        for idx, char in enumerate(chars):
            if char.strip() == "": 
                if current_word: words.append({"text": current_word, "start": start_time, "end": ends[idx-1]}); current_word, start_time = "", None
            else:
                if current_word == "": start_time = starts[idx]
                current_word += char
        if current_word: words.append({"text": current_word, "start": start_time, "end": ends[-1]})

        for j in range(0, len(words), 2):
            chunk = words[j:j+2]; txt_str = " ".join([w["text"] for w in chunk]).upper()
            s = chunk[0]["start"]; e = words[j+2]["start"] if j+2 < len(words) else duration
            subs.append(TextClip(txt_str, font=font_p, fontsize=100, color='yellow', stroke_color='black', stroke_width=4, method='caption', size=(950, None)).set_duration(e-s).set_start(s).set_position(('center', 1300)).resize(lambda t: min(1.0, 0.8 + 5*t)))

    # 6. AUDIO MIX & EXPORT
    try: music = audio_loop(AudioFileClip("bible_bgm.m4a"), duration=duration).volumex(0.12); final_audio = CompositeAudioClip([voice, music]) if voice else music
    except: final_audio = voice

    final_video = CompositeVideoClip(final_clips + subs, size=(1080, 1920)).set_audio(final_audio).set_duration(duration)
    final_video.write_videofile("biblical_export.mp4", fps=24, codec="libx264", preset="ultrafast", threads=4)

    # 7. UPLOAD
    if os.path.exists("biblical_export.mp4"):
        print("🚀 Starting YouTube upload...")
        try:
            creds_json = json.loads(os.getenv('YOUTUBE_CREDENTIALS'))
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload
            youtube = build("youtube", "v3", credentials=Credentials(**creds_json))
            body = {'snippet': {'title': f"{data.get('TITLE')} | {data.get('SCRIPTURE')}", 'description': f"{data.get('MONOLOGUE')}\n\n#dailygospel #biblestories", 'categoryId': '22'}, 'status': {'privacyStatus': 'public'}}
            youtube.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload("biblical_export.mp4", chunksize=-1, resumable=True)).execute()
            print("✅ SUCCESS!")
        except Exception as e: print(f"❌ YouTube error: {e}")

if __name__ == "__main__":
    produce()
