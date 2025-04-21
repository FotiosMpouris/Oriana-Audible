# mainfunctions.py

import requests
from newspaper import Article as NewspaperArticle, Config
from openai import OpenAI
import streamlit as st
import time
import os
import logging
import re
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from langdetect import detect, LangDetectException
import tempfile # Needed for temporary files
from pydub import AudioSegment # Needed for concatenation

# --- NEW IMPORTS ---
from elevenlabs.client import ElevenLabs, UnauthenticatedRateLimitError, RateLimitError
from elevenlabs import Voice, VoiceSettings # VoiceSettings might be used later

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Configuration ---
AUDIO_DIR = "temp_audio"
if not os.path.exists(AUDIO_DIR):
    os.makedirs(AUDIO_DIR)

# --- ElevenLabs Configuration ---
# You can change this default voice ID based on your ElevenLabs options
ELEVENLABS_DEFAULT_VOICE_ID = "Rachel"
# Character limit per chunk for ElevenLabs API call
ELEVENLABS_CHUNK_TARGET_SIZE = 2500
# OpenAI's hard limit per request (used in fallback and potentially if EL chunk > this)
OPENAI_TTS_MAX_CHARS = 4096

# --- Helper Functions ---
# (is_valid_url and get_valid_filename remain unchanged from your provided version)
def is_valid_url(url):
    """Checks if the URL is valid and potentially reachable."""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

def get_valid_filename(text_input):
    """Creates a safe filename from a string (URL, title, etc.)."""
    if isinstance(text_input, str) and text_input.startswith(('http://', 'https://')):
        parsed_url = urlparse(text_input)
        filename_base = f"{parsed_url.netloc}{parsed_url.path}"
    else:
        filename_base = str(text_input)
    filename = re.sub(r'[\\/*?:"<>|]', "", filename_base)
    filename = filename.replace(' ', '_').replace('/', '_').replace(':', '_')
    max_len = 100
    filename = re.sub(r'^[_./]+|[_./]+$', '', filename[:max_len])
    if not filename: filename = f"article_{int(time.time())}"
    return filename

# --- Core Fetching and Summarization Functions ---
# (fetch_article_content and summarize_text remain unchanged from your provided version)
def fetch_article_content(url):
    """
    Fetches and extracts the main content and title of an article from a URL.
    Uses enhanced headers and fallback.
    """
    logging.info(f"Attempting to fetch article from: {url}")
    if not is_valid_url(url): return None, "Invalid URL format provided."
    browser_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36'
    request_headers = { 'User-Agent': browser_user_agent, 'Accept': 'text/html,...', 'Accept-Language': 'en-US,en;q=0.9', 'DNT': '1' }
    try:
        config = Config(); config.browser_user_agent = browser_user_agent; config.request_timeout = 15; config.fetch_images = False
        article = NewspaperArticle(url, config=config); article.download(); article.parse()
        if not article.text or len(article.text) < 50: raise ValueError(f"Newspaper3k minimal text ({len(article.text)} chars).")
        logging.info(f"Fetched title: '{article.title}' via newspaper3k")
        return {"title": article.title if article.title else url, "text": article.text}, None
    except Exception as newspaper_err:
        logging.warning(f"Newspaper3k failed for {url}: {newspaper_err}. Trying fallback.")
        try:
            response = requests.get(url, timeout=20, headers=request_headers); response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser'); page_title = soup.title.string.strip() if soup.title else url
            content_selectors = ['article', 'main', '.main-content', '#main', '.post-content', '.entry-content', '#content', '.story-content']
            main_content = None
            for selector in content_selectors:
                 found = soup.select_one(selector)
                 if found: main_content = found; break
            if not main_content: main_content = soup.body
            paragraphs = main_content.find_all('p') if main_content else []
            fallback_text = '\n\n'.join([p.get_text(" ", strip=True) for p in paragraphs if p.get_text(strip=True)])
            if fallback_text and len(fallback_text) > 100:
                logging.info(f"Using fallback extraction for {url}, length {len(fallback_text)}")
                return {"title": page_title, "text": fallback_text}, None
            else: raise ValueError(f"Fallback insufficient text ({len(fallback_text)} chars)")
        except Exception as fallback_err:
            logging.error(f"Fallback failed for {url}: {fallback_err}")
            status_code = getattr(getattr(fallback_err, 'response', None), 'status_code', None)
            error_detail = f"HTTP {status_code}" if status_code else f"Error: {fallback_err}"
            final_error_msg = f"Failed to fetch content: {error_detail}. (Initial: {newspaper_err})"
            return None, final_error_msg

