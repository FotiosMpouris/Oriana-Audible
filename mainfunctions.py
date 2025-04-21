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

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Configuration ---
AUDIO_DIR = "temp_audio"
if not os.path.exists(AUDIO_DIR):
    os.makedirs(AUDIO_DIR)

# --- Helper Functions ---
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

    filename = re.sub(r'[\\/*?:"<>|]', "", filename_base) # Remove invalid OS chars
    filename = filename.replace(' ', '_').replace('/', '_').replace(':', '_') # Replace common separators
    max_len = 100
    # Ensure it doesn't start/end with invalid chars like _/.
    filename = re.sub(r'^[_./]+|[_./]+$', '', filename[:max_len])
    # Default name if empty after sanitization
    if not filename:
        filename = f"article_{int(time.time())}"
    return filename

# --- Core Functions ---

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
        # Use a lower threshold for newspaper, rely more on fallback if needed
        if not article.text or len(article.text) < 50:
            raise ValueError(f"Newspaper3k extracted minimal text ({len(article.text)} chars).")
        logging.info(f"Successfully fetched title: '{article.title}' from {url} using newspaper3k")
        return {"title": article.title if article.title else url, "text": article.text}, None
    except Exception as newspaper_err:
        logging.warning(f"Newspaper3k failed for {url}: {newspaper_err}. Trying fallback.")
        try:
            logging.info(f"Executing requests fallback for: {url} with enhanced headers.")
            response = requests.get(url, timeout=20, headers=request_headers)
            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
            soup = BeautifulSoup(response.text, 'html.parser')
            page_title = soup.title.string.strip() if soup.title and soup.title.string else url

            # Improved fallback text extraction logic
            potential_content = []
            for tag_name in ['article', 'main', '.main-content', '#main', '.post-content', '.entry-content', '#content', '.story-content']: # CSS selectors possible too
                 found = soup.select_one(tag_name) if tag_name.startswith('.') or tag_name.startswith('#') else soup.find(tag_name)
                 if found:
                     potential_content.append(found)
                     break # Stop if a good primary container is found
            if not potential_content: # If no primary container found, fallback to body
                 potential_content.append(soup.body)

            fallback_text = ""
            if potential_content[0]:
                 paragraphs = potential_content[0].find_all('p')
                 fallback_text = '\n\n'.join([p.get_text(" ", strip=True) for p in paragraphs if p.get_text(strip=True)])

            # Check length after joining paragraphs
            if fallback_text and len(fallback_text) > 100: # Increased threshold for fallback
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
            else: error_detail = f"Error: {fallback_err}" # Generic fallback error

            final_error_msg = f"Failed to fetch content from {url}. {error_detail}. (Newspaper3k msg: {newspaper_err})"
            return None, final_error_msg


def summarize_text(text, api_key):
    """
    Detects language, then summarizes the text using OpenAI API in that language.
    Returns the summary text or None, error_message if fails.
    """
    logging.info("Attempting to detect language and summarize text...")
    min_length_for_summary = 150 # Characters
    if not text or len(text.strip()) < min_length_for_summary:
        logging.warning(f"Text too short ({len(text.strip())} chars, need {min_length_for_summary}) for summarization.")
        # Return the original text if it's very short but not empty? Or a specific message.
        if text and len(text.strip()) > 0:
             return text, "Content too short to summarize effectively, returning original text."
        else:
             return None, "Cannot summarize empty or extremely short text."

    try:
        # Language Detection
        detected_language = "English" # Default
        language_code = "en"
        try:
            sample_text = text[:1500] if len(text) > 1500 else text
            lang_code = detect(sample_text)
            logging.info(f"Detected language: {lang_code}")
            lang_map = {'el': 'Greek', 'en': 'English', 'es': 'Spanish', 'fr': 'French', 'de': 'German', 'it': 'Italian'} # Add more if needed
            detected_language = lang_map.get(lang_code, f"the detected language ({lang_code})")
        except LangDetectException:
            logging.warning("Language detection failed. Defaulting to English summary prompt.")

        # Prepare Prompt based on detected language
        system_prompt = f"You are a helpful assistant. Summarize the key information from the provided article text concisely and accurately. Write the summary IN {detected_language.upper()}."
        # Adjust user prompt slightly for clarity
        user_prompt = f"Please provide a concise summary (around 5-7 sentences) of the following article text, ensuring it is written IN {detected_language.upper()}:\n\n---\n{text}\n---"

        # Call OpenAI
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini", # Good balance of capability and cost
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.5, # Slightly lower for more factual summary
            max_tokens=400 # Adjust if summaries are consistently too short/long
        )
        summary = response.choices[0].message.content.strip()
        logging.info(f"Successfully generated summary in {detected_language}.")
        # Basic check if the summary seems valid
        if not summary or len(summary) < 20:
             logging.warning(f"Generated summary seems too short or empty: '{summary}'")
             return None, "Summary generation resulted in very short or empty content."

        return summary, None

    except Exception as e:
        logging.error(f"Error during summarization (incl. detection): {e}")
        error_detail = str(e)
        # Check for specific API errors if possible (e.g., authentication, rate limits)
        # from openai import AuthenticationError, RateLimitError
        # if isinstance(e, AuthenticationError): ...
        return None, f"Failed to summarize the text. Error: {error_detail}"


