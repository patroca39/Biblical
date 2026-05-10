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
from moviepy.config import change_settings
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip, AudioFileClip, CompositeAudioClip, concatenate_videoclips, ColorClip
from moviepy.audio.fx.all import audio_loop

# --- 1. SYSTEM CONFIG ---
change_settings({"IMAGEMAGICK_BINARY": "/usr/bin/convert"})

gen_client = genai.Client(
    api_key=os.getenv('GEMINI_API_KEY'), 
    http_options={'api_version': 'v1beta'} 
)
ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY')
PEXELS_API_KEY = os.getenv('PEXELS_API_KEY')

def scout_viral_news():
    print("🌍 ViralScout is scouting trending global events...")
    prompt = f"""
    Today is {datetime.date.today()}. 
    Use Google Search to find one major, highly engaging viral current event or trending global news story from the last 24 hours. 
    Focus on fascinating topics like incredible tech breakthroughs, major pop culture moments, heroic acts, or viral human-interest stories.
    
    1. Write a highly engaging, fast-paced narration of exactly 75 words.
    2. Provide a 3-word Pexels video search query (e.g., "Technology Server Room", "Crowd Cheering Concert").
    3. Split the monologue EXACTLY verbatim into PART_A, PART_B, PART_C, PART_D.
    
    FORMAT: 
    TITLE: [text] 
    CATEGORY: [text] 
    QUERY: [3-word search]
    MONOLOGUE: [text] 
    PART_A: [text] 
    PART_B: [text] 
    PART_C: [text] 
    PART_D: [text] 
    """
    res_text = ""
    for attempt in range(3):
        try:
            print(f"Attempting Gemini Search API (Try {attempt + 1}/3)...")
            res = gen_client.models.generate_content(
                model='gemini-2.5-flash', 
                contents=prompt,
                config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())])
            )
            res_text = res.text
            break
        except Exception as e:
            error_str = str(e)
            if "503" in error_str or "high demand" in error_str.lower():
                print(f"⚠️ Gemini servers busy (503). Waiting 30 seconds before retrying...")
                time.sleep(30)
            else:
                print(f"⚠️ Search failed: {e}")
                break

    if not res_text:
        print("🚨 Search failed entirely. Using emergency offline generation...")
        fallback_prompt = f"""
        Write a highly engaging 75-word viral news story about an incredible, near-future technology breakthrough or a fascinating human achievement.
        Provide a 3-word Pexels search query (e.g., "Futuristic City Technology").
        Split the monologue EXACTLY verbatim into PART_A, PART_B, PART_C, PART_D.
        FORMAT: 
        TITLE: [text] 
        CATEGORY: [text] 
        QUERY: [text]
        MONOLOGUE: [text] 
        PART_A: [text] 
        PART_B: [text] 
        PART_C: [text] 
        PART_D: [text] 
        """
        try:
            res = gen_client.models.generate_content(model='gemini-2.5-flash', contents=fallback_prompt)
            res_text = res.text
        except Exception as e:
            print(f"❌ Complete API Failure: {e}")
            return None

    return {line.split(':', 1)[0].strip(): line.split(':', 1)[1].strip() for line in res_text.split('\n') if ':' in line}

def download_pexels_video(query):
    print(f"📥 Fetching multiple news visuals for: {query}")
    if not PEXELS_API_KEY:
        return []
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
        print(f"⚠️ Pexels error: {e}")
        return []

