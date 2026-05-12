import os
import json
import datetime
import time
import requests
import base64
import PIL.Image

if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

from google import genai
from google.genai import types 
from moviepy.config import change_settings
from moviepy.editor import ImageClip, TextClip, CompositeVideoClip, AudioFileClip, CompositeAudioClip, VideoFileClip, ColorClip, concatenate_videoclips
from moviepy.audio.fx.all import audio_loop

change_settings({"IMAGEMAGICK_BINARY": "/usr/bin/convert"})

gen_client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'), http_options={'api_version': 'v1beta'})
ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY')
LEO_API_KEY = os.getenv('LEONARDO_API_KEY')

def scout_daily_gospel():
    print("📖 Scouting the Gospel for Cinematic Production...")
    prompt = f"""
    Today is {datetime.date.today()}. Find the official Daily Gospel reading.
    
    You are a Hollywood Screenwriter. You must adapt this Gospel reading into a thrilling, 75-word cinematic narrative. 
    DO NOT write a theological summary. Put the viewer in the scene. 
    1. HOOK: First 5 words must be high stakes and dramatic.
    2. STORY: Tell what is happening physically and emotionally in the scene.
    3. CLIFFHANGER: End with a provocative question.

    VISUAL RULES:
    Every single image prompt MUST be strictly set in 1st-century Middle Eastern biblical times. 
    ABSOLUTELY NO modern elements (no modern clothes, no park benches, no modern architecture).
    
    FORMAT: 
    TITLE: [Daily Gospel]
    SCRIPTURE: [Book Chapter:Verse] 
    MONOLOGUE: [The 75-word cinematic story] 
    CHARACTER_DEF: [facial details, 1st-century biblical clothing]
    
    IMAGE_A: [Include CHARACTER_DEF. 1st-century Jerusalem setting. Hyper-realistic, 8k...]
    IMAGE_B: [Include CHARACTER_DEF. Biblical era setting. Hyper-realistic, 8k...]
    IMAGE_C: [Include CHARACTER_DEF. Ancient historical setting. Hyper-realistic, 8k...]
    IMAGE_D: [Include CHARACTER_DEF. 1st-century setting. Hyper-realistic, 8k...]
    """
    for attempt in range(4):
        try:
            res = gen_client.models.generate_content(
                model='gemini-2.5-flash', contents=prompt,
                config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())])
            )
            cleaned = res.text.replace('**', '')
            return {line.split(':', 1)[0].strip(): line.split(':', 1)[1].strip() for line in cleaned.split('\n') if ':' in line}
        except Exception as e:
            if "503" in str(e) or "429" in str(e): time.sleep(30)
            else: break
    return None

def generate_leonardo_image(prompt, filename):
    print(f"🎨 Leonardo Rendering Base Image: {filename}...")
    url = "https://cloud.leonardo.ai/api/rest/v1/generations"
    headers = {"accept": "application/json", "content-type": "application/json", "authorization": f"Bearer {LEO_API_KEY}"}
    payload = {
        "height": 1024, "width": 576, 
        "prompt": f"Hyper-realistic cinematic photography, 8k. {prompt}",
        "num_images": 1, "modelId": "aa77f04e-3eec-4034-9c07-d0f619684628", "alchemy": True
    }
    try:
        response = requests.post(url, json=payload, headers=headers).json()
        gen_id = response['sdGenerationJob']['generationId']
        for _ in range(20):
            time.sleep(4)
            status = requests.get(f"https://cloud.leonardo.ai/api/rest/v1/generations/{gen_id}", headers=headers).json()
            images = status.get('generations_by_pk', {}).get('generated_images', [])
            if images:
                image_id = images[0]['id'] 
                image_url = images[0]['url']
                with open(filename, 'wb') as f: f.write(requests.get(image_url).content)
                return image_id 
    except Exception as e: print(f"❌ Leonardo Image error: {e}")
    return None

def animate_with_leonardo(image_id, filename):
    print(f"🎥 Leonardo Animating Image ID {image_id}...")
    url = "https://cloud.leonardo.ai/api/rest/v2/generations/motion-svd"
    headers = {"accept": "application/json", "content-type": "application/json", "authorization": f"Bearer {LEO_API_KEY}"}
    payload = {
        "imageId": image_id,
        "motionStrength": 5
    }
    try:
        res = requests.post(url, json=payload, headers=headers).json()
        if 'sdGenerationJob' not in res: 
            print(f"❌ Leonardo API Rejected Motion Request: {res}")
            return None
        
        gen_id = res['sdGenerationJob']['generationId']
        print(f"⏳ Motion Task {gen_id} rendering (This may take up to 4 minutes)...")
        
        for _ in range(30): 
            time.sleep(9)
            status = requests.get(f"https://cloud.leonardo.ai/api/rest/v1/generations/{gen_id}", headers=headers).json()
            images = status.get('generations_by_pk', {}).get('generated_images', [])
            if images and images[0].get('motionMP4URL'):
                video_url = images[0]['motionMP4URL']
                with open(filename, "wb") as f: f.write(requests.get(video_url).content)
                print(f"✅ Leonardo Animation Saved: {filename}")
                return filename
            elif status.get('generations_by_pk', {}).get('status') == 'FAILED':
                print("❌ Leonardo explicitly failed to render the video on their end.")
                return None
                
        print("⚠️ Leonardo Motion timed out after 4.5 minutes.")
    except Exception as e: print(f"⚠️ Leonardo Motion Error: {e}")
    return None