# --- MODIFIED generate_audio function with Chunking ---
def generate_audio(text, api_key, base_filename_id, identifier, voice="alloy", speed=1.0):
    """
    Generates audio from text using OpenAI TTS API with specified voice and speed.
    Handles text longer than 4096 chars by chunking and concatenating using pydub.
    Requires FFmpeg to be installed.
    Returns the path to the saved final audio file or None, error_message if fails.
    """
    logging.info(f"Attempting audio generation for: {base_filename_id}_{identifier} (Voice: {voice}, Speed: {speed})")
    if not text or not text.strip():
        logging.error("Cannot generate audio for empty text.")
        return None, "Cannot generate audio for empty text."

    # Warning for Non-English Text
    try:
        text_lang = detect(text[:500])
        if text_lang != 'en':
             logging.warning(f"Text appears non-English ({text_lang}). Voice '{voice}' is primarily English-trained; pronunciation may be inaccurate.")
    except LangDetectException:
        logging.warning("Language detection failed for TTS input text sample.")

    safe_base_filename = get_valid_filename(base_filename_id)
    # Final output filename (unique)
    final_filename = f"{safe_base_filename}_{identifier}_{voice}_{int(time.time())}.mp3"
    final_filepath = os.path.join(AUDIO_DIR, final_filename)

    client = OpenAI(api_key=api_key)
    max_tts_chars = 4096  # OpenAI TTS API limit per request
    # Use a slightly smaller target size for chunks to leave buffer room
    target_chunk_size = 4000

    # --- Chunking Logic ---
    text_chunks = []
    # Simple paragraph/newline splitting strategy
    paragraphs = text.split('\n')
    current_chunk = ""
    for paragraph in paragraphs:
        stripped_paragraph = paragraph.strip()
        if not stripped_paragraph:
            continue

        # Check if adding the next paragraph exceeds the target size
        if len(current_chunk) + len(stripped_paragraph) + 1 <= target_chunk_size:
            current_chunk += stripped_paragraph + "\n"
        else:
            # If the current chunk is not empty, add it to the list
            if current_chunk.strip():
                text_chunks.append(current_chunk.strip())

            # Handle the case where a single paragraph is too long
            if len(stripped_paragraph) > target_chunk_size:
                logging.warning(f"Single paragraph is too long ({len(stripped_paragraph)} chars). Splitting it.")
                # Simple split for oversized paragraph
                start = 0
                while start < len(stripped_paragraph):
                    end = start + target_chunk_size
                    text_chunks.append(stripped_paragraph[start:end])
                    start = end
                current_chunk = "" # Reset chunk after handling the long one
            else:
                # Start a new chunk with the current paragraph
                current_chunk = stripped_paragraph + "\n"

    # Add the last remaining chunk if it exists
    if current_chunk.strip():
        text_chunks.append(current_chunk.strip())

    if not text_chunks:
        logging.error("Text processing resulted in no valid chunks to synthesize.")
        return None, "Text could not be split into processable chunks."

    logging.info(f"Split text into {len(text_chunks)} chunks for TTS processing.")

    # --- Generate Audio for Each Chunk ---
    chunk_files = []
    combined_audio = AudioSegment.empty() # Initialize empty audio segment for concatenation

    try:
        for i, chunk in enumerate(text_chunks):
            # Use tempfile for intermediate chunk files to ensure cleanup
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3", dir=AUDIO_DIR) as tmp_file:
                chunk_filepath = tmp_file.name

            logging.info(f"Generating audio for chunk {i+1}/{len(text_chunks)} -> {os.path.basename(chunk_filepath)}")

            try:
                # Ensure chunk isn't empty after stripping/processing
                if not chunk:
                    logging.warning(f"Skipping empty chunk {i+1}")
                    # Clean up the created temp file if skipping
                    if os.path.exists(chunk_filepath): os.remove(chunk_filepath)
                    continue

                # Truncate chunk *just in case* it's slightly over the hard limit
                chunk_to_send = chunk[:max_tts_chars]
                if len(chunk) > max_tts_chars:
                     logging.warning(f"Chunk {i+1} slightly truncated from {len(chunk)} to {max_tts_chars} chars before API call.")

                # Make the API call for the chunk
                response = client.audio.speech.create(
                    model="tts-1", # Use tts-1-hd for higher quality if needed (slower/more expensive)
                    voice=voice,
                    speed=speed,
                    input=chunk_to_send, # Send the (potentially truncated) chunk text
                    response_format="mp3"
                )
                # Stream response directly to the temporary file path
                response.stream_to_file(chunk_filepath)

                # Verify file creation and size
                if os.path.exists(chunk_filepath) and os.path.getsize(chunk_filepath) > 0:
                    chunk_files.append(chunk_filepath) # Add path to list for concatenation
                else:
                    logging.error(f"Generated audio chunk file missing or empty: {chunk_filepath}")
                    # Attempt cleanup of empty/failed file
                    if os.path.exists(chunk_filepath): os.remove(chunk_filepath)
                    # Decide how to handle: raise error, skip chunk? Let's log and continue, skipping this chunk.

            except Exception as chunk_e:
                logging.error(f"Error generating audio for chunk {i+1}: {chunk_e}")
                # Attempt cleanup of potentially corrupt temp file
                if os.path.exists(chunk_filepath):
                    try: os.remove(chunk_filepath)
                    except OSError as rm_err: logging.error(f"Error removing failed chunk file {chunk_filepath}: {rm_err}")
                # Option: Re-raise the exception to stop the entire process
                # raise chunk_e
                # Option: Log and continue (will result in missing audio for this chunk)
                continue # Skip to the next chunk

        # --- Concatenate Audio Chunks ---
        if not chunk_files:
            logging.error("No audio chunks were successfully generated. Cannot create final file.")
            return None, "Audio generation failed for all text chunks."

        logging.info(f"Concatenating {len(chunk_files)} successfully generated audio chunks...")
        concatenation_errors = 0
        for chunk_file in chunk_files:
            try:
                # Important: Ensure FFmpeg is available for pydub to read MP3s
                segment = AudioSegment.from_mp3(chunk_file)
                combined_audio += segment
            except Exception as concat_e:
                concatenation_errors += 1
                logging.error(f"Error loading/concatenating chunk {os.path.basename(chunk_file)}: {concat_e}. Skipping this chunk.")
                # Optionally add details about needing FFmpeg here if error suggests it
                if "ffmpeg" in str(concat_e).lower() or "Couldn't find ffprobe or avprobe" in str(concat_e):
                    logging.error("This error often indicates FFmpeg is not installed or not found in the system's PATH.")
                continue # Skip corrupted/unreadable chunk

        if len(combined_audio) == 0:
             logging.error("Concatenation resulted in empty audio. All chunks might have failed processing.")
             return None, "Failed to combine audio chunks."

        if concatenation_errors > 0:
             logging.warning(f"{concatenation_errors} chunk(s) failed to load during concatenation and were skipped.")

        # Export the final combined audio file
        logging.info(f"Exporting combined audio to {final_filepath}")
        combined_audio.export(final_filepath, format="mp3")

        # Final verification
        if not os.path.exists(final_filepath) or os.path.getsize(final_filepath) == 0:
            logging.error(f"Final concatenated audio file missing or empty after export: {final_filepath}")
            # Attempt cleanup
            if os.path.exists(final_filepath): os.remove(final_filepath)
            return None, "Failed to save the final combined audio file."

        logging.info(f"Successfully generated and saved combined audio: {final_filepath}")
        return final_filepath, None # Return path to the final combined file

    except Exception as e:
        logging.error(f"An unexpected error occurred during the audio generation/concatenation process: {e}")
        # Ensure final file isn't left if export failed before completion or was empty
        if os.path.exists(final_filepath) and (len(combined_audio) == 0 or not combined_audio):
             try: os.remove(final_filepath)
             except OSError: pass
        return None, f"Failed during audio processing: {e}"

    finally:
        # --- Cleanup Temporary Chunk Files ---
        logging.info(f"Cleaning up {len(chunk_files)} temporary chunk audio files...")
        cleanup_count = 0
        for chunk_file in chunk_files:
            try:
                if os.path.exists(chunk_file):
                    os.remove(chunk_file)
                    cleanup_count += 1
            except OSError as e:
                logging.error(f"Error removing temporary chunk file {chunk_file}: {e}")
        logging.info(f"Removed {cleanup_count} temporary files.")


