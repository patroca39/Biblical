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
# Ensure ImageMagick and FFmpeg are available on the GitHub Runner
change_settings({"IMAGEMAGICK_BINARY": "/usr/bin/convert"})
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

# Initialize API Clients
gen_client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'), http_options={'api_version': 'v1beta'})
client_11 = ElevenLabs(api_key=os.getenv('ELEVENLABS_API_KEY'))
PEXELS_API_KEY = os.getenv('PEXELS_API_KEY')

def scout_bible_story():
    print("📖 Scripting anime bible story with Biblical accuracy...")
    # Strict prompt to ensure scriptural integrity
    prompt = f"""
    Today is {datetime.date.today()}. Select a dramatic, pivotal Bible story. 
    Write a narration of exactly 75 words that is 100% faithful to the scripture.
    Include the specific SCRIPTURE BOOK and VERSE.
    Provide a 3-word Pexels query for EPIC SHONEN ANIME style cinematic visuals (e.g., 'Golden Temple Sky', 'Ancient Desert Storm').
    
    FORMAT: 
    TITLE: [text] 
    SCRIPTURE: [text] 
    QUERY: [text] 
    MONOLOGUE: [text] 
    PART_A: [text] 
    PART_B: [text] 
    PART_C: [text] 
    PART_D: [text]
    """
    
    res_text = ""
    for attempt in range(3):
        try:
            response = gen_client.models.generate_content(
                model='gemini-2.5-flash', 
                contents=prompt, 
                config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())])
            )
            res_text = response.text
            break
        except Exception as e:
            print(f"⚠️ Gemini busy (Attempt {attempt+1}): {e}")
            time.sleep(30)
    
    # Parse the response into a dictionary
    return {line.split(':', 1)[0].strip(): line.split(':', 1)[1].strip() for line in res_text.split('\n') if ':' in line}

def download_pexels(query):
    print(f"📥 Fetching Epic visuals for: {query}")
    headers = {"Authorization": PEXELS_API_KEY}
    url = f"https://api.pexels.com/videos/search?query={query}&per_page=5&orientation=portrait"
    try:
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
    except Exception as e:
        print(f"❌ Pexels fetch failed: {e}")
        return []

def produce():
    data = scout_bible_story()
    video_files = download_pexels(data.get('QUERY', 'Cinematic Light'))
    
    # 🎙️ AUDIO: ElevenLabs Narration
    print("🎙️ Generating Holy Scripture Narration...")
    audio_gen = client_11.text_to_speech.convert(
        text=data.get('MONOLOGUE'), 
        voice_id="pNInz6obpgDQGcFmaJgB", # Using the authoritative news/narrator voice
        model_id="eleven_multilingual_v2"
    )
    with open("voice.mp3", "wb") as f:
        for chunk in audio_gen: f.write(chunk)
    
    voice = AudioFileClip("voice.mp3")
    duration = voice.duration
    
    # 🎛️ MIXER: Add Background Music
    print("🎛️ Mixing Audio Tracks...")
    if os.path.exists("bible_bgm.m4a"):
        try:
            music = audio_loop(AudioFileClip("bible_bgm.m4a"), duration=duration).volumex(0.12)
            final_audio = CompositeAudioClip([voice, music])
            print("✅ Music successfully mixed.")
        except Exception as e:
            print(f"❌ Music mix failed: {e}")
            final_audio = voice
    else:
        print("⚠️ bible_bgm.m4a not found. Using voice only.")
        final_audio = voice

    # 🎬 VIDEO: BULLETPROOF LOOP (Eliminates Black Screen)
    print(f"🎬 Rendering {duration:.1f}s anime bible story...")
    processed_clips = []
    if video_files:
        for f in video_files:
            try:
                full_clip = VideoFileClip(f).resize(width=1080).without_audio()
                processed_clips.append(full_clip.subclip(0, min(6, full_clip.duration)))
            except: continue

    if not processed_clips:
        main_bg = ColorClip(size=(1080, 1920), color=(10, 10, 20)).set_duration(duration)
    else:
        final_video_sequence = []
        current_vid_duration = 0
        clip_index = 0
        while current_vid_duration < duration:
            clip_to_add = processed_clips[clip_index % len(processed_clips)]
            final_video_sequence.append(clip_to_add)
            current_vid_duration += clip_to_add.duration
            clip_index += 1
        main_bg = concatenate_videoclips(final_video_sequence, method="compose").set_duration(duration)

    # ✍️ SUBTITLES: Anime Stylized (Yellow with Black Outline)
    font_p = "THEBOLDFONT-FREEVERSION.ttf"
    subs = []
    p_dur = duration / 4
    for i, k in enumerate(['PART_A', 'PART_B', 'PART_C', 'PART_D']):
        txt = TextClip(data.get(k, "..."), font=font_p, fontsize=85, 
                       color='yellow' if i%2==0 else 'white', 
                       stroke_color='black', stroke_width=2,
                       method='caption', size=(950, None)).set_duration(p_dur).set_start(i*p_dur).set_position(('center', 1400))
        subs.append(txt)

    # 📺 FINAL COMPOSITION
    final = CompositeVideoClip([main_bg] + subs).set_audio(final_audio).set_duration(duration)
    final.write_videofile("biblical_export.mp4", fps=24, codec="libx264", audio_codec="aac", 
                        threads=4, preset="ultrafast", temp_audiofile='temp-audio.m4a', remove_temp=True)

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
            
            body = {
                'snippet': {
                    'title': f"{data.get('TITLE')} | {data.get('SCRIPTURE')}", 
                    'description': f"{data.get('MONOLOGUE')}\n\n#bible #anime #scripture #faith", 
                    'categoryId': '22'
                }, 
                'status': {'privacyStatus': 'public', 'selfDeclaredMadeForKids': False}
            }
            
            youtube.videos().insert(
                part="snippet,status", 
                body=body, 
                media_body=MediaFileUpload("biblical_export.mp4", chunksize=-1, resumable=True)
            ).execute()
            print("✅ SUCCESS: Biblical Anime LIVE!")
        except Exception as e:
            print(f"❌ Upload failed: {e}")

if __name__ == "__main__":
    produce()
