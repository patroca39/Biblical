import os
import math
import subprocess
import numpy as np
import PIL.Image
from moviepy.editor import ImageClip, CompositeVideoClip, ColorClip, VideoFileClip

# Fix for newer Pillow versions
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

TEMP_DIR = "temp_render_files"
os.makedirs(TEMP_DIR, exist_ok=True)

# ---------------------------------------------------------
# FFMPEG EFFECTS (Hardware Accelerated)
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

def fx_wrath_tremor(path, duration, idx):
    # Replaced "Violent Shake" with a low-frequency, heavy rumble (like a massive earthquake)
    vf = "crop=in_w*0.92:in_h*0.92:out_w/2+((in_w-out_w)/2)*sin(t*15):out_h/2+((in_h-out_h)/2)*cos(t*12)"
    return process_ffmpeg_effect(path, f"wrath_{idx}.mp4", duration, vf)

def fx_abyssal_shadow(path, duration, idx):
    # Replaced "Vignette Pulse" with a shadow that slowly creeps in from the edges (Death, Plagues, Fear)
    vf = "vignette=PI/3-t*0.08"
    return process_ffmpeg_effect(path, f"abyss_{idx}.mp4", duration, vf)

# ---------------------------------------------------------
# MOVIEPY EFFECTS (Atmospherics & Blends)
# ---------------------------------------------------------
def fx_reverent_zoom(path, seg_dur):
    # Safely targets the upper-third of the image (faces/sky) for a smooth, religious Ken Burns zoom
    base_clip = ImageClip(path).set_duration(seg_dur).resize(height=1920)
    
    def zoom(get_frame, t):
        frame = get_frame(t)
        z = 1.0 + (0.12 * (t / seg_dur)) # 12% smooth zoom
        w, h = frame.shape[1], frame.shape[0]
        
        crop_w, crop_h = int(w / z), int(h / z)
        x1 = int((w - crop_w) / 2)
        y1 = int((h - crop_h) / 4) # Focuses higher up on the image
        
        cropped = frame[y1:y1+crop_h, x1:x1+crop_w]
        return np.array(PIL.Image.fromarray(cropped).resize((w, h), PIL.Image.Resampling.LANCZOS))
    
    return base_clip.fl(zoom).set_position('center')

def fx_divine_ascension(path, duration):
    # A smooth, slow camera tilt upwards. Used when revealing massive structures, angels, or God.
    base_clip = ImageClip(path).set_duration(duration).resize(width=1080)
    # Ensure the image is tall enough to pan up
    if base_clip.h < 1920: base_clip = base_clip.resize(height=2100) 
    mh = base_clip.h - 1920
    
    def pan_up(t):
        # Starts at the bottom of the crop and moves Y up to 0 over the duration
        speed = mh / duration
        y_pos = -int(mh - (t * speed))
        return ('center', y_pos)
        
    return CompositeVideoClip([base_clip.set_position(pan_up)], size=(1080, 1920)).set_fps(24).set_duration(duration)

def fx_holy_flash(path, duration):
    # Replaced "Strobe Invert". This simulates a blinding flash of divine light that fades back into the image.
    base_clip = ImageClip(path).set_duration(duration).resize(height=1920).set_position('center')
    
    # Create a pure white layer
    white_flash = ColorClip(size=(1080, 1920), color=(255, 255, 255)).set_duration(duration)
    # Make the white layer instantly appear, then fade out quickly over 0.8 seconds
    flash_clip = white_flash.set_opacity(1).crossfadeout(0.8)
    
    return CompositeVideoClip([base_clip, flash_clip.set_start(0)], size=(1080, 1920)).set_fps(24).set_duration(duration)

def fx_organic_drift(path, duration):
    # A very slow, breathing hand-held drift. Standard for biblical narration.
    base_clip = ImageClip(path).set_duration(duration).resize(height=1960)
    mw = base_clip.w - 1080
    mh = base_clip.h - 1920
    
    def drift_pos(t):
        max_drift = 8 # Subtler than before
        speed = 0.8
        x = max_drift * math.sin(t * speed) + (max_drift / 2) * math.cos(t * (speed * 0.7))
        y = max_drift * math.cos(t * (speed * 1.1)) + (max_drift / 2) * math.sin(t * (speed * 0.5))
        return (-int(mw / 2) + int(x), -int(mh / 2) + int(y))
        
    return CompositeVideoClip([base_clip.set_position(drift_pos)], size=(1080, 1920)).set_fps(24).set_duration(duration)

# ---------------------------------------------------------
# MASTER ROUTER
# ---------------------------------------------------------
def apply_motion(path, seg_dur, intensity, scene_idx):
    if not path or not os.path.exists(path):
        return ColorClip(size=(1080, 1920), color=(20, 20, 20)).set_duration(seg_dur)

    intensity = intensity.upper()
    print(f"🎬 Applying Biblical Motif: {intensity} on scene {scene_idx}")

    try:
        if intensity == "REVERENT_ZOOM": return fx_reverent_zoom(path, seg_dur)
        elif intensity == "WRATH_TREMOR": return fx_wrath_tremor(path, seg_dur, scene_idx)
        elif intensity == "ABYSSAL_SHADOW": return fx_abyssal_shadow(path, seg_dur, scene_idx)
        elif intensity == "DIVINE_ASCENSION": return fx_divine_ascension(path, seg_dur)
        elif intensity == "HOLY_FLASH": return fx_holy_flash(path, seg_dur)
        elif intensity == "ORGANIC_DRIFT": return fx_organic_drift(path, seg_dur)
        else: return fx_organic_drift(path, seg_dur)

    except Exception as e:
        print(f"⚠️ Motion render failed, falling back to static: {e}")
        base_clip = ImageClip(path).set_duration(seg_dur).resize(height=1920)
        return CompositeVideoClip([base_clip.set_position('center')], size=(1080, 1920)).set_fps(24).set_duration(seg_dur)
