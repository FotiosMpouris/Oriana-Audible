# mainfunctions.py (Rewritten with ElevenLabs Integration and Fallback - Indentation Fixed)

import requests
from newspaper import Article as NewspaperArticle, Config
from openai import OpenAI
import time
import os
import logging
import re
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from langdetect import detect, LangDetectException
import tempfile
from pydub import AudioSegment
import httpx

# --- NEW: Import ElevenLabs ---
from elevenlabs.client import ElevenLabs
from elevenlabs import Voice, VoiceSettings
# Commented out previous attempt:
# from elevenlabs.core.api_error import APIError as ElevenLabsAPIError

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Configuration ---
AUDIO_DIR = "temp_audio"
if not os.path.exists(AUDIO_DIR):
    os.makedirs(AUDIO_DIR)

# --- Helper Functions (Unchanged) ---
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
    if not filename:
        filename = f"article_{int(time.time())}"
    return filename

# --- Core Functions ---

# fetch_article_content (Unchanged)
def fetch_article_content(url):
    """
    Fetches and extracts the main content and title of an article from a URL.
    Uses enhanced headers and fallback.
    Returns a dictionary {'title': title, 'text': text} or None, error_message if fails.
    """
    logging.info(f"Attempting to fetch article from: {url}")
    if not is_valid_url(url):
        logging.error(f"Invalid URL format: {url}")
        return None, "Invalid URL format provided."

    browser_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36'
    request_headers = {
        'User-Agent': browser_user_agent,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
        'Accept-Language': 'en-US,en;q=0.9', 'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive', 'Upgrade-Insecure-Requests': '1', 'DNT': '1',
    }

    try:
        config = Config()
        config.browser_user_agent = browser_user_agent
        config.request_timeout = 15
        config.fetch_images = False
        article = NewspaperArticle(url, config=config)
        article.download()
        article.parse()
        if not article.text or len(article.text) < 50:
            raise ValueError(f"Newspaper3k extracted minimal text ({len(article.text)} chars).")
        logging.info(f"Successfully fetched title: '{article.title}' from {url} using newspaper3k")
        return {"title": article.title if article.title else url, "text": article.text}, None
    except Exception as newspaper_err:
        logging.warning(f"Newspaper3k failed for {url}: {newspaper_err}. Trying fallback.")
        try:
            logging.info(f"Executing requests fallback for: {url} with enhanced headers.")
            response = requests.get(url, timeout=20, headers=request_headers)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            page_title = soup.title.string.strip() if soup.title and soup.title.string else url

            potential_content = []
            for tag_name in ['article', 'main', '.main-content', '#main', '.post-content', '.entry-content', '#content', '.story-content']:
                 found = soup.select_one(tag_name) if tag_name.startswith('.') or tag_name.startswith('#') else soup.find(tag_name)
                 if found:
                     potential_content.append(found)
                     break
            if not potential_content:
                 potential_content.append(soup.body)

            fallback_text = ""
            if potential_content[0]:
                 paragraphs = potential_content[0].find_all('p')
                 fallback_text = '\n\n'.join([p.get_text(" ", strip=True) for p in paragraphs if p.get_text(strip=True)])

            if fallback_text and len(fallback_text) > 100:
                logging.info(f"Using fallback text extraction for: {url} (Title: {page_title}, Length: {len(fallback_text)})")
                return {"title": page_title, "text": fallback_text}, None
            else:
                raise ValueError(f"Fallback extraction yielded insufficient text ({len(fallback_text)} chars). Body paragraphs: {len(soup.find_all('p'))}")

        except Exception as fallback_err:
            logging.error(f"Fallback failed for {url}: {fallback_err}")
            status_code = getattr(getattr(fallback_err, 'response', None), 'status_code', None)
            if status_code == 403: error_detail = "Access denied (403 Forbidden). Bot detection/login likely required."
            elif status_code == 404: error_detail = "Page not found (404)."
            elif status_code: error_detail = f"HTTP Error {status_code}."
            elif isinstance(fallback_err, requests.exceptions.Timeout): error_detail = "Request timed out."
            elif isinstance(fallback_err, requests.exceptions.RequestException): error_detail = f"Network error: {fallback_err}"
            else: error_detail = f"Error: {fallback_err}"

            final_error_msg = f"Failed to fetch content from {url}. {error_detail}. (Newspaper3k msg: {newspaper_err})"
            return None, final_error_msg

