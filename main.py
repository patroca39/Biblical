import os
import json
import datetime
import time
import requests
import urllib.parse
from google import genai
from google.genai import types
from elevenlabs.client import ElevenLabs
from moviepy.config import change_settings
from moviepy.editor import ImageClip, TextClip, CompositeVideoClip, AudioFileClip, CompositeAudioClip
from moviepy.audio.fx.all import audio_loop

# --- 1. SYSTEM CONFIG ---
change_settings({"IMAGEMAGICK_BINARY": "/usr/bin/convert"})

# Initialize Clients - Using v1beta and explicit model ID to prevent 404s
gen_client = genai.Client(
    api_key=os.getenv('GEMINI_API_KEY'), 
    http_options={'api_version': 'v1beta'} 
)
client_11 = ElevenLabs(api_key=os.getenv('ELEVENLABS_API_KEY'))

def scout_bible_story():
    print("📖 Scripting anime bible story...")
    prompt = f"""
    Today is {datetime.date.today()}. Select a dramatic, pivotal Bible story. 
    Write a narration of exactly 75 words.
    Provide 4 highly detailed IMAGE PROMPTS in 'Epic Shonen Anime Style'.
    FORMAT: 
    TITLE: [text] 
    SCRIPTURE: [text] 
    MONOLOGUE: [text] 
    PART_A: [text] PROMPT_A: [text]
    PART_B: [text] PROMPT_B: [text]
    PART_C: [text] PROMPT_C: [text]
    PART_D: [text] PROMPT_D: [text]
    """
    
    for attempt in range(3):
        try:
            # Using the full resource name to bypass naming glitches
            res = gen_client.models.generate_content(
                model='models/gemini-1.5-flash', 
                contents=prompt
            )
            return {line.split(':', 1)[0].strip(): line.split(':', 1)[1].strip() for line in res.text.split('\n') if ':' in line}
        except Exception as e:
            print(f"⚠️ Attempt {attempt+1} failed: {e}")
            time.sleep(15)
    return None

def produce():
    data = scout_bible_story()
    if not data:
        print("❌ Could not generate script. Exiting.")
        return

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

    # 🎨 IMAGE GENERATION: Pollinations AI (Zero Quota Usage)
    image_files = []
    chars = ['A', 'B', 'C', 'D']
    for char in chars:
        print(f"🎨 Pollinations generating scene_{char}...")
        raw_prompt = data.get(f'PROMPT_{char}', "Epic Anime Scenery")
        # Ensure the prompt is safe for a URL
        clean_prompt = urllib.parse.quote(f"Epic Shonen Anime Style, hand-drawn illustration, cinematic lighting, {raw_prompt}")
        
        # Pollinations URL - dynamic seed ensures unique images every time
        url = f"https://image.pollinations.ai/prompt/{clean_prompt}?width=1080&height=1920&nologo=true&seed={datetime.datetime.now().microsecond}"
        
        try:
            img_res = requests.get(url, timeout=30)
            filename = f"scene_{char}.png"
            with open(filename, 'wb') as f:
                f.write(img_res.content)
            image_files.append(filename)
            time.sleep(2) # Breath time for the server
        except Exception as e:
            print(f"⚠️ Image {char} failed: {e}. Creating fallback.")
            from PIL import Image
            img = Image.new('RGB', (1080, 1920), color=(15, 15, 35))
            filename = f"scene_{char}.png"
            img.save(filename)
            image_files.append(filename)

    # 🎬 VIDEO ASSEMBLY
    clips = []
    for i, img in enumerate(image_files):
        # Ken Burns effect: 4% slow zoom in
        clip = ImageClip(img).set_duration(p_dur).set_start(i * p_dur).set_position('center')
        clip = clip.resize(lambda t: 1 + 0.04 * t) 
        clips.append(clip)

    # ✍️ SUBTITLES (Anime Yellow/White style)
    font_p = "THEBOLDFONT-FREEVERSION.ttf"
    subs = []
    for i, char in enumerate(chars):
        txt = TextClip(data.get(f'PART_{char}', "..."), font=font_p, fontsize=85, 
                       color='yellow' if i%2==0 else 'white', stroke_color='black', stroke_width=2,
                       method='caption', size=(950, None)).set_duration(p_dur).set_start(i*p_dur).set_position(('center', 1450))
        subs.append(txt)

    # 🎛️ AUDIO MIX (With BGM)
    try:
        music = audio_loop(AudioFileClip("bible_bgm.m4a"), duration=duration).volumex(0.12)
        final_audio = CompositeAudioClip([voice, music])
    except:
        print("⚠️ Music mix failed or bible_bgm.m4a missing. Using voice only.")
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
            creds = Credentials(
                token=creds_json.get('token') or creds_json.get('access_token'),
                refresh_token=creds_json.get('refresh_token'),
                token_uri=creds_json.get('token_uri'),
                client_id=creds_json.get('client_id'),
                client_secret=creds_json.get('client_secret'),
                scopes=creds_json.get('scopes')
            )
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload
            youtube = build("youtube", "v3", credentials=creds)
            
            video_title = f"{data.get('TITLE')} | {data.get('SCRIPTURE')}"
            video_desc = f"{data.get('MONOLOGUE')}\n\n#bible #anime #scripture #faith"
            
            body = {'snippet': {'title': video_title, 'description': video_desc, 'categoryId': '22'}, 'status': {'privacyStatus': 'public'}}
            youtube.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload("biblical_export.mp4", chunksize=-1, resumable=True)).execute()
            print("✅ SUCCESS: Video is live!")
        except Exception as e:
            print(f"❌ Upload gate failed: {e}")

if __name__ == "__main__":
    produce()
