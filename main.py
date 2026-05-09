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
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip, AudioFileClip, concatenate_videoclips, ColorClip, CompositeAudioClip
from moviepy.audio.fx.all import audio_loop

# --- 1. SYSTEM CONFIG ---
change_settings({"IMAGEMAGICK_BINARY": "/usr/bin/convert"})
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

gen_client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'), http_options={'api_version': 'v1beta'})
client_11 = ElevenLabs(api_key=os.getenv('ELEVENLABS_API_KEY'))
PEXELS_API_KEY = os.getenv('PEXELS_API_KEY')

def scout_bible_story():
    print("📖 Scripting anime bible story...")
    prompt = f"""
    Today is {datetime.date.today()}. Select a dramatic Bible story. 
    Write a narration of exactly 75 words.
    Provide a 3-word Pexels query for 'ANIME STYLE ILLUSTRATION' (e.g., 'Anime Cloud Palace', 'Anime Desert Knight').
    FORMAT: TITLE: [text] SCRIPTURE: [text] QUERY: [text] MONOLOGUE: [text] PART_A: [text] PART_B: [text] PART_C: [text] PART_D: [text]
    """
    res = gen_client.models.generate_content(model='gemini-2.5-flash', contents=prompt, config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())]))
    return {line.split(':', 1)[0].strip(): line.split(':', 1)[1].strip() for line in res.text.split('\n') if ':' in line}

def download_pexels(query):
    headers = {"Authorization": PEXELS_API_KEY}
    # We add "illustration" to the query to force non-realistic results
    url = f"https://api.pexels.com/videos/search?query={query}+illustration&per_page=5&orientation=portrait"
    r = requests.get(url, headers=headers).json()
    clips = []
    for i, video in enumerate(r.get('videos', [])):
        v_url = video['video_files'][0]['link']
        v_name = f"clip_{i}.mp4"
        with requests.get(v_url, stream=True) as v:
            with open(v_name, "wb") as f:
                for chunk in v.iter_content(chunk_size=1024): f.write(chunk)
        clips.append(v_name)
    return clips

def produce():
    data = scout_bible_story()
    video_files = download_pexels(data.get('QUERY', 'Anime Landscape'))
    
    # --- AUDIO FIX ---
    print("🎙️ Generating Narration...")
    audio_gen = client_11.text_to_speech.convert(text=data.get('MONOLOGUE'), voice_id="pNInz6obpgDQGcFmaJgB", model_id="eleven_multilingual_v2")
    with open("voice.mp3", "wb") as f:
        for chunk in audio_gen: f.write(chunk)
    
    voice = AudioFileClip("voice.mp3")
    duration = voice.duration
    
    try:
        music = audio_loop(AudioFileClip("bible_bgm.m4a"), duration=duration).volumex(0.10)
        final_audio = CompositeAudioClip([voice, music])
    except:
        final_audio = voice

    # --- VIDEO FIX (FREEZE PREVENTION) ---
    print("🎬 Rendering Anime Visuals...")
    processed_clips = []
    for f in video_files:
        try:
            # .set_fps(24) prevents the "first frame only" bug
            c = VideoFileClip(f).resize(width=1080).without_audio().set_fps(24)
            processed_clips.append(c.subclip(0, min(6, c.duration)))
        except: continue

    final_seq = []
    curr_dur = 0
    idx = 0
    while curr_dur < duration:
        clip = processed_clips[idx % len(processed_clips)]
        final_seq.append(clip)
        curr_dur += clip.duration
        idx += 1
    main_bg = concatenate_videoclips(final_seq, method="compose").set_duration(duration)

    # --- SUBTITLE FIX (READABILITY) ---
    font_p = "THEBOLDFONT-FREEVERSION.ttf"
    subs = []
    # Using 4 parts, but we ensure they are timed to the actual duration
    p_dur = duration / 4
    for i, k in enumerate(['PART_A', 'PART_B', 'PART_C', 'PART_D']):
        txt = TextClip(data.get(k, "..."), font=font_p, fontsize=85, 
                       color='yellow' if i%2==0 else 'white', 
                       stroke_color='black', stroke_width=2,
                       method='caption', size=(950, None)).set_duration(p_dur).set_start(i*p_dur).set_position(('center', 1400))
        subs.append(txt)

    # --- FINAL MIX ---
    final = CompositeVideoClip([main_bg] + subs).set_audio(final_audio).set_duration(duration)
    # Using 'libx264' and 'aac' ensures high compatibility with YouTube
    final.write_videofile("biblical_export.mp4", fps=24, codec="libx264", audio_codec="aac", temp_audiofile='temp-audio.m4a', remove_temp=True)

    # UPLOAD
    if os.path.exists("biblical_export.mp4"):
        try:
            creds_json = json.loads(os.getenv('YOUTUBE_CREDENTIALS'))
            from google.oauth2.credentials import Credentials
            creds = Credentials(token=creds_json.get('token') or creds_json.get('access_token'), refresh_token=creds_json.get('refresh_token'), token_uri=creds_json.get('token_uri'), client_id=creds_json.get('client_id'), client_secret=creds_json.get('client_secret'), scopes=creds_json.get('scopes'))
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload
            youtube = build("youtube", "v3", credentials=creds)
            body = {'snippet': {'title': data.get('TITLE'), 'description': f"{data.get('SCRIPTURE')}\n#bible #anime", 'categoryId': '22'}, 'status': {'privacyStatus': 'public'}}
            youtube.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload("biblical_export.mp4", chunksize=-1, resumable=True)).execute()
            print("✅ Biblical Anime successfully uploaded!")
        except Exception as e: print(f"❌ Upload failed: {e}")

if __name__ == "__main__":
    produce()