# summarize_text (Unchanged)
def summarize_text(text, api_key):
    """
    Detects language, then summarizes the text using OpenAI API in that language.
    Returns the summary text or None, error_message if fails.
    """
    logging.info("Attempting to detect language and summarize text...")
    min_length_for_summary = 150
    if not text or len(text.strip()) < min_length_for_summary:
        logging.warning(f"Text too short ({len(text.strip())} chars, need {min_length_for_summary}) for summarization.")
        if text and len(text.strip()) > 0:
             return text, "Content too short to summarize effectively, returning original text."
        else:
             return None, "Cannot summarize empty or extremely short text."

    try:
        detected_language = "English"
        language_code = "en"
        try:
            sample_text = text[:1500] if len(text) > 1500 else text
            lang_code = detect(sample_text)
            logging.info(f"Detected language: {lang_code}")
            lang_map = {'el': 'Greek', 'en': 'English', 'es': 'Spanish', 'fr': 'French', 'de': 'German', 'it': 'Italian'}
            detected_language = lang_map.get(lang_code, f"the detected language ({lang_code})")
        except LangDetectException:
            logging.warning("Language detection failed. Defaulting to English summary prompt.")

        system_prompt = f"You are a helpful assistant. Summarize the key information from the provided article text concisely and accurately. Write the summary IN {detected_language.upper()}."
        user_prompt = f"Please provide a concise summary (around 5-7 sentences) of the following article text, ensuring it is written IN {detected_language.upper()}:\n\n---\n{text}\n---"

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.5,
            max_tokens=400
        )
        summary = response.choices[0].message.content.strip()
        logging.info(f"Successfully generated summary in {detected_language}.")
        if not summary or len(summary) < 20:
             logging.warning(f"Generated summary seems too short or empty: '{summary}'")
             return None, "Summary generation resulted in very short or empty content."

        return summary, None

    except Exception as e:
        logging.error(f"Error during summarization (incl. detection): {e}")
        error_detail = str(e)
        return None, f"Failed to summarize the text. Error: {error_detail}"


