import os
import math
import random
import subprocess
import cv2
import numpy as np
import PIL.Image
from moviepy.editor import ImageClip, CompositeVideoClip, ColorClip, VideoFileClip

# Fix for newer Pillow versions
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

# ---------------------------------------------------------
# GLOBAL SETUP
# ---------------------------------------------------------
# OpenCV Face/Eye Tracker for the Divine Reveal Zooms
FACE_CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

TEMP_DIR = "temp_render_files"
os.makedirs(TEMP_DIR, exist_ok=True)


# ---------------------------------------------------------
# CATEGORY 1: FFMPEG HARDWARE ACCELERATION
# ---------------------------------------------------------
def process_ffmpeg_effect(input_path, output_name, duration, vf_string):
    output_path = os.path.join(TEMP_DIR, output_name)
    cmd = [
        'ffmpeg', '-loop', '1', '-i', input_path,
        '-vf', vf_string,
        '-t', str(duration), '-pix_fmt', 'yuv420p',
        '-c:v', 'libx264', '-preset', 'superfast', '-y', output_path
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return VideoFileClip(output_path)

def fx_violent_shake(path, duration, idx):
    # Heavy, erratic X/Y axis camera shake representing earthquakes or divine wrath
    vf = "crop=in_w*0.9:in_h*0.9:out_w/2+((in_w-out_w)/2)*sin(t*50):out_h/2+((in_h-out_h)/2)*cos(t*40)"
    return process_ffmpeg_effect(path, f"shake_{idx}.mp4", duration, vf)

def fx_vignette_pulse(path, duration, idx):
    # Rhythmic heartbeat darkening at the edges representing fear or claustrophobia
    vf = "vignette=PI/4+PI/8*sin(t*2)"
    return process_ffmpeg_effect(path, f"pulse_{idx}.mp4", duration, vf)


# ---------------------------------------------------------
# CATEGORY 2: OPENCV & MOVIEPY ATMOSPHERICS
# ---------------------------------------------------------
def fx_creep_zoom_target(path, seg_dur):
    # Finds the subject's face and performs a slow, agonizing zoom into their eyes
    cv_img = cv2.imread(path)
    if cv_img is None: raise ValueError("OpenCV read failed")
    
    gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
    faces = FACE_CASCADE.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(100, 100))
    
    h_raw, w_raw, _ = cv_img.shape
    target_x, target_y = w_raw // 2, h_raw // 2
    if len(faces) > 0:
        fx, fy, fw, fh = faces[0]
        target_x, target_y = fx + (fw // 2), fy + (fh // 2)
        
    scale_factor = 1920 / h_raw
    cx, cy = int(target_x * scale_factor), int(target_y * scale_factor)
    
    base_clip = ImageClip(path).set_duration(seg_dur).resize(height=1920)
    
    def zoom_frame_processor(get_frame, t):
        frame = get_frame(t)
        # Slow, dramatic cinematic zoom
        z_factor = 1.0 + (0.35 * (t / seg_dur)) 
        f_h, f_w, _ = frame.shape
        crop_w, crop_h = int(f_w / z_factor), int(f_h / z_factor)
        
        x_start = max(0, min(cx - (crop_w // 2), f_w - crop_w))
        y_start = max(0, min(cy - (crop_h // 2), f_h - crop_h))
        
        cropped_matrix = frame[y_start:y_start+crop_h, x_start:x_start+crop_w]
        return np.array(PIL.Image.fromarray(cropped_matrix).resize((f_w, f_h), PIL.Image.Resampling.LANCZOS))
        
    # Set duration explicitly to prevent NoneType crash
    zoomed_clip = base_clip.fl(zoom_frame_processor).set_duration(seg_dur)
    return CompositeVideoClip([zoomed_clip.set_position((-int((zoomed_clip.w - 1080)/2), 0))], size=(1080, 1920)).set_fps(24).set_duration(seg_dur)

def fx_organic_drift(path, duration):
    # Replaces static panning with a breathing, hand-held camera drift
    base_clip = ImageClip(path).set_duration(duration).resize(height=1980)
    mw = base_clip.w - 1080
    mh = base_clip.h - 1920
    
    def drift_pos(t):
        max_drift = 12
        speed = 1.2
        x = max_drift * math.sin(t * speed) + (max_drift / 2) * math.cos(t * (speed * 0.7))
        y = max_drift * math.cos(t * (speed * 1.1)) + (max_drift / 2) * math.sin(t * (speed * 0.5))
        return (-int(mw / 2) + int(x), -int(mh / 2) + int(y))
        
    return CompositeVideoClip([base_clip.set_position(drift_pos)], size=(1080, 1920)).set_fps(24).set_duration(duration)

def fx_strobe_invert(path, duration):
    # Flashes colors to negative for a few frames to simulate divine lightning or miracles
    base_clip = ImageClip(path).set_duration(duration).resize(height=1920).set_position('center')
    def invert_filter(get_frame, t):
        frame = get_frame(t)
        if (0.5 < t < 0.6) or (1.2 < t < 1.3):
            return 255 - frame
        return frame
    
    # Set duration explicitly to prevent NoneType crash
    return CompositeVideoClip([base_clip.fl(invert_filter).set_duration(duration)], size=(1080, 1920)).set_fps(24).set_duration(duration)


# ---------------------------------------------------------
# MASTER ROUTER
# ---------------------------------------------------------
def apply_motion(path, seg_dur, intensity, scene_idx):
    if not path or not os.path.exists(path):
        return ColorClip(size=(1080, 1920), color=(20, 20, 20)).set_duration(seg_dur)

    intensity = intensity.upper()
    print(f"🎬 Applying Cinematic Action: {intensity} on scene {scene_idx}")

    try:
        # Route to the requested cinematic motion profile
        if intensity == "CREEP_ZOOM_TARGET": return fx_creep_zoom_target(path, seg_dur)
        elif intensity == "VIOLENT_SHAKE": return fx_violent_shake(path, seg_dur, scene_idx)
        elif intensity == "VIGNETTE_PULSE": return fx_vignette_pulse(path, seg_dur, scene_idx)
        elif intensity == "ORGANIC_DRIFT": return fx_organic_drift(path, seg_dur)
        elif intensity == "STROBE_INVERT": return fx_strobe_invert(path, seg_dur)
        elif intensity == "THE_VOID_CUT": return ColorClip(size=(1080, 1920), color=(0, 0, 0)).set_duration(seg_dur)
        
        # Default Fallback for biblical storytelling is the organic camera drift
        else: return fx_organic_drift(path, seg_dur)

    except Exception as e:
        print(f"⚠️ Motion render failed for Scene {scene_idx}, falling back to static image: {e}")
        try:
            base_clip = ImageClip(path).set_duration(seg_dur).resize(height=1920)
            return CompositeVideoClip([base_clip.set_position('center')], size=(1080, 1920)).set_fps(24).set_duration(seg_dur)
        except Exception as static_err:
            print(f"⚠️ Static fallback failed: {static_err}")
            return None