def summarize_text(text, api_key):
    """
    Detects language, then summarizes the text using OpenAI API in that language.
    """
    logging.info("Attempting summarization...")
    min_length = 150
    if not text or len(text.strip()) < min_length:
        logging.warning(f"Text too short ({len(text.strip())} chars) for summary.")
        return text if text and len(text.strip()) > 0 else None, "Content too short to summarize."
    try:
        lang_code = "en"; detected_language = "English"
        try: lang_code = detect(text[:1500]); lang_map = {'el': 'Greek','en': 'English'}; detected_language = lang_map.get(lang_code, f"lang {lang_code}"); logging.info(f"Detected lang: {lang_code}")
        except LangDetectException: logging.warning("Lang detect failed.")
        system_prompt = f"Summarize the key info concisely and accurately IN {detected_language.upper()}."
        user_prompt = f"Provide a concise summary (around 5-7 sentences) IN {detected_language.upper()} of:\n\n---\n{text}\n---"
        client = OpenAI(api_key=api_key); response = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "system", "content": system_prompt},{"role": "user", "content": user_prompt}], temperature=0.5, max_tokens=400)
        summary = response.choices[0].message.content.strip()
        if not summary or len(summary) < 20: raise ValueError("Generated summary too short/empty.")
        logging.info(f"Generated summary in {detected_language}.")
        return summary, None
    except Exception as e:
        logging.error(f"Summarization error: {e}")
        return None, f"Failed to summarize: {e}"

