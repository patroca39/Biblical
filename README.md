🕊️ Faceless Biblical Automation: Daily Gospel Video Engine

End-to-End Hybrid AI Video Generation & Distribution Pipeline

📖 Overview

The Faceless Biblical Automation Engine is a production-grade orchestration system that autonomously researches, produces, and publishes daily religious video content.

Unlike standard text-to-video scripts, this pipeline utilizes Real-Time Search Grounding via Google Gemini to pull the exact Catholic Daily Gospel for the current calendar date. It then orchestrates a hybrid dual-render pipeline—passing assets through Leonardo AI for both high-fidelity image generation and Motion SVD (Stable Video Diffusion). Finally, it uses a custom Python compositor to mix sub-second audio SFX offsets, apply FFMPEG-accelerated motion effects, and securely publish the video to YouTube.

📂 Repository Structure

main.py: The core orchestrator. Handles real-time web scraping via Gemini, JSON validation, audio rhythm mixing, and the dual-render visual pipeline.

motion_engine.py: A custom hybrid router that applies hardware-accelerated FFMPEG effects (e.g., WRATH_TREMOR, ABYSSAL_SHADOW) and MoviePy zooms when SVD generation is unavailable or times out.

utils.py: Contains production plumbing, including Telegram webhook alerts, logging configurations, and the YouTube API exponential backoff uploader.

bible_bgm.m4a / THEBOLDFONT-FREEVERSION.ttf: Local assets for the compositing engine.

✨ Core Engineering Highlights

🌍 Real-Time Grounding (RAG): Gemini 2.5 Flash is configured with Google Search tools to dynamically fetch and verify the exact scripture reading for datetime.date.today(), ensuring content is always accurate and timely.

🎛️ Hybrid Dual-Render Pipeline (SVD + FFMPEG): The visual engine attempts to render realistic physics via Leonardo's Motion SVD. If the API times out or fails, the orchestrator gracefully falls back to motion_engine.py to generate mathematical, hardware-accelerated FFMPEG drifts and camera pans.

🎵 Advanced Audio Rhythm & Sub-Second Sync: The engine parses tags like [NARRATOR|REVERENT_ZOOM|THUNDER] to dynamically fetch SFX. It automatically offsets the voice track by 0.2s to allow the SFX impact to hit first, and calculates organic silence gaps based on the narrative tension of the scene.

⚡ Idempotency & Downstream Webhooks: Features a Google Sheets barrier that prevents redundant API spending by ensuring only one video is produced per calendar day. Upon successful YouTube upload, it POSTs the binary video file and metadata to an n8n webhook for cross-platform distribution.

🏗️ System Architecture

Phase 1: Intelligence & Data Grounding

Idempotency Check: Pings Google Sheets to verify today's date hasn't already been processed.

Web Scraping: Gemini executes a live Google Search to pull today's Daily Gospel.

Structured Prompting: Outputs a strict JSON payload mapping out 6 cinematic scenes, complete with precise MOTION_PROFILES and SFX_TRIGGERS.

Phase 2: Dual Asset Generation

Leonardo Visuals: Generates 16:9 vertical images using a rotating pool of cinematic anime styles.

Leonardo SVD: Automatically sends the generated images into the Motion SVD queue for AI video generation.

ElevenLabs Audio: Generates voice lines with exact character timestamps and parallel dynamic SFX generation.

Phase 3: Hybrid Compositing & Kinetic Typography

Smart Assembly: If the SVD video successfully rendered, it loops and crops it. If not, it routes the static image through motion_engine.py to apply math-based visual effects (like Wrath Tremor or Holy Flash).

Crossfade Compositing: Concatenates the 6 scenes using smooth -0.5s crossfades to eliminate harsh visual cuts.

Typography: Overlays word-by-word captions tied exactly to ElevenLabs millisecond timestamps, highlighting predefined IMPACT_WORDS in gold.

Phase 4: Distribution & Alerting

YouTube Upload: Uploads the final .mp4 using googleapiclient with a built-in exponential backoff to survive connection drops.

Metadata Injection: Automatically generates SEO tags, titles, and Fair Use copyright disclaimers.

Handoff: Logs the URL to Google Sheets and dispatches the file to n8n via HTTP POST for TikTok/Instagram deployment.

🚀 Setup & Installation

1. Environment Variables

You must configure the following environment variables:

GEMINI_API_KEY: Your Google DeepMind API key.

ELEVENLABS_API_KEY: ElevenLabs API key for Voice and SFX.

LEONARDO_API_KEY: Leonardo AI API key.

N8N_WEBHOOK_URL: Your n8n production webhook endpoint.

GOOGLE_SHEETS_JSON: Stringified OAuth2 credentials for Sheets.

YOUTUBE_CREDENTIALS: Stringified OAuth2 dict for the YouTube API.

SPREADSHEET_ID: The ID of your orchestrator Google Sheet.

2. Running the Engine

To execute a single generation cycle manually, run:

python main.py


⚖️ Disclaimer

This project is an autonomous orchestration engine designed for educational and portfolio demonstration purposes. All content generated is synthetic. Users are responsible for monitoring their own API usage costs (ElevenLabs, Leonardo AI) and ensuring adherence to YouTube's Community Guidelines and automation terms of service.
