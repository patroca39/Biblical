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
gen_client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'), http_options={'api_version': 'v1beta'})
client_11 = ElevenLabs(api_key=os.getenv('ELEVENLABS_API_KEY'))
PEXELS_API_KEY = os.getenv('PEXELS_API_KEY')

def scout_bible_story():
    print("📖 Fetching Scripture...")
    prompt = f"""
    Today is {datetime.date.today()}. Select a pivotal story from the Bible. 
    1. Extract the exact SCRIPTURE reference.
    2. Write a 75-word faithful narration (30s duration).
    3. Provide a 3-word Pexels query for EPIC, ANIME-STYLE cinematic visuals (e.g., 'Golden Temple Light', 'Stormy Sea Clouds').
    FORMAT: TITLE: [text] SCRIPTURE: [text] QUERY: [text] MONOLOGUE: [text] PART_A: [text] PART_B: [text] PART_C: [text] PART_D: [text]
    """
    res_text = ""
    for _ in range(3):
        try:
            response = gen_client.models.generate_content(model='gemini-2.5-flash', contents=prompt, config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())]))
            res_text = response.text
            break
        except: time.sleep(30)
    return {line.split(':', 1)[0].strip(): line.split(':', 1)[1].strip() for line in res_text.split('\n') if ':' in line}

def download_pexels_video(query):
    headers = {"Authorization": PEXELS_API_KEY}
    url = f"https://api.pexels.com/videos/search?query={query}&per_page=5&orientation=portrait"
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

def produce_bible_video():
    data = scout_bible_story()
    video_files = download_pexels_video(data.get('QUERY', 'Cinematic Light'))
    
    # 🎙️ AUDIO: ElevenLabs + BGM Mix
    audio_gen = client_11.text_to_speech.convert(text=data.get('MONOLOGUE'), voice_id="pNInz6obpgDQGcFmaJgB", model_id="eleven_multilingual_v2")
    with open("voice.mp3", "wb") as f:
        for chunk in audio_gen: f.write(chunk)
    
    voice = AudioFileClip("voice.mp3")
    duration = voice.duration
    
    # MIX MUSIC
    try:
        music = AudioFileClip("bible_bgm.m4a").volumex(0.12)
        music = audio_loop(music, duration=duration)
        final_audio = CompositeAudioClip([voice, music])
    except: final_audio = voice

    # 🎬 VIDEO: Bulletproof Loop
    processed_clips = [VideoFileClip(f).resize(width=1080).without_audio().subclip(0, 6) for f in video_files if os.path.exists(f)]
    final_seq = []
    curr_dur = 0
    idx = 0
    while curr_dur < duration:
        c = processed_clips[idx % len(processed_clips)]
        final_seq.append(c)
        curr_dur += c.duration
        idx += 1
    main_bg = concatenate_videoclips(final_seq, method="compose").set_duration(duration)

    # ✍️ SUBTITLES (Yellow/White Anime Style)
    font_p = "THEBOLDFONT-FREEVERSION.ttf"
    p_dur = duration / 4
    subs = []
    for i, key in enumerate(['PART_A', 'PART_B', 'PART_C', 'PART_D']):
        txt = TextClip(data.get(key, "..."), font=font_p, fontsize=80, color='yellow' if i%2==0 else 'white', stroke_color='black', stroke_width=2, method='caption', size=(950, None)).set_duration(p_dur).set_start(i*p_dur).set_position(('center', 1400))
        subs.append(txt)

    # 🚀 RENDER & UPLOAD
    final = CompositeVideoClip([main_bg] + subs).set_audio(final_audio).set_duration(duration)
    final.write_videofile("biblical_export.mp4", fps=24, codec="libx264", audio_codec="aac")

    # [YouTube Upload Logic - Same as TheWorldToday]
    if os.path.exists("biblical_export.mp4"):
        print(f"✅ Created: {data.get('TITLE')}")
        # Insert YouTube upload block here using YOUTUBE_CREDENTIALS secret

if __name__ == "__main__":
    produce_bible_video()