# --- Combined TTS Function (Primary: ElevenLabs, Fallback: OpenAI) ---
def generate_audio(
    text,
    elevenlabs_api_key, # Required for primary attempt
    openai_api_key,     # Required for fallback
    base_filename_id,
    identifier,
    # Parameters specifically for the OpenAI fallback:
    voice_openai="alloy",
    speed_openai=1.0,
    # Parameters for ElevenLabs (can be expanded later, e.g., pass voice_id)
    # For now, using default voice ID specified above
):
    """
    Generates audio using ElevenLabs (primary) or OpenAI (fallback).
    Handles chunking and concatenation for both. Requires FFmpeg.
    Returns final audio file path or (None, error_message).
    """
    operation_id = f"{base_filename_id}_{identifier}" # For logging context
    logging.info(f"[{operation_id}] Starting audio generation process...")
    if not text or not text.strip():
        logging.error(f"[{operation_id}] Cannot generate audio for empty text.")
        return None, "Cannot generate audio for empty text."

    # --- Language Warning (Applies to both TTS engines) ---
    try:
        text_lang = detect(text[:500])
        if text_lang != 'en':
            logging.warning(f"[{operation_id}] Text appears non-English ({text_lang}). TTS pronunciation may be inaccurate with selected voices.")
    except LangDetectException:
        logging.warning(f"[{operation_id}] Language detection failed for TTS sample.")

    # --- Prepare Filenames ---
    safe_base_filename = get_valid_filename(base_filename_id)
    # Unique filename for the final output
    final_filename = f"{safe_base_filename}_{identifier}_{int(time.time())}.mp3"
    final_filepath = os.path.join(AUDIO_DIR, final_filename)

    # --- Chunking Logic (Using your provided strategy) ---
    text_chunks = []
    paragraphs = text.split('\n')
    current_chunk = ""
    # Target size slightly less than EL limit for safety margin
    chunk_target_size = ELEVENLABS_CHUNK_TARGET_SIZE
    for paragraph in paragraphs:
        stripped = paragraph.strip()
        if not stripped: continue
        if len(current_chunk) + len(stripped) + 1 <= chunk_target_size:
            current_chunk += stripped + "\n"
        else:
            if current_chunk.strip(): text_chunks.append(current_chunk.strip())
            if len(stripped) > chunk_target_size:
                logging.warning(f"[{operation_id}] Single paragraph too long ({len(stripped)} chars), force splitting.")
                for i in range(0, len(stripped), chunk_target_size): text_chunks.append(stripped[i:i+chunk_target_size])
                current_chunk = ""
            else: current_chunk = stripped + "\n"
    if current_chunk.strip(): text_chunks.append(current_chunk.strip())

    if not text_chunks:
        logging.error(f"[{operation_id}] Text processing resulted in no valid chunks.")
        return None, "Text could not be split into processable chunks."
    logging.info(f"[{operation_id}] Split text into {len(text_chunks)} chunks.")

    # --- Attempt ElevenLabs TTS ---
    elevenlabs_client = None
    elevenlabs_failed = False
    chunk_temp_files = [] # Store paths of generated temporary chunk files
    try:
        if not elevenlabs_api_key:
             raise ValueError("ElevenLabs API key is missing.") # Force fallback if key not provided

        logging.info(f"[{operation_id}] Initializing ElevenLabs client...")
        elevenlabs_client = ElevenLabs(api_key=elevenlabs_api_key)
        # Optional: Check quota here if desired using elevenlabs_client.user.get()

        logging.info(f"[{operation_id}] Generating audio chunks using ElevenLabs (Voice: {ELEVENLABS_DEFAULT_VOICE_ID})...")
        for i, chunk in enumerate(text_chunks):
            if not chunk: logging.warning(f"[{operation_id}] Skipping empty chunk {i+1}"); continue

            # Ensure chunk doesn't exceed absolute limits (though chunking logic aims lower)
            chunk_to_send = chunk[:ELEVENLABS_CHUNK_TARGET_SIZE + 500] # Allow slightly larger just in case
            if len(chunk) > len(chunk_to_send): logging.warning(f"[{operation_id}] Chunk {i+1} truncated before EL call.")

            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3", dir=AUDIO_DIR) as tmp_file:
                chunk_filepath = tmp_file.name

            try:
                logging.debug(f"[{operation_id}] Calling ElevenLabs for chunk {i+1} -> {os.path.basename(chunk_filepath)}")
                audio_bytes = elevenlabs_client.generate(
                    text=chunk_to_send,
                    voice=ELEVENLABS_DEFAULT_VOICE_ID, # Use default or pass as arg later
                    model="eleven_multilingual_v2" # Or "eleven_turbo_v2" etc.
                )
                with open(chunk_filepath, "wb") as f: f.write(audio_bytes)

                if os.path.exists(chunk_filepath) and os.path.getsize(chunk_filepath) > 0:
                    chunk_temp_files.append(chunk_filepath)
                    logging.debug(f"[{operation_id}] Chunk {i+1} saved successfully.")
                else:
                    logging.error(f"[{operation_id}] ElevenLabs chunk {i+1} file missing/empty: {chunk_filepath}")
                    if os.path.exists(chunk_filepath): os.remove(chunk_filepath) # Cleanup empty file
                    # Decide: raise error or just skip? Let's raise to trigger fallback
                    raise IOError(f"ElevenLabs failed to generate valid audio for chunk {i+1}")

            except (UnauthenticatedRateLimitError, RateLimitError) as el_rate_limit_err:
                 logging.warning(f"[{operation_id}] ElevenLabs Quota/Rate Limit Error on chunk {i+1}: {el_rate_limit_err}. Triggering fallback.")
                 elevenlabs_failed = True
                 if os.path.exists(chunk_filepath): os.remove(chunk_filepath) # Cleanup temp file
                 break # Stop processing more chunks with ElevenLabs
            except Exception as el_chunk_err:
                 logging.error(f"[{operation_id}] Error during ElevenLabs generation for chunk {i+1}: {el_chunk_err}")
                 elevenlabs_failed = True
                 if os.path.exists(chunk_filepath): os.remove(chunk_filepath) # Cleanup temp file
                 break # Stop processing more chunks with ElevenLabs

    except Exception as el_init_err:
        logging.error(f"[{operation_id}] Failed to initialize or use ElevenLabs client: {el_init_err}")
        elevenlabs_failed = True # Ensure fallback is triggered

    # --- Fallback to OpenAI TTS if ElevenLabs failed ---
    if elevenlabs_failed:
        logging.warning(f"[{operation_id}] Attempting fallback to OpenAI TTS (Voice: {voice_openai}, Speed: {speed_openai}).")
        # Cleanup any successful ElevenLabs chunks before starting OpenAI
        for temp_f in chunk_temp_files:
            if os.path.exists(temp_f): try: os.remove(temp_f); except OSError: pass
        chunk_temp_files = [] # Reset the list for OpenAI chunks

        try:
            openai_client = OpenAI(api_key=openai_api_key)
            logging.info(f"[{operation_id}] Generating audio chunks using OpenAI TTS...")
            for i, chunk in enumerate(text_chunks):
                 if not chunk: logging.warning(f"[{operation_id}] Skipping empty chunk {i+1} (OpenAI)"); continue

                 chunk_to_send = chunk[:OPENAI_TTS_MAX_CHARS] # Use OpenAI limit
                 if len(chunk) > len(chunk_to_send): logging.warning(f"[{operation_id}] Chunk {i+1} truncated for OpenAI.")

                 with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3", dir=AUDIO_DIR) as tmp_file:
                     chunk_filepath = tmp_file.name

                 try:
                     logging.debug(f"[{operation_id}] Calling OpenAI for chunk {i+1} -> {os.path.basename(chunk_filepath)}")
                     response = openai_client.audio.speech.create(
                         model="tts-1", voice=voice_openai, speed=speed_openai,
                         input=chunk_to_send, response_format="mp3"
                     )
                     response.stream_to_file(chunk_filepath)

                     if os.path.exists(chunk_filepath) and os.path.getsize(chunk_filepath) > 0:
                         chunk_temp_files.append(chunk_filepath)
                         logging.debug(f"[{operation_id}] OpenAI Chunk {i+1} saved successfully.")
                     else:
                         logging.error(f"[{operation_id}] OpenAI chunk {i+1} file missing/empty: {chunk_filepath}")
                         if os.path.exists(chunk_filepath): os.remove(chunk_filepath)
                         raise IOError(f"OpenAI failed to generate valid audio for chunk {i+1}")

                 except Exception as openai_chunk_err:
                      logging.error(f"[{operation_id}] Error during OpenAI generation for chunk {i+1}: {openai_chunk_err}")
                      if os.path.exists(chunk_filepath): os.remove(chunk_filepath)
                      raise # Reraise to indicate overall failure

        except Exception as openai_err:
            logging.error(f"[{operation_id}] Critical error during OpenAI fallback: {openai_err}")
            # Cleanup and return error
            for temp_f in chunk_temp_files:
                 if os.path.exists(temp_f): try: os.remove(temp_f); except OSError: pass
            return None, f"OpenAI TTS fallback failed: {openai_err}"

    # --- Concatenate Generated Chunks (from successful primary or fallback) ---
    if not chunk_temp_files:
        logging.error(f"[{operation_id}] No audio chunks available for concatenation.")
        return None, "Audio generation failed, no chunks were produced."

    logging.info(f"[{operation_id}] Concatenating {len(chunk_temp_files)} audio chunks...")
    combined_audio = AudioSegment.empty()
    concatenation_errors = 0

    try:
        for chunk_file in chunk_temp_files:
            try:
                # Ensure pydub can find ffmpeg (installed via packages.txt)
                segment = AudioSegment.from_mp3(chunk_file)
                combined_audio += segment
            except Exception as concat_e:
                concatenation_errors += 1
                logging.error(f"[{operation_id}] Error loading/concatenating chunk {os.path.basename(chunk_file)}: {concat_e}.")
                if "ffmpeg" in str(concat_e).lower() or "avprobe" in str(concat_e):
                     logging.critical(f"[{operation_id}] FFmpeg might be missing or inaccessible. Check packages.txt installation.")
                # Continue trying other chunks
        
        if len(combined_audio) == 0:
             raise ValueError("Concatenation resulted in empty audio.")
        if concatenation_errors > 0:
             logging.warning(f"[{operation_id}] {concatenation_errors} chunk(s) failed during concatenation.")

        # Export final audio
        logging.info(f"[{operation_id}] Exporting combined audio to {final_filepath}")
        combined_audio.export(final_filepath, format="mp3")

        if not os.path.exists(final_filepath) or os.path.getsize(final_filepath) == 0:
            raise OSError(f"Final audio file missing or empty after export: {final_filepath}")

        logging.info(f"[{operation_id}] Audio generation process successful. Final file: {final_filepath}")
        return final_filepath, None # SUCCESS!

    except Exception as final_err:
        logging.error(f"[{operation_id}] Error during final concatenation/export: {final_err}")
        # Attempt cleanup of final file if it exists but might be bad
        if os.path.exists(final_filepath): try: os.remove(final_filepath); except OSError: pass
        return None, f"Failed during final audio processing: {final_err}"

    finally:
        # --- Cleanup ALL temporary chunk files ---
        logging.info(f"[{operation_id}] Cleaning up temporary chunk files...")
        cleanup_count = 0
        for temp_f in chunk_temp_files: # Iterate through the list we tracked
            if os.path.exists(temp_f):
                try: os.remove(temp_f); cleanup_count += 1
                except OSError as e: logging.error(f"Error removing temp chunk {temp_f}: {e}")
        logging.info(f"[{operation_id}] Removed {cleanup_count} temporary chunk files.")


# --- Cleanup Function ---
# (cleanup_audio_files remains unchanged from your provided version,
# as temp files are handled within generate_audio's finally block)
def cleanup_audio_files(files_to_keep):
    """Removes FINAL audio files from AUDIO_DIR not in the set of files_to_keep."""
    logging.info(f"Final audio cleanup. Keeping {len(files_to_keep)} active file paths.")
    if not os.path.exists(AUDIO_DIR): return
    kept_paths = set(files_to_keep)
    try:
        removed_count = 0; actual_kept_count = 0
        for filename in os.listdir(AUDIO_DIR):
            if filename.lower().endswith(".mp3"): # Only target mp3s
                file_path = os.path.join(AUDIO_DIR, filename)
                if file_path not in kept_paths:
                    try: os.remove(file_path); removed_count += 1
                    except OSError as e: logging.error(f"Error removing {file_path}: {e}")
                elif os.path.exists(file_path): # Count only if it actually exists
                     actual_kept_count +=1

        logging.info(f"Final audio cleanup: Found {actual_kept_count} kept files, removed {removed_count} unused.")
    except Exception as e: logging.error(f"Audio cleanup scan error in {AUDIO_DIR}: {e}")