def produce():
    data = scout_daily_gospel()
    if not data: return

    # 1. AUDIO GENERATION
    print("🎙️ Generating Voice...")
    duration = 30.0
    voice, alignment_data = None, None
    for attempt in range(3):
        try:
            res_api = requests.post(
                "https://api.elevenlabs.io/v1/text-to-speech/SAxJUlDKRc79XAyeWyMu/with-timestamps", 
                json={"text": data.get('MONOLOGUE'), "model_id": "eleven_multilingual_v2"}, 
                headers={"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"}
            ).json()
            if "audio_base64" in res_api:
                with open("voice.mp3", "wb") as f: f.write(base64.b64decode(res_api['audio_base64']))
                alignment_data = res_api.get('alignment', {})
                if os.path.exists("voice.mp3"):
                    voice = AudioFileClip("voice.mp3")
                    duration = voice.duration
                    break
        except: time.sleep(3)

    # 2. GENERATE & ANIMATE ASSETS
    print("⚙️ Initiating Unified Leonardo Pipeline...")
    seg_dur = duration / 4 
    video_clips = []

    for char in ['A', 'B', 'C', 'D']:
        img_name = f"scene_{char}.png"
        vid_name = f"scene_{char}.mp4"
        
        # Step A: Leonardo Base Image (Returns ID)
        image_id = generate_leonardo_image(data.get(f'IMAGE_{char}'), img_name)
        
        # Step B: Leonardo Animation
        animated_path = None
        if image_id:
            animated_path = animate_with_leonardo(image_id, vid_name)

        # Step C: Clip Assembly with Fallbacks
        try:
            if animated_path and os.path.exists(animated_path):
                # SUCCESS: Leonardo generated a video. Loop it to match segment length.
                clip = VideoFileClip(animated_path).resize(height=1920).crop(width=1080, height=1920).without_audio().loop(duration=seg_dur).subclip(0, seg_dur)
            elif image_id:
                # FALLBACK 1: Motion failed, but image worked.
                print(f"⚠️ Using static image fallback for Scene {char}")
                clip = ImageClip(img_name).set_duration(seg_dur).resize(height=1920).crop(width=1080, height=1920).resize(lambda t: 1 + 0.03 * t)
            else:
                # FALLBACK 2: Everything failed.
                clip = ColorClip(size=(1080, 1920), color=(15, 20, 30)).set_duration(seg_dur)
            
            video_clips.append(clip)
        except Exception as e:
            print(f"❌ Error assembling Scene {char}: {e}")
            video_clips.append(ColorClip(size=(1080, 1920), color=(15, 20, 30)).set_duration(seg_dur))

    main_v = concatenate_videoclips(video_clips, method="compose")

    # 3. SUBTITLES
    subs = []
    font_p = "THEBOLDFONT-FREEVERSION.ttf"
    if alignment_data and 'characters' in alignment_data:
        chars = alignment_data['characters']; starts = alignment_data['character_start_times_seconds']; ends = alignment_data['character_end_times_seconds']
        words, current_word, start_time = [], "", None
        for idx, char in enumerate(chars):
            if char.strip() == "": 
                if current_word: words.append({"text": current_word, "start": start_time, "end": ends[idx-1]}); current_word, start_time = "", None
            else:
                if current_word == "": start_time = starts[idx]
                current_word += char
        if current_word: words.append({"text": current_word, "start": start_time, "end": ends[-1]})

        for j in range(0, len(words), 2):
            chunk = words[j:j+2]; txt_str = " ".join([w["text"] for w in chunk]).upper()
            s = chunk[0]["start"]; e = words[j+2]["start"] if j+2 < len(words) else duration
            subs.append(TextClip(txt_str, font=font_p, fontsize=100, color='yellow', stroke_color='black', stroke_width=5, method='caption', size=(950, None)).set_duration(e-s).set_start(s).set_position(('center', 1300)).resize(lambda t: min(1.0, 0.8 + 5*t)))

    cta = TextClip("SUBSCRIBE FOR MORE", font=font_p, fontsize=65, color='black', bg_color='yellow', size=(850, 110)).set_duration(5).set_start(duration-5.5).set_position(('center', 1650))

    # 4. AUDIO MIX & EXPORT
    print("🎛️ Rendering Final Video...")
    try: music = audio_loop(AudioFileClip("bible_bgm.m4a"), duration=duration).volumex(0.12); final_audio = CompositeAudioClip([voice, music]) if voice else music
    except: final_audio = voice

    final_video = CompositeVideoClip([main_v] + subs + [cta], size=(1080, 1920)).set_audio(final_audio).set_duration(duration)
    final_video.write_videofile("biblical_export.mp4", fps=24, codec="libx264", preset="ultrafast", threads=4)

    # 5. UPLOAD
    if os.path.exists("biblical_export.mp4"):
        print("🚀 Starting YouTube upload...")
        try:
            creds_json = json.loads(os.getenv('YOUTUBE_CREDENTIALS'))
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload
            youtube = build("youtube", "v3", credentials=Credentials(**creds_json))
            body = {'snippet': {'title': f"{data.get('TITLE')} | {data.get('SCRIPTURE')}", 'description': f"{data.get('MONOLOGUE')}\n\n#dailygospel #biblestories #shorts", 'categoryId': '22'}, 'status': {'privacyStatus': 'public'}}
            youtube.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload("biblical_export.mp4", chunksize=-1, resumable=True)).execute()
            print("✅ SUCCESS!")
        except Exception as e: print(f"❌ YouTube error: {e}")

if __name__ == "__main__":
    produce()
