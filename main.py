import os
import json
import datetime
import time
import requests
import PIL.Image

# --- PILLOW COMPATIBILITY FIX ---
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

from google import genai
from elevenlabs.client import ElevenLabs
from moviepy.config import change_settings
from moviepy.editor import ImageClip, TextClip, CompositeVideoClip, AudioFileClip, CompositeAudioClip
from moviepy.audio.fx.all import audio_loop

# --- 1. SYSTEM CONFIG ---
change_settings({"IMAGEMAGICK_BINARY": "/usr/bin/convert"})

# Initialize Clients
gen_client = genai.Client(
    api_key=os.getenv('GEMINI_API_KEY'), 
    http_options={'api_version': 'v1beta'} 
)
client_11 = ElevenLabs(api_key=os.getenv('ELEVENLABS_API_KEY'))
LEO_API_KEY = os.getenv('LEONARDO_API_KEY')

def scout_bible_story():
    print("📖 Scripting classical bible story...")
    # 🚨 FIX: Classical Style + Character Lock + Strict Verbatim Subtitle Rule
    prompt = f"""
    Today is {datetime.date.today()}. Select a dramatic Bible story. 
    Write a narration of exactly 75 words.
    First, write a CHARACTER_DEF (max 15 words) describing the main character's hair, beard, and exact traditional clothing.
    Provide 4 highly detailed IMAGE PROMPTS. YOU MUST INCLUDE THE EXACT 'CHARACTER_DEF' IN EVERY SINGLE PROMPT to maintain consistency.
    
    CRITICAL RULE: PART_A, PART_B, PART_C, and PART_D MUST be exact, verbatim splits of the MONOLOGUE. You must not skip, summarize, or alter a single word from the MONOLOGUE when dividing it into these 4 parts.
    
    FORMAT: 
    TITLE: [text] 
    SCRIPTURE: [text] 
    MONOLOGUE: [text] 
    CHARACTER_DEF: [hair color, beard style, specific clothing]
    PART_A: [text] PROMPT_A: [Include CHARACTER_DEF here. Classical biblical illustration style, action...]
    PART_B: [text] PROMPT_B: [Include CHARACTER_DEF here. Classical biblical illustration style, action...]
    PART_C: [text] PROMPT_C: [Include CHARACTER_DEF here. Classical biblical illustration style, action...]
    PART_D: [text] PROMPT_D: [Include CHARACTER_DEF here. Classical biblical illustration style, action...]
    """
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
    
    # 🚨 NAKED PAYLOAD: Bypasses API crash. Negative prompt blocks anime.
    payload = {
        "height": 1024,
        "width": 576,
        "prompt": f"Masterpiece, classical biblical storybook illustration, Renaissance oil painting style, traditional art, dramatic lighting, highly detailed face. {prompt}",
        "negative_prompt": "anime, manga, modern cartoon, pop art, sketch, 3d render, distorted face, poorly drawn eyes, deformed anatomy, ugly, mutated, missing limbs",
        "num_images": 1
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        res_json = response.json()
        
        if 'sdGenerationJob' not in res_json:
            print(f"❌ Leonardo API error: {res_json}")
            return False
            
        gen_id = res_json['sdGenerationJob']['generationId']
        
        # Poll for completion
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

    # 🎙️ AUDIO GENERATION: Stable SDK logic ported from TheWorldToday
    print("🎙️ Generating Narration...")
    duration = 30.0
    voice = None
    
    for attempt in range(3):
        try:
            print(f"  ...Audio Attempt {attempt + 1}/3")
            audio_gen = client_11.text_to_speech.convert(
                text=data.get('MONOLOGUE'), 
                voice_id="SAxJUlDKRc79XAyeWyMu", 
                model_id="eleven_multilingual_v2",
                output_format="mp3_44100_128" # Stable format constraint
            )
            
            with open("voice.mp3", "wb") as f:
                for chunk in audio_gen:
                    f.write(chunk)
            
            time.sleep(5) # Buffer to ensure file saves properly
            voice_clip = AudioFileClip("voice.mp3")
            
            if voice_clip.duration < 15:
                print(f"⚠️ Incomplete audio detected ({voice_clip.duration}s). Re-downloading...")
                voice_clip.close() 
                time.sleep(3)
                continue
                
            # Success
            duration = voice_clip.duration
            voice = voice_clip
            print(f"✅ Voice generated successfully: {duration:.1f}s")
            break
            
        except Exception as e:
            print(f"⚠️ ElevenLabs SDK error: {e}")
            time.sleep(3)
            
    if not voice:
        print("❌ All ElevenLabs attempts failed. Proceeding with background track only.")

    p_dur = duration / 4 

    # 🎨 IMAGE GENERATION
    image_files = []
    for char in ['A', 'B', 'C', 'D']:
        fname = f"scene_{char}.png"
        prompt = data.get(f'PROMPT_{char}')
        if not generate_leonardo_image(prompt, fname):
            PIL.Image.new('RGB', (1080, 1920), color=(15, 20, 35)).save(fname)
        image_files.append(fname)

    # 🎬 VIDEO ASSEMBLY
    print(f"🎬 Compiling {duration:.1f}s video...")
    final_clips = []
    
    for i, img in enumerate(image_files):
        try:
            # Background Layer
            bg = (ImageClip(img)
                  .set_duration(p_dur)
                  .set_start(i * p_dur)
                  .resize(height=1920)
                  .set_position('center')
                  .resize(lambda t: 1 + 0.04 * t)) # Ken Burns
            final_clips.append(bg)
            
            # 🚨 FIX: Uncapped Text, Expanded Box Height (500), Safe Zone Positioning
            char_key = ['A', 'B', 'C', 'D'][i]
            raw_text = data.get(f'PART_{char_key}', "...") 
            
            txt = (TextClip(raw_text, font="THEBOLDFONT-FREEVERSION.ttf", fontsize=60, 
                            color='yellow' if i % 2 == 0 else 'white', 
                            stroke_color='black', stroke_width=3,
                            method='caption', size=(850, 500)) 
                   .set_duration(p_dur)
                   .set_start(i * p_dur)
                   .set_position(('center', 1100))) 
            final_clips.append(txt)
        except Exception as e:
            print(f"⚠️ Clip {i} assembly error: {e}")

    # 🎛️ AUDIO MIX
    try:
        music = audio_loop(AudioFileClip("bible_bgm.m4a"), duration=duration).volumex(0.12)
        final_audio = CompositeAudioClip([voice, music]) if voice else music
    except Exception as e:
        print(f"⚠️ Music mix error: {e}")
        final_audio = voice

    # 🚀 FINAL EXPORT
    final_video = CompositeVideoClip(final_clips, size=(1080, 1920))
    if final_audio:
        final_video = final_video.set_audio(final_audio)
    
    final_video.set_duration(duration).write_videofile("biblical_export.mp4", fps=24, codec="libx264", audio_codec="aac")

    # 🚀 YOUTUBE UPLOAD
    if os.path.exists("biblical_export.mp4"):
        print("🚀 Starting YouTube upload...")
        try:
            creds_json = json.loads(os.getenv('YOUTUBE_CREDENTIALS'))
            from google.oauth2.credentials import Credentials
            creds = Credentials(**creds_json)
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload
            youtube = build("youtube", "v3", credentials=creds)
            body = {
                'snippet': {
                    'title': f"{data.get('TITLE')} | {data.get('SCRIPTURE')}", 
                    'description': f"{data.get('MONOLOGUE')}\n\n#bible #biblestories #shorts", 
                    'categoryId': '22'
                }, 
                'status': {'privacyStatus': 'public'}
            }
            youtube.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload("biblical_export.mp4", chunksize=-1, resumable=True)).execute()
            print("✅ SUCCESS!")
        except Exception as e:
            print(f"❌ YouTube error: {e}")

if __name__ == "__main__":
    produce()