def produce():
    data = scout_viral_news()
    if not data: return

    # 1. PEXELS B-ROLL
    video_files = download_pexels_video(data.get('QUERY', 'Breaking News'))

    # 2. ADVANCED AUDIO GENERATION (With Word-Level Timestamps)
    print("🎙️ Generating Narration & Fetching Timestamps...")
    duration = 30.0
    voice = None
    alignment_data = None
    
    for attempt in range(3):
        try:
            # 🚨 THE FIX: Direct API call to get exact character timestamps
            url = f"https://api.elevenlabs.io/v1/text-to-speech/4QLC5fepxZkYmdD2IGRU/with-timestamps"
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
            print(f"⚠️ ElevenLabs error: {e}")
            time.sleep(3)

    # 3. VIDEO ASSEMBLY
    print(f"🎬 Compiling {duration:.1f}s video...")
    processed_clips = []
    if video_files:
        for f in video_files:
            try:
                full_clip = VideoFileClip(f).resize(width=1080).without_audio()
                slice_dur = min(6, full_clip.duration)
                processed_clips.append(full_clip.subclip(0, slice_dur))
            except: continue

    if not processed_clips:
        main_bg = ColorClip(size=(1080, 1920), color=(15, 25, 40)).set_duration(duration)
    else:
        final_video_sequence = []
        current_vid_duration = 0
        clip_index = 0
        while current_vid_duration < duration:
            clip_to_add = processed_clips[clip_index % len(processed_clips)]
            final_video_sequence.append(clip_to_add)
            current_vid_duration += clip_to_add.duration
            clip_index += 1
        combined_seq = concatenate_videoclips(final_video_sequence, method="compose")
        main_bg = combined_seq.set_duration(duration) 

    # 4. TIMESTAMP PARSER & POPPING SUBTITLES ENGINE 🚀
    subs = []
    font_p = "THEBOLDFONT-FREEVERSION.ttf"
    
    if alignment_data and 'characters' in alignment_data:
        chars = alignment_data['characters']
        starts = alignment_data['character_start_times_seconds']
        ends = alignment_data['character_end_times_seconds']
        
        # Step A: Group Characters into Words
        words = []
        current_word = ""
        start_time = None
        
        for idx, char in enumerate(chars):
            if char.strip() == "": # If it's a space, finalize the word
                if current_word:
                    words.append({"text": current_word, "start": start_time, "end": ends[idx-1]})
                    current_word = ""
                    start_time = None
            else:
                if current_word == "":
                    start_time = starts[idx]
                current_word += char
                
        if current_word: # Catch the final word
            words.append({"text": current_word, "start": start_time, "end": ends[-1]})
            
        # Step B: Group Words into 2-Word Chunks
        chunk_size = 2
        for j in range(0, len(words), chunk_size):
            chunk_words = words[j:j+chunk_size]
            text = " ".join([w["text"] for w in chunk_words])
            start = chunk_words[0]["start"]
            
            # The clip stays on screen exactly until the NEXT word starts (seamless visual flow)
            if j + chunk_size < len(words):
                end = words[j+chunk_size]["start"]
            else:
                end = duration # Last word holds until video ends
                
            chunk_dur = end - start
            
            # Create the precise TextClip with the pop animation
            txt = (TextClip(text, font=font_p, fontsize=80, 
                           color='white' if (j // chunk_size) % 2 == 0 else 'yellow', 
                           stroke_color='black', stroke_width=4, 
                           method='caption', size=(900, None))
                   .set_duration(chunk_dur)
                   .set_start(start)
                   .set_position(('center', 1100))
                   .resize(lambda t: min(1.0, 0.8 + 4*t)))
            subs.append(txt)

    # 5. AUDIO MIX & EXPORT
    try:
        music = audio_loop(AudioFileClip("bgm.m4a"), duration=duration).volumex(0.12)
        final_audio = CompositeAudioClip([voice, music]) if voice else music
    except: final_audio = voice

    final = CompositeVideoClip([main_bg] + subs).set_audio(final_audio).set_duration(duration)
    final.write_videofile("viral_export.mp4", fps=24, codec="libx264", audio_codec="aac")

    # 6. YOUTUBE UPLOAD
    if os.path.exists("viral_export.mp4"):
        print("🚀 Starting YouTube upload...")
        try:
            creds_json = json.loads(os.getenv('YOUTUBE_TOKEN_JSON'))
            from google.oauth2.credentials import Credentials
            creds = Credentials(**creds_json)
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload
            youtube = build("youtube", "v3", credentials=creds)
            body = {
                'snippet': {'title': f"{data.get('TITLE')} | {data.get('CATEGORY', 'Trending')}", 
                            'description': f"{data.get('MONOLOGUE')}\n\n#viral #trending #news #shorts", 
                            'categoryId': '25'}, 
                'status': {'privacyStatus': 'public'}
            }
            youtube.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload("viral_export.mp4", chunksize=-1, resumable=True)).execute()
            print("✅ SUCCESS!")
        except Exception as e: print(f"❌ YouTube error: {e}")

if __name__ == "__main__":
    produce()
