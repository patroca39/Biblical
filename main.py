import os
import json
import datetime
import time
import requests
import base64
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

# Initialize Clients
gen_client = genai.Client(
    api_key=os.getenv('GEMINI_API_KEY'), 
    http_options={'api_version': 'v1beta'} 
)
ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY')
client_11 = ElevenLabs(api_key=ELEVENLABS_API_KEY)
LEO_API_KEY = os.getenv('LEONARDO_API_KEY')

def scout_daily_gospel():
    print("📖 Scouting the Gospel of the Day...")
    
    # 🚨 GOSPEL SEARCH: Automatically finds today's specific reading
    prompt = f"""
    Today is {datetime.date.today()}. 
    Use Google Search to find the official Daily Gospel reading (Catholic or Revised Common Lectionary) for today's exact date.
    
    Based ONLY on that specific Gospel reading, write a narration of exactly 75 words.
    
    CRITICAL: If the reading is a parable or abstract teaching, focus your IMAGE PROMPTS on the physical metaphors (e.g., sheep, vineyards, storms, seeds) rather than just people talking.
    
    First, write a CHARACTER_DEF (max 15 words) describing the main character or metaphor subject with realistic facial features, weathered skin, and historically accurate 1st-century clothing.
    Provide 4 highly detailed IMAGE PROMPTS. YOU MUST INCLUDE THE EXACT 'CHARACTER_DEF' IN EVERY SINGLE PROMPT to maintain consistency.
    
    CRITICAL RULE: You MUST place each PART and each PROMPT on a brand new line. Do NOT combine them on the same line.
    
    FORMAT: 
    TITLE: [Daily Gospel for Today's Date]
    SCRIPTURE: [Book Chapter:Verse] 
    MONOLOGUE: [text] 
    CHARACTER_DEF: [facial details, skin texture, specific clothing]
    PART_A: [text] 
    PROMPT_A: [Include CHARACTER_DEF here. Hyper-realistic cinematic photography, shot on 35mm lens, 8k, action...]
    PART_B: [text] 
    PROMPT_B: [Include CHARACTER_DEF here. Hyper-realistic cinematic photography, epic scale, action...]
    PART_C: [text] 
    PROMPT_C: [Include CHARACTER_DEF here. Hyper-realistic cinematic photography, dramatic lighting, action...]
    PART_D: [text] 
    PROMPT_D: [Include CHARACTER_DEF here. Hyper-realistic cinematic photography, masterpiece, action...]
    """
    try:
        res = gen_client.models.generate_content(
            model='gemini-2.5-flash', 
            contents=prompt,
            config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())])
        )
        return {line.split(':', 1)[0].strip(): line.split(':', 1)[1].strip() for line in res.text.split('\n') if ':' in line}
    except Exception as e:
        print(f"⚠️ Scripting failed: {e}")
        return None

