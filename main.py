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
# --------------------------------

from google import genai
from google.genai import types
from elevenlabs.client import ElevenLabs
from moviepy.config import change_settings
from moviepy.editor import ImageClip, TextClip, CompositeVideoClip, AudioFileClip, CompositeAudioClip
from moviepy.audio.fx.all import audio_loop

# --- 1. SYSTEM CONFIG ---
change_settings({"IMAGEMAGICK_BINARY": "/usr/bin/convert"})

gen_client = genai.Client(
    api_key=os.getenv('GEMINI_API_KEY'), 
    http_options={'api_version': 'v1beta'} 
)
client_11 = ElevenLabs(api_key=os.getenv('ELEVENLABS_API_KEY'))

def scout_bible_story():
    print("📖 Scripting anime bible story using Gemini 2.5 Engine...")
    prompt = f"""
    Today is {datetime.date.today()}. Select a dramatic Bible story. 
    Write a narration of exactly 75 words.
    Provide 4 highly detailed IMAGE PROMPTS in 'Epic Shonen Anime Style'.
    FORMAT: TITLE: [text] SCRIPTURE: [text] MONOLOGUE: [text] 
    PART_A: [text] PROMPT_A: [text]
    PART_B: [text] PROMPT_B: [text]
    PART_C: [text] PROMPT_C: [text]
    PART_D: [text] PROMPT_D: [text]
    """
    
    for attempt in range(3):
        try:
            res = gen_client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
            res_text = res.text
            return {line.split(':', 1)[0].strip(): line.split(':', 1)[1].strip() for line in res_text.split('\n') if ':' in line}
        except Exception as e:
            print(f"⚠️ Attempt {attempt+1} failed: {e}")
            time.sleep(15)
    return None

def produce():
    data = scout_bible_story()
    if not data: return

    # 🎙️ AUDIO: Cinematic Voice (SAxJUlDKRc79XAyeWyMu)
    print("🎙️ Generating Narration...")
    audio_gen = client_11.text_to_speech.convert(
        text=data.get('MONOLOGUE'), 
        voice_id="SAxJUlDKRc79XAyeWyMu", 
        model_id="eleven_multilingual_v2"
    )
    with open("voice.mp3", "wb") as f:
        for chunk in audio_gen: f.write(chunk)
    
    voice = AudioFileClip("voice.mp3")
    duration = voice.duration
    p_dur = duration / 4 

    # 🎨 IMAGE GENERATION: Pollinations AI
    image_files = []
    chars = ['A', 'B', 'C', 'D']
    for char in chars:
        print(f"🎨 Pollinations generating scene_{char}...")
        raw_prompt = data.get(f'PROMPT_{char}', "Epic Anime Scenery")
        clean_prompt = urllib.parse.quote(f"Epic Shonen Anime Style, hand-drawn illustration, cinematic lighting, {raw_prompt}")
        url = f"https://image.pollinations.ai/prompt/{clean_prompt}?width=1080&height=1920&nologo=true&seed={datetime.datetime.now().microsecond}"
        
        try:
            img_res = requests.get(url, timeout=30)
            filename = f"scene_{char}.png"
            with open(filename, 'wb') as f:
                f.write(img_res.content)
            image_files.append(filename)
            time.sleep(2)
        except:
            image_files.append(None)

    # 🎬 VIDEO ASSEMBLY
    clips = []
    for i, img in enumerate(image_files):
        if img:
            clip = ImageClip(img).set_duration(p_dur).set_start(i * p_dur).set_position('center')
            # Ken Burns effect: This was where the error happened
            clip = clip.resize(lambda t: 1 + 0.04 * t) 
            clips.append(clip)

    # ✍️ SUBTITLES
    font_p = "THEBOLDFONT-FREEVERSION.ttf"
    subs = []
    for i, char in enumerate(chars):
        txt = TextClip(data.get(f'PART_{char}', "..."), font=font_p, fontsize=85, 
                       color='yellow' if i%2==0 else 'white', stroke_color='black', stroke_width=2,
                       method='caption', size=(950, None)).set_duration(p_dur).set_start(i*p_dur).set_position(('center', 1450))
        subs.append(txt)

    # 🎛️ AUDIO MIX
    try:
        music = audio_loop(AudioFileClip("bible_bgm.m4a"), duration=duration).volumex(0.12)
        final_audio = CompositeAudioClip([voice, music])
    except:
        final_audio = voice

    # 🚀 RENDER
    final = CompositeVideoClip(clips + subs).set_audio(final_audio).set_duration(duration)
    final.write_videofile("biblical_export.mp4", fps=24, codec="libx264", audio_codec="aac")

    # 🚀 YOUTUBE UPLOAD
    if os.path.exists("biblical_export.mp4"):
        print("🚀 Uploading to YouTube...")
        try:
            creds_json = json.loads(os.getenv('YOUTUBE_CREDENTIALS'))
            from google.oauth2.credentials import Credentials
            creds = Credentials(**creds_json)
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload
            youtube = build("youtube", "v3", credentials=creds)
            body = {'snippet': {'title': f"{data.get('TITLE')} | {data.get('SCRIPTURE')}", 'description': f"{data.get('MONOLOGUE')}\n#bible #anime", 'categoryId': '22'}, 'status': {'privacyStatus': 'public'}}
            youtube.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload("biblical_export.mp4", chunksize=-1, resumable=True)).execute()
            print("✅ SUCCESS!")
        except Exception as e:
            print(f"❌ Upload failed: {e}")

if __name__ == "__main__":
    produce()
