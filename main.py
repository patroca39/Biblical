import os
import json
import datetime
import time
import requests
import urllib.parse
import PIL.Image

# --- PILLOW COMPATIBILITY FIX ---
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

from google import genai
from google.genai import types
from elevenlabs.client import ElevenLabs
from moviepy.config import change_settings
from moviepy.editor import ImageClip, TextClip, CompositeVideoClip, AudioFileClip, CompositeAudioClip
from moviepy.audio.fx.all import audio_loop

# --- 1. SYSTEM CONFIG ---
change_settings({"IMAGEMAGICK_BINARY": "/usr/bin/convert"})

gen_client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'), http_options={'api_version': 'v1beta'})
client_11 = ElevenLabs(api_key=os.getenv('ELEVENLABS_API_KEY'))
LEO_API_KEY = os.getenv('LEONARDO_API_KEY')

def scout_bible_story():
    print("📖 Scripting anime bible story...")
    prompt = f"Today is {datetime.date.today()}. Select a dramatic Bible story. Write a narration of exactly 75 words. Provide 4 IMAGE PROMPTS in 'Epic Shonen Anime Style'. FORMAT: TITLE: [text] SCRIPTURE: [text] MONOLOGUE: [text] PART_A: [text] PROMPT_A: [text] PART_B: [text] PROMPT_B: [text] PART_C: [text] PROMPT_C: [text] PART_D: [text] PROMPT_D: [text]"
    try:
        res = gen_client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
        return {line.split(':', 1)[0].strip(): line.split(':', 1)[1].strip() for line in res.text.split('\n') if ':' in line}
    except Exception as e:
        print(f"⚠️ Scripting failed: {e}")
        return None

def generate_leonardo_image(prompt, filename):
    print(f"🎨 Requesting Leonardo render: {prompt[:60]}...")
    url = "https://cloud.leonardo.ai/api/rest/v1/generations"
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "authorization": f"Bearer {LEO_API_KEY}"
    }
    
    payload = {
        "height": 1024,
        "width": 576,
        "modelId": "e5a30e3b-ce09-4f95-bc3a-8d0a2046639c", # Leonardo Vision XL
        "prompt": f"Shonen Anime Style, cinematic lighting, high resolution, {prompt}",
        "num_images": 1,
        "alchemy": True,
        "presetStyle": "ANIME",
        "photoReal": False
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        res_json = response.json()
        
        if 'sdGenerationJob' not in res_json:
            print(f"❌ API Error (Check balance/key): {res_json}")
            return False
            
        gen_id = res_json['sdGenerationJob']['generationId']
        
        # Poll for completion (Wait up to 90 seconds)
        for attempt in range(15):
            time.sleep(6)
            status_res = requests.get(f"https://cloud.leonardo.ai/api/rest/v1/generations/{gen_id}", headers=headers).json()
            images = status_res.get('generations_by_pk', {}).get('generated_images', [])
            
            if images:
                img_data = requests.get(images[0]['url']).content
                with open(filename, 'wb') as f:
                    f.write(img_data)
                print(f"✅ Scene saved: {filename}")
                return True
            print(f"  ...rendering ({attempt+1}/15)")
    except Exception as e:
        print(f"❌ Leonardo function failed: {e}")
    return False

def produce():
    data = scout_bible_story()
    if not data: return

    # 🎙️ AUDIO
    print("🎙️ Generating Narration...")
    duration = 30.0
    voice = None
    try:
        audio_gen = client_11.text_to_speech.convert(
            text=data.get('MONOLOGUE'), 
            voice_id="SAxJUlDKRc79XAyeWyMu", 
            model_id="eleven_multilingual_v2"
        )
        with open("voice.mp3", "wb") as f:
            for chunk in audio_gen: f.write(chunk)
        voice = AudioFileClip("voice.mp3")
        duration = voice.duration
    except Exception as e:
        print(f"⚠️ Voice failed: {e}")

    p_dur = duration / 4 

    # 🎨 IMAGES
    image_files = []
    for char in ['A', 'B', 'C', 'D']:
        fname = f"scene_{char}.png"
        if not generate_leonardo_image(data.get(f'PROMPT_{char}'), fname):
            print(f"⚠️ Using fallback for scene {char}")
            PIL.Image.new('RGB', (1080, 1920), color=(15, 20, 35)).save(fname)
        image_files.append(fname)

    # 🎬 ASSEMBLY
    print(f"🎬 Compiling {duration:.1f}s anime broadcast...")
    final_clips = []
    for i, img in enumerate(image_files):
        # Background layer
        bg = (ImageClip(img)
              .set_duration(p_dur)
              .set_start(i * p_dur)
              .resize(height=1920)
              .set_position('center')
              .resize(lambda t: 1 + 0.04 * t)) # Ken Burns effect
        final_clips.append(bg)
        
        # Subtitle layer
        raw_text = data.get(f'PART_{["A","B","C","D"][i]}', "...")
        txt = (TextClip(raw_text[:110], font="THEBOLDFONT-FREEVERSION.ttf", fontsize=75, 
                        color='yellow' if i % 2 == 0 else 'white', 
                        stroke_color='black', stroke_width=2,
                        method='caption', size=(850, 450))
               .set_duration(p_dur)
               .set_start(i * p_dur)
               .set_position(('center', 1350)))
        final_clips.append(txt)

    # 🎛️ MIX
    try:
        music = audio_loop(AudioFileClip("bible_bgm.m4a"), duration=duration).volumex(0.12)
        final_audio = CompositeAudioClip([voice, music]) if voice else music
    except:
        final_audio = voice

    # 🚀 RENDER
    final_video = CompositeVideoClip(final_clips, size=(1080, 1920))
    if final_audio:
        final_video = final_video.set_audio(final_audio)
    
    final_video.set_duration(duration).write_videofile("biblical_export.mp4", fps=24, codec="libx264", audio_codec="aac")

    # 🚀 YOUTUBE
    if os.path.exists("biblical_export.mp4"):
        print("🚀 Uploading to YouTube...")
        try:
            creds_json = json.loads(os.getenv('YOUTUBE_CREDENTIALS'))
            from google.oauth2.credentials import Credentials
            creds = Credentials(**creds_json)
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload
            youtube = build("youtube", "v3", credentials=creds)
            body = {'snippet': {'title': f"{data.get('TITLE')} | {data.get('SCRIPTURE')}", 'description': f"{data.get('MONOLOGUE')}\n\n#bible #anime", 'categoryId': '22'}, 'status': {'privacyStatus': 'public'}}
            youtube.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload("biblical_export.mp4", chunksize=-1, resumable=True)).execute()
            print("✅ SUCCESS!")
        except Exception as e:
            print(f"❌ YouTube upload failed: {e}")

if __name__ == "__main__":
    produce()
