import os
import json
import datetime
import time
import requests
import PIL.Image
from google import genai
from google.genai import types
from elevenlabs.client import ElevenLabs
from moviepy.config import change_settings
from moviepy.editor import ImageClip, TextClip, CompositeVideoClip, AudioFileClip, CompositeAudioClip
from moviepy.audio.fx.all import audio_loop

# --- 1. SYSTEM CONFIG ---
change_settings({"IMAGEMAGICK_BINARY": "/usr/bin/convert"})
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

gen_client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'), http_options={'api_version': 'v1beta'})
client_11 = ElevenLabs(api_key=os.getenv('ELEVENLABS_API_KEY'))

def scout_bible_story():
    print("📖 Scripting and generating custom Anime prompts...")
    prompt = f"""
    Today is {datetime.date.today()}. Select a dramatic Bible story. 
    Write a narration of exactly 75 words.
    Provide 4 highly detailed IMAGE PROMPTS in 'Epic Shonen Anime Style' that match PART_A through PART_D.
    FORMAT: 
    TITLE: [text] 
    SCRIPTURE: [text] 
    MONOLOGUE: [text] 
    PART_A: [text] PROMPT_A: [text]
    PART_B: [text] PROMPT_B: [text]
    PART_C: [text] PROMPT_C: [text]
    PART_D: [text] PROMPT_D: [text]
    """
    res = gen_client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
    return {line.split(':', 1)[0].strip(): line.split(':', 1)[1].strip() for line in res.text.split('\n') if ':' in line}

def generate_anime_image(prompt, filename):
    print(f"🎨 Nano Banana 2 generating: {filename}...")
    # Using Gemini 3 Flash Image (Nano Banana 2)
    response = gen_client.models.generate_image(
        model='gemini-3-flash-image',
        prompt=f"Epic Shonen Anime Style, hand-drawn high quality illustration, cinematic lighting, vibrant colors, {prompt}",
        config=types.GenerateImageConfig(aspect_ratio="9:16")
    )
    for generated_image in response.generated_images:
        generated_image.image.save(filename)
    return filename

def produce():
    data = scout_bible_story()
    
    # 🎙️ AUDIO: Using the new Voice ID
    print("🎙️ Generating Cinematic Narration...")
    audio_gen = client_11.text_to_speech.convert(
        text=data.get('MONOLOGUE'), 
        voice_id="SAxJUlDKRc79XAyeWyMu", # Updated Voice ID
        model_id="eleven_multilingual_v2"
    )
    with open("voice.mp3", "wb") as f:
        for chunk in audio_gen: f.write(chunk)
    
    voice = AudioFileClip("voice.mp3")
    duration = voice.duration
    p_dur = duration / 4 

    # 🎨 IMAGE GENERATION
    image_files = []
    for char in ['A', 'B', 'C', 'D']:
        img_path = generate_anime_image(data.get(f'PROMPT_{char}'), f"scene_{char}.png")
        image_files.append(img_path)

    # 🎬 VIDEO ASSEMBLY
    clips = []
    for i, img in enumerate(image_files):
        # Create image clips and apply a subtle zoom (Ken Burns effect)
        clip = ImageClip(img).set_duration(p_dur).set_start(i * p_dur).set_position('center')
        clip = clip.resize(lambda t: 1 + 0.04 * t) # Slow 4% zoom for movement
        clips.append(clip)

    # ✍️ SUBTITLES
    font_p = "THEBOLDFONT-FREEVERSION.ttf"
    subs = []
    for i, char in enumerate(['A', 'B', 'C', 'D']):
        txt = TextClip(data.get(f'PART_{char}', "..."), font=font_p, fontsize=85, 
                       color='yellow' if i%2==0 else 'white', stroke_color='black', stroke_width=2,
                       method='caption', size=(950, None)).set_duration(p_dur).set_start(i*p_dur).set_position(('center', 1450))
        subs.append(txt)

    # 🎛️ AUDIO MIX
    try:
        music = audio_loop(AudioFileClip("bible_bgm.m4a"), duration=duration).volumex(0.12)
        final_audio = CompositeAudioClip([voice, music])
    except: final_audio = voice

    # 🚀 RENDER
    final = CompositeVideoClip(clips + subs).set_audio(final_audio).set_duration(duration)
    final.write_videofile("biblical_export.mp4", fps=24, codec="libx264", audio_codec="aac")

    # 🚀 UPLOAD
    if os.path.exists("biblical_export.mp4"):
        print("🚀 Uploading Custom Anime Story to YouTube...")
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
        body = {'snippet': {'title': data.get('TITLE'), 'description': f"{data.get('SCRIPTURE')}\n#bible #anime", 'categoryId': '22'}, 'status': {'privacyStatus': 'public'}}
        youtube.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload("biblical_export.mp4", chunksize=-1, resumable=True)).execute()
        print("✅ SUCCESS!")

if __name__ == "__main__":
    produce()