# --- REWRITTEN generate_audio function with ElevenLabs Integration and OpenAI Fallback ---
def generate_audio(
    text: str,
    openai_api_key: str,
    elevenlabs_api_key: str,
    base_filename_id: str,
    identifier: str,
    elevenlabs_voice_id: str = "Rachel", # Default EL voice if not specified
    openai_voice: str = "alloy",        # Default OpenAI voice for fallback
    openai_speed: float = 1.0           # Default speed for fallback
):
    """
    Generates audio using ElevenLabs primarily, falling back to OpenAI TTS.
    Handles text chunking and audio concatenation using pydub.
    Requires FFmpeg to be installed.

    Args:
        text: The text content to convert to speech.
        openai_api_key: API key for OpenAI (used for fallback).
        elevenlabs_api_key: API key for ElevenLabs (used primarily).
        base_filename_id: Base identifier for the generated file (e.g., URL or manual ID).
        identifier: Type identifier ('summary' or 'full').
        elevenlabs_voice_id: The voice ID to use with ElevenLabs TTS.
        openai_voice: The voice name to use with OpenAI TTS (if fallback occurs).
        openai_speed: The speed multiplier for OpenAI TTS (if fallback occurs).

    Returns:
        Tuple[str | None, str | None]: (path_to_final_audio_file, error_message)
                                       Returns (filepath, None) on success,
                                       (None, error_message) on failure.
    """
    logging.info(f"Audio generation requested for: {base_filename_id}_{identifier} (EL Primary: {elevenlabs_voice_id}, OpenAI Fallback: {openai_voice} @{openai_speed}x)")
    if not text or not text.strip():
        logging.error("Cannot generate audio for empty text.")
        return None, "Cannot generate audio for empty text."

    # Language warning (unchanged)
    try:
        text_lang = detect(text[:500])
        if text_lang != 'en':
             logging.warning(f"Text appears non-English ({text_lang}). TTS voices perform best with English; pronunciation may vary.")
    except LangDetectException:
        logging.warning("Language detection failed for TTS input text sample.")

    safe_base_filename = get_valid_filename(base_filename_id)
    # Keep final filename unique using timestamp as before
    final_filename = f"{safe_base_filename}_{identifier}_{elevenlabs_voice_id.lower()}_EL_or_fallback_{int(time.time())}.mp3"
    final_filepath = os.path.join(AUDIO_DIR, final_filename)

   # --- Initialize API Clients (Outside loop for efficiency) ---
        try:
            # ① give the SDK a longer timeout so big chunks finish downloading
            EL_TIMEOUT = 300  # seconds

            elevenlabs_client = ElevenLabs(
                api_key=elevenlabs_api_key,
                timeout=EL_TIMEOUT
            )
            logging.info("ElevenLabs client initialized.")
        
        except Exception as el_init_err:
            logging.error(f"Failed to initialize ElevenLabs client: {el_init_err}. Audio generation will likely fail.")
        # Fallback won't work without client, so return error early
            return None, f"Failed to initialize ElevenLabs client: {el_init_err}"


    try:
        openai_client = OpenAI(api_key=openai_api_key)
        logging.info("OpenAI client initialized.")
    except Exception as oai_init_err:
        logging.error(f"Failed to initialize OpenAI client: {oai_init_err}. Fallback TTS will not be available.")
        # Proceed, but log warning about fallback unavailability
        openai_client = None # Ensure fallback attempt fails gracefully if client init failed
    # --- End API Client Initialization ---


    # --- Chunking Logic (Unchanged OpenAI TTS limits, EL limits might differ but chunking helps both) ---
    max_chars_per_chunk = 2000 # Use a reasonable limit safe for both APIs
    text_chunks = []
    paragraphs = text.split('\n')
    current_chunk = ""
    for paragraph in paragraphs:
        stripped_paragraph = paragraph.strip()
        if not stripped_paragraph: continue

        if len(current_chunk) + len(stripped_paragraph) + 1 <= max_chars_per_chunk:
            current_chunk += stripped_paragraph + "\n"
        else:
            if current_chunk.strip():
                text_chunks.append(current_chunk.strip())
            if len(stripped_paragraph) > max_chars_per_chunk:
                logging.warning(f"Single paragraph too long ({len(stripped_paragraph)} chars). Splitting.")
                start = 0
                while start < len(stripped_paragraph):
                    end = start + max_chars_per_chunk
                    text_chunks.append(stripped_paragraph[start:end])
                    start = end
                current_chunk = ""
            else:
                current_chunk = stripped_paragraph + "\n"
    if current_chunk.strip():
        text_chunks.append(current_chunk.strip())

    if not text_chunks:
        logging.error("Text processing resulted in no valid chunks.")
        return None, "Text could not be split into processable chunks."
    logging.info(f"Split text into {len(text_chunks)} chunks for TTS processing.")
    # --- End Chunking Logic ---

    chunk_files = []
    combined_audio = AudioSegment.empty()
    overall_error_message = None # Store the first critical error

    # --- Process Each Chunk with ElevenLabs -> OpenAI Fallback ---
    for i, chunk in enumerate(text_chunks):
        chunk_success = False
        # Use tempfile for intermediate chunk files
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3", dir=AUDIO_DIR) as tmp_file:
            chunk_filepath = tmp_file.name
        logging.info(f"--- Processing Chunk {i+1}/{len(text_chunks)} -> {os.path.basename(chunk_filepath)} ---")

        # Ensure chunk isn't empty
        if not chunk or not chunk.strip():
            logging.warning(f"Skipping empty chunk {i+1}.")
            if os.path.exists(chunk_filepath): os.remove(chunk_filepath) # Clean up temp file
            continue

        # --- Attempt 1: ElevenLabs ---
        try:
            logging.info(f"Attempting TTS with ElevenLabs (Voice: {elevenlabs_voice_id}) for chunk {i+1}...")
            # Define voice settings (can be customized further)
            voice_settings = VoiceSettings(stability=0.7, similarity_boost=0.75) # Example settings
            audio_bytes = elevenlabs_client.generate(
                text=chunk,
                voice=Voice(voice_id=elevenlabs_voice_id, settings=voice_settings),
                model="eleven_multilingual_v2" # Or another appropriate model
                # stream=False by default, returns bytes
            )

            # Write the generated audio bytes to the temporary file
            with open(chunk_filepath, "wb") as f:
                for audio_chunk_data in audio_bytes: # Iterate if generate returns a generator/stream
                    f.write(audio_chunk_data)

            if os.path.exists(chunk_filepath) and os.path.getsize(chunk_filepath) > 0:
                logging.info(f"ElevenLabs TTS successful for chunk {i+1}.")
                chunk_files.append(chunk_filepath)
                chunk_success = True
            else:
                logging.error(f"ElevenLabs generated audio file missing or empty for chunk {i+1}: {chunk_filepath}")
                if os.path.exists(chunk_filepath): os.remove(chunk_filepath) # Clean up failed file

        except httpx.HTTPStatusError as el_http_err:
            # This catches HTTP errors like 4xx, 5xx from ElevenLabs via httpx
            status_code = el_http_err.response.status_code
            logging.warning(f"ElevenLabs HTTP Error for chunk {i+1}: {el_http_err} (Status: {status_code})")
            # Fallback triggers: 401 (Auth), 429 (Rate Limit/Quota), 400 (Bad Request - sometimes quota/input), 5xx (Server Error)
            # You might refine these based on testing.
            if status_code in [400, 401, 429] or status_code >= 500:
                logging.warning(f"Falling back to OpenAI TTS for chunk {i+1} due to ElevenLabs HTTP error (Status: {status_code}).")
                # Don't set chunk_success = True, proceed to fallback
            else:
                 # For other HTTP errors (e.g., 403 Forbidden if not auth, 404 not found, etc.)
                 # Treat as non-fallback errors for now, log and skip chunk.
                logging.error(f"Non-fallback ElevenLabs HTTP error for chunk {i+1} (Status: {status_code}). Skipping chunk.")
                # --- CORRECTED INDENTATION START ---
                if os.path.exists(chunk_filepath):
                    os.remove(chunk_filepath)
                overall_error_message = overall_error_message or f"ElevenLabs HTTP error {status_code} on chunk {i+1}"
                continue # Skip to next chunk
                # --- CORRECTED INDENTATION END ---

        except Exception as el_general_err:
            # Catch other potential errors during ElevenLabs generation
            logging.error(f"Unexpected error during ElevenLabs TTS for chunk {i+1}: {el_general_err}", exc_info=True)
            logging.warning(f"Falling back to OpenAI TTS for chunk {i+1} due to unexpected ElevenLabs error.")
            # Don't set chunk_success = True, proceed to fallback


        # --- Attempt 2: OpenAI TTS (Fallback) ---
        if not chunk_success:
            if not openai_client:
                 logging.error(f"Skipping OpenAI fallback for chunk {i+1}: OpenAI client failed to initialize.")
                 if os.path.exists(chunk_filepath): os.remove(chunk_filepath) # Clean up temp file from failed EL attempt
                 overall_error_message = overall_error_message or "OpenAI client unavailable for fallback."
                 continue # Skip to next chunk

            logging.info(f"Attempting TTS fallback with OpenAI (Voice: {openai_voice}, Speed: {openai_speed}) for chunk {i+1}...")
            try:
                # Use the existing OpenAI TTS logic
                response = openai_client.audio.speech.create(
                    model="tts-1",
                    voice=openai_voice,
                    speed=openai_speed,
                    input=chunk[:4096], # Ensure OpenAI limit is respected
                    response_format="mp3"
                )
                response.stream_to_file(chunk_filepath)

                if os.path.exists(chunk_filepath) and os.path.getsize(chunk_filepath) > 0:
                    logging.info(f"OpenAI TTS fallback successful for chunk {i+1}.")
                    chunk_files.append(chunk_filepath)
                    chunk_success = True # Mark success for this chunk
                else:
                    logging.error(f"OpenAI fallback audio file missing or empty for chunk {i+1}: {chunk_filepath}")
                    if os.path.exists(chunk_filepath): os.remove(chunk_filepath) # Clean up failed file

            except Exception as openai_err:
                logging.error(f"OpenAI TTS fallback failed for chunk {i+1}: {openai_err}", exc_info=True)
                if os.path.exists(chunk_filepath): # Clean up potentially corrupt file
                    try: os.remove(chunk_filepath)
                    except OSError as rm_err: logging.error(f"Error removing failed OpenAI chunk file {chunk_filepath}: {rm_err}")
                overall_error_message = overall_error_message or f"OpenAI fallback failed on chunk {i+1}: {openai_err}"
                continue # Skip to next chunk

        # If neither EL nor OpenAI succeeded for this chunk after trying
        if not chunk_success:
            logging.error(f"Both ElevenLabs and OpenAI TTS failed for chunk {i+1}. Skipping.")
            # Ensure temp file is cleaned up if it still exists
            if os.path.exists(chunk_filepath):
                try: os.remove(chunk_filepath)
                except OSError: pass


    # --- Concatenate Audio Chunks (Unchanged logic) ---
    if not chunk_files:
        logging.error("No audio chunks were successfully generated. Cannot create final file.")
        # Return the first critical error encountered, or a generic message
        return None, overall_error_message or "Audio generation failed for all text chunks."

    logging.info(f"Concatenating {len(chunk_files)} successfully generated audio chunks...")
    concatenation_errors = 0
    try:
        for chunk_file in chunk_files:
            try:
                # Ensure FFmpeg is available for pydub
                segment = AudioSegment.from_mp3(chunk_file)
                combined_audio += segment
            except Exception as concat_e:
                concatenation_errors += 1
                logging.error(f"Error loading/concatenating chunk {os.path.basename(chunk_file)}: {concat_e}. Skipping this chunk.")
                if "ffmpeg" in str(concat_e).lower() or "Couldn't find ffprobe or avprobe" in str(concat_e):
                    logging.error("This error often indicates FFmpeg is not installed or not found in the system's PATH.")
                continue

        if len(combined_audio) == 0:
             logging.error("Concatenation resulted in empty audio. All chunks might have failed processing.")
             return None, overall_error_message or "Failed to combine audio chunks."

        if concatenation_errors > 0:
             logging.warning(f"{concatenation_errors} chunk(s) failed to load during concatenation and were skipped.")

        # Export the final combined audio file
        logging.info(f"Exporting combined audio to {final_filepath}")
        combined_audio.export(final_filepath, format="mp3")

        if not os.path.exists(final_filepath) or os.path.getsize(final_filepath) == 0:
            logging.error(f"Final concatenated audio file missing or empty after export: {final_filepath}")
            if os.path.exists(final_filepath): os.remove(final_filepath)
            return None, overall_error_message or "Failed to save the final combined audio file."

        logging.info(f"Successfully generated and saved combined audio: {final_filepath}")
        # Return the final path and None for error on success
        return final_filepath, None

    except Exception as e:
        logging.error(f"An unexpected error occurred during the audio concatenation/export process: {e}", exc_info=True)
        if os.path.exists(final_filepath) and (len(combined_audio) == 0 or not combined_audio):
             try: os.remove(final_filepath)
             except OSError: pass
        return None, f"Failed during audio processing: {e}"

    finally:
        # --- Cleanup Temporary Chunk Files (Unchanged logic) ---
        logging.info(f"Cleaning up {len(chunk_files)} temporary chunk audio files...")
        cleanup_count = 0
        for chunk_file in chunk_files:
            try:
                if os.path.exists(chunk_file):
                    os.remove(chunk_file)
                    cleanup_count += 1
            except OSError as e:
                logging.error(f"Error removing temporary chunk file {chunk_file}: {e}")
        logging.info(f"Removed {cleanup_count} temporary files used for chunks.")


