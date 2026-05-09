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

gen_client = genai.Client(
    api_key=os.getenv('GEMINI_API_KEY'), 
    http_options={'api_version': 'v1beta'} 
)
client_11 = ElevenLabs(api_key=os.getenv('ELEVENLABS_API_KEY'))

def scout_bible_story():
    print("📖 Scripting anime bible story...")
    prompt = f"""
    Today is {datetime.date.today()}. Select a dramatic Bible story. 
    Write a narration of exactly 75 words.
    Provide 4 IMAGE PROMPTS in 'Epic Shonen Anime Style'.
    FORMAT: TITLE: [text] SCRIPTURE: [text] MONOLOGUE: [text] 
    PART_A: [text] PROMPT_A: [text]
    PART_B: [text] PROMPT_B: [text]
    PART_C: [text] PROMPT_C: [text]
    PART_D: [text] PROMPT_D: [text]
    """
    try:
        res = gen_client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
        return {line.split(':', 1)[0].strip(): line.split(':', 1)[1].strip() for line in res.text.split('\n') if ':' in line}
    except Exception as e:
        print(f"⚠️ Scripting failed: {e}")
        return None

def produce():
    data = scout_bible_story()
    if not data: return

    # 🎙️ AUDIO GENERATION
    print("🎙️ Generating Narration...")
    duration = 30.0 # Standard Default
    voice = None
    
    try:
        audio_gen = client_11.text_to_speech.convert(
            text=data.get('MONOLOGUE'), 
            voice_id="SAxJUlDKRc79XAyeWyMu", 
            model_id="eleven_multilingual_v2"
        )
        with open("voice.mp3", "wb") as f:
            for chunk in audio_gen: f.write(chunk)
        
        voice_clip = AudioFileClip("voice.mp3")
        if voice_clip.duration > 5:
            voice = voice_clip
            duration = voice.duration
            print(f"✅ Voice generated. Duration: {duration:.1f}s")
    except Exception as e:
        print(f"⚠️ Voice failed ({e}). Using 30s silent-anchor mode.")

    # CALCULATE TIMING
    p_dur = duration / 4 

    # 🎨 IMAGE GENERATION (Pollinations Flux)
    image_files = []
    chars = ['A', 'B', 'C', 'D']
    for char in chars:
        print(f"🎨 Generating Scene {char}...")
        raw_prompt = data.get(f'PROMPT_{char}', "Epic Anime Scenery")
        # Added 'Flux' model to the URL for much higher visual quality
        clean_prompt = urllib.parse.quote(f"Epic Shonen Anime Style, {raw_prompt}")
        url = f"https://pollinations.ai/p/{clean_prompt}?width=1080&height=1920&seed={datetime.datetime.now().microsecond}&model=flux"
        
        filename = f"scene_{char}.png"
        try:
            img_res = requests.get(url, timeout=35)
            if img_res.status_code == 200 and len(img_res.content) > 20000:
                with open(filename, 'wb') as f:
                    f.write(img_res.content)
                image_files.append(filename)
            else:
                raise ValueError("Small/Bad file")
        except:
            print(f"⚠️ Fallback background for {char}")
            PIL.Image.new('RGB', (1080, 1920), color=(15, 20, 35)).save(filename)
            image_files.append(filename)
        time.sleep(2)

    # 🎬 VIDEO ASSEMBLY
    print(f"🎬 Creating {duration:.1f}s sequence...")
    final_clips = []
    
    for i, img in enumerate(image_files):
        try:
            # 1. Background (Layer 0)
            bg = (ImageClip(img)
                  .set_duration(p_dur)
                  .set_start(i * p_dur)
                  .resize(height=1920)
                  .set_position('center')
                  .resize(lambda t: 1 + 0.04 * t)) # Ken Burns
            final_clips.append(bg)
            
            # 2. Subtitle (Layer 1 - Added after BG to stay on top)
            raw_text = data.get(f'PART_{chars[i]}', "...")
            safe_text = (raw_text[:110] + '...') if len(raw_text) > 110 else raw_text
            
            txt = (TextClip(safe_text, font="THEBOLDFONT-FREEVERSION.ttf", fontsize=75, 
                            color='yellow' if i % 2 == 0 else 'white', 
                            stroke_color='black', stroke_width=2,
                            method='caption', size=(850, 450))
                   .set_duration(p_dur)
                   .set_start(i * p_dur)
                   .set_position(('center', 1350)))
            final_clips.append(txt)
        except Exception as e:
            print(f"⚠️ Frame {i} assembly error: {e}")

    # 🎛️ AUDIO MIX
    try:
        music = audio_loop(AudioFileClip("bible_bgm.m4a"), duration=duration).volumex(0.12)
        final_audio = CompositeAudioClip([voice, music]) if voice else music
    except:
        final_audio = voice if voice else None

    # 🚀 RENDER
    final_video = CompositeVideoClip(final_clips, size=(1080, 1920))
    if final_audio:
        final_video = final_video.set_audio(final_audio)
    
    # Force duration one last time to prevent the "short cycling" bug
    final_video.set_duration(duration).write_videofile("biblical_export.mp4", fps=24, codec="libx264", audio_codec="aac")

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
            body = {'snippet': {'title': f"{data.get('TITLE')} | {data.get('SCRIPTURE')}", 'description': f"{data.get('MONOLOGUE')}\n\n#bible #anime", 'categoryId': '22'}, 'status': {'privacyStatus': 'public'}}
            youtube.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload("biblical_export.mp4", chunksize=-1, resumable=True)).execute()
            print("✅ SUCCESS!")
        except Exception as e:
            print(f"❌ Upload failed: {e}")

if __name__ == "__main__":
    produce()