def generate_leonardo_image(prompt, filename):
    if not prompt:
        print("❌ No prompt provided to Leonardo!")
        return False

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
        "prompt": f"Hyper-realistic cinematic photography, shot on 35mm lens, 8k resolution, highly detailed skin textures, natural lighting, masterpiece, realistic eyes, historical accuracy, perfect human proportions, anatomically correct. {prompt}",
        "negative_prompt": "anime, manga, illustration, 3d render, plastic skin, deformed anatomy, bad proportions, mismatched limbs, extra limbs, missing limbs, disembodied limbs, elongated body, disconnected limbs, mutated hands, poorly drawn face, distorted face, extra fingers, blurry, out of frame",
        "num_images": 1,
        "modelId": "aa77f04e-3eec-4034-9c07-d0f619684628", # Leonardo Kino XL
        "alchemy": True # 🚨 Ensure Alchemy is on for Kino XL
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        res_json = response.json()
        
        if 'sdGenerationJob' not in res_json:
            print(f"❌ Leonardo API error: {res_json}")
            return False
            
        gen_id = res_json['sdGenerationJob']['generationId']
        
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
    data = scout_daily_gospel()
    if not data: return

    # 🎙️ ADVANCED AUDIO GENERATION (With Word-Level Timestamps)
    print("🎙️ Generating Narration & Fetching Timestamps...")
    duration = 30.0
    voice = None
    alignment_data = None
    
    for attempt in range(3):
        try:
            print(f"  ...Audio Attempt {attempt + 1}/3")
            url = f"https://api.elevenlabs.io/v1/text-to-speech/SAxJUlDKRc79XAyeWyMu/with-timestamps"
            headers = {
                "xi-api-key": ELEVENLABS_API_KEY,
                "Content-Type": "application/json"
            }
            payload = {
                "text": data.get('MONOLOGUE'),
                "model_id": "eleven_multilingual_v2",
                "output_format": "mp3_44100_128"
            }
            
            response = requests.post(url, json=payload, headers=headers).json()
            
            if "audio_base64" in response:
                audio_bytes = base64.b64decode(response['audio_base64'])
                with open("voice.mp3", "wb") as f:
                    f.write(audio_bytes)
                
                alignment_data = response.get('alignment', {})
                
                if os.path.exists("voice.mp3") and os.path.getsize("voice.mp3") > 15000:
                    voice_clip = AudioFileClip("voice.mp3")
                    if voice_clip.duration >= 10:
                        duration = voice_clip.duration
                        voice = voice_clip
                        print(f"✅ Voice & Timestamps generated successfully: {duration:.1f}s")
                        break
                    else:
                        voice_clip.close()
            print("⚠️ ElevenLabs returned a short/error file. Retrying...")
            time.sleep(3)
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

    # 🎬 VIDEO ASSEMBLY (Images Only)
    print(f"🎬 Compiling {duration:.1f}s video...")
    final_clips = []
    
    for i, img in enumerate(image_files):
        try:
            bg = (ImageClip(img)
                  .set_duration(p_dur)
                  .set_start(i * p_dur)
                  .resize(height=1920)
                  .set_position('center')
                  .resize(lambda t: 1 + 0.04 * t)) 
            final_clips.append(bg)
        except Exception as e:
            print(f"⚠️ Clip {i} assembly error: {e}")

    # 🚀 TIMESTAMP PARSER & POPPING SUBTITLES ENGINE
    subs = []
    font_p = "THEBOLDFONT-FREEVERSION.ttf"
    
    if alignment_data and 'characters' in alignment_data:
        chars = alignment_data['characters']
        starts = alignment_data['character_start_times_seconds']
        ends = alignment_data['character_end_times_seconds']
        
        words = []
        current_word = ""
        start_time = None
        
        for idx, char in enumerate(chars):
            if char.strip() == "": 
                if current_word:
                    words.append({"text": current_word, "start": start_time, "end": ends[idx-1]})
                    current_word = ""
                    start_time = None
            else:
                if current_word == "":
                    start_time = starts[idx]
                current_word += char
                
        if current_word: 
            words.append({"text": current_word, "start": start_time, "end": ends[-1]})
            
        chunk_size = 2
        for j in range(0, len(words), chunk_size):
            chunk_words = words[j:j+chunk_size]
            text = " ".join([w["text"] for w in chunk_words])
            start = chunk_words[0]["start"]
            
            if j + chunk_size < len(words):
                end = words[j+chunk_size]["start"]
            else:
                end = duration 
                
            chunk_dur = end - start
            
            txt = (TextClip(text, font=font_p, fontsize=80, 
                           color='white' if (j // chunk_size) % 2 == 0 else 'yellow', 
                           stroke_color='black', stroke_width=4, 
                           method='caption', size=(900, None))
                   .set_duration(chunk_dur)
                   .set_start(start)
                   .set_position(('center', 1100))
                   .resize(lambda t: min(1.0, 0.8 + 4*t)))
            subs.append(txt)

    # 🎛️ AUDIO MIX & EXPORT
    try:
        music = audio_loop(AudioFileClip("bible_bgm.m4a"), duration=duration).volumex(0.12)
        final_audio = CompositeAudioClip([voice, music]) if voice else music
    except Exception as e:
        print(f"⚠️ Music mix error: {e}")
        final_audio = voice

    final_video = CompositeVideoClip(final_clips + subs, size=(1080, 1920))
    if final_audio:
        final_video = final_video.set_audio(final_audio)
    
    final_video.set_duration(duration).write_videofile("biblical_export.mp4", fps=24, codec="libx264", audio_codec="aac")

    # 🚀 YOUTUBE UPLOAD
    if os.path.exists("biblical_export.mp4"):
        print("🚀 Starting YouTube upload...")
        try:
            # NOTE: Double check if your GitHub Secret for this repo is YOUTUBE_CREDENTIALS or YOUTUBE_TOKEN_JSON
            creds_json = json.loads(os.getenv('YOUTUBE_CREDENTIALS'))
            from google.oauth2.credentials import Credentials
            creds = Credentials(**creds_json)
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload
            youtube = build("youtube", "v3", credentials=creds)
            body = {
                'snippet': {
                    'title': f"{data.get('TITLE')} | {data.get('SCRIPTURE')}", 
                    'description': f"{data.get('MONOLOGUE')}\n\n#dailygospel #biblestories #shorts", 
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