def cleanup_audio_files(files_to_keep):
    """Removes audio files from AUDIO_DIR not in the set of files_to_keep."""
    logging.info(f"Audio cleanup running. Keeping {len(files_to_keep)} active file paths.")
    if not os.path.exists(AUDIO_DIR):
        logging.warning(f"Audio directory {AUDIO_DIR} not found during cleanup.")
        return # Nothing to clean if directory doesn't exist

    # Ensure files_to_keep contains absolute paths if AUDIO_DIR is used that way
    # (os.path.join inside generate_audio should handle this already)
    kept_paths = set(files_to_keep) # Use a set for efficient lookup

    try:
        removed_count = 0
        kept_count = 0
        for filename in os.listdir(AUDIO_DIR):
            # Only target .mp3 files, ignore other files/subdirs
            if filename.lower().endswith(".mp3"):
                file_path = os.path.join(AUDIO_DIR, filename)
                if file_path not in kept_paths:
                    try:
                        os.remove(file_path)
                        logging.info(f"Removed old/unused audio file: {file_path}")
                        removed_count += 1
                    except OSError as e:
                        logging.error(f"Error removing audio file {file_path}: {e}")
                else:
                    kept_count += 1
        # Log kept count based on files actually found matching the kept_paths list
        actual_kept_count = 0
        for path in kept_paths:
            if os.path.exists(path):
                 actual_kept_count += 1
        logging.info(f"Audio cleanup complete. Found {actual_kept_count} active files to keep, removed {removed_count} unused files.")

    except Exception as e:
        logging.error(f"Error during audio cleanup scan in {AUDIO_DIR}: {e}")