# cleanup_audio_files (Unchanged)
def cleanup_audio_files(files_to_keep):
    """Removes audio files from AUDIO_DIR not in the set of files_to_keep."""
    logging.info(f"Audio cleanup running. Keeping {len(files_to_keep)} active file paths.")
    if not os.path.exists(AUDIO_DIR):
        logging.warning(f"Audio directory {AUDIO_DIR} not found during cleanup.")
        return

    kept_paths = set(files_to_keep)

    try:
        removed_count = 0
        kept_count = 0
        for filename in os.listdir(AUDIO_DIR):
            # Only target .mp3 files
            if filename.lower().endswith(".mp3"):
                file_path = os.path.join(AUDIO_DIR, filename)
                # Check if it's a generated file (vs. a leftover chunk if cleanup failed)
                # We only care about keeping the *final* files listed in session state.
                if file_path not in kept_paths:
                    # Check if it looks like a temporary chunk file (can add more specific patterns if needed)
                    is_temp_chunk = "_chunk_" in filename or len(filename) > 60 # Heuristic
                    log_prefix = "Removed old/unused" if not is_temp_chunk else "Cleaning up leftover temp chunk"

                    try:
                        os.remove(file_path)
                        logging.info(f"{log_prefix} audio file: {file_path}")
                        removed_count += 1
                    except OSError as e:
                        logging.error(f"Error removing audio file {file_path}: {e}")
                else:
                    kept_count += 1

        actual_kept_count = 0
        for path in kept_paths:
            if os.path.exists(path):
                 actual_kept_count += 1
        logging.info(f"Audio cleanup complete. Found {actual_kept_count} active files matching keep list, removed {removed_count} other mp3 files.")

    except Exception as e:
        logging.error(f"Error during audio cleanup scan in {AUDIO_DIR}: {e}")
