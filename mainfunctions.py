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
from langdetect import detect, LangDetectException # Import language detection

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
        if not article.text or len(article.text) < 50:
            raise ValueError("Newspaper3k failed to extract sufficient text.")
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
            # Try finding common main content containers
            main_content = soup.find('article') or soup.find('main') or soup.find(id='main') or soup.find(id='content') or soup.body
            paragraphs = main_content.find_all('p') if main_content else soup.find_all('p')
            fallback_text = '\n'.join([p.get_text(" ", strip=True) for p in paragraphs if p.get_text(strip=True)])

            if fallback_text and len(fallback_text) > 50:
                logging.info(f"Using fallback text extraction for: {url}")
                return {"title": page_title, "text": fallback_text}, None
            else:
                raise ValueError(f"Fallback extraction failed ({len(fallback_text)} chars)")
        except Exception as fallback_err:
            logging.error(f"Fallback failed for {url}: {fallback_err}")
            # Provide more specific error details
            status_code = getattr(getattr(fallback_err, 'response', None), 'status_code', None)
            if status_code == 403: error_detail = "Access denied (403 Forbidden). Advanced bot detection/login likely required."
            elif status_code == 404: error_detail = "Page not found (404)."
            elif status_code: error_detail = f"HTTP Error {status_code}."
            else: error_detail = f"Error: {fallback_err}" # Generic fallback error
            # Combine initial and fallback errors for clarity
            final_error_msg = f"Failed to fetch article content from {url}. {error_detail}. (Initial newspaper error was: {newspaper_err})"
            return None, final_error_msg


def summarize_text(text, api_key):
    """
    Detects language, then summarizes the text using OpenAI API in that language.
    Returns the summary text or None, error_message if fails.
    """
    logging.info("Attempting to detect language and summarize text...")
    if not text or len(text.strip()) < 150: # Adjusted minimum length
        logging.warning(f"Text too short ({len(text.strip())} chars) for summarization.")
        return "Content too short to summarize effectively.", None

    try:
        # Language Detection
        detected_language = "English" # Default
        language_code = "en"
        try:
            # Use a larger sample for potentially mixed-language articles if needed
            sample_text = text[:1500] if len(text) > 1500 else text
            lang_code = detect(sample_text)
            logging.info(f"Detected language: {lang_code}")
            # Map common codes to full names
            lang_map = {'el': 'Greek', 'en': 'English', 'es': 'Spanish', 'fr': 'French', 'de': 'German', 'it': 'Italian'} # Add more if needed
            detected_language = lang_map.get(lang_code, f"the detected language ({lang_code})")
        except LangDetectException:
            logging.warning("Language detection failed. Defaulting to English summary prompt.")
            # Keep default 'English'

        # Prepare Prompt based on detected language
        system_prompt = f"You are a helpful assistant that summarizes articles clearly and in detail, writing the summary IN {detected_language.upper()}."
        user_prompt = f"Please provide a detailed summary of the following article content, IN {detected_language.upper()}. Cover the key points in about 5-7 sentences:\n\n{text}"

        # Call OpenAI
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini", # Using a potentially better model for multilingual tasks
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.6,
            max_tokens=450 # Allow sufficient length for detailed summaries
        )
        summary = response.choices[0].message.content.strip()
        logging.info(f"Successfully generated summary in {detected_language}.")
        return summary, None

    except Exception as e:
        logging.error(f"Error during summarization (incl. detection): {e}")
        return None, f"Failed to summarize the text. Error: {e}"


def generate_audio(text, api_key, base_filename_id, identifier, voice="alloy", speed=1.0):
    """
    Generates audio from text using OpenAI TTS API with specified voice and speed.
    Includes check for non-English text limitations.
    Returns the path to the saved audio file or None, error_message if fails.
    """
    logging.info(f"Attempting audio: {base_filename_id}_{identifier} (Voice: {voice}, Speed: {speed})")
    if not text or not text.strip():
        return None, "Cannot generate audio for empty text."

    # Add Warning for Non-English TTS with English-optimized voices
    try:
        text_lang = detect(text[:500])
        if text_lang != 'en':
             logging.warning(f"Text appears non-English ({text_lang}). Voice '{voice}' is primarily English-trained; pronunciation may be inaccurate.")
    except LangDetectException:
        logging.warning("Lang detect failed for TTS input.")

    safe_base_filename = get_valid_filename(base_filename_id)
    # Include voice/speed in filename? Maybe too long. Keep it simple.
    unique_filename = f"{safe_base_filename}_{identifier}_{voice}_{int(time.time())}.mp3"
    filepath = os.path.join(AUDIO_DIR, unique_filename)

    try:
        client = OpenAI(api_key=api_key)
        max_tts_chars = 4096 # OpenAI TTS limit
        text_to_speak = text[:max_tts_chars] if len(text) > max_tts_chars else text
        if len(text) > max_tts_chars:
            logging.warning(f"Text truncated to {max_tts_chars} characters for TTS API.")
            # Optionally add note to the spoken text itself? e.g. text_to_speak += " [End of generated audio due to length limit]"

        response = client.audio.speech.create(
            model="tts-1", # Use tts-1-hd for potentially better quality but slower/more expensive
            voice=voice,
            speed=speed,
            input=text_to_speak,
            response_format="mp3"
        )
        response.stream_to_file(filepath)

        # Verify file creation
        if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
             # Attempt cleanup if empty file exists
             if os.path.exists(filepath): os.remove(filepath)
             raise OSError(f"Generated audio file missing or empty: {filepath}")

        logging.info(f"Successfully generated audio: {filepath}")
        return filepath, None # Return path and no error message
    except Exception as e:
        logging.error(f"Error calling OpenAI API for TTS: {e}")
        # Cleanup potentially corrupted file
        if os.path.exists(filepath):
            try: os.remove(filepath)
            except OSError as rm_err: logging.error(f"Error removing potentially corrupt file {filepath}: {rm_err}")
        # Provide specific error if possible
        error_message = f"Failed to generate audio. OpenAI API error: {e}"
        return None, error_message # Return None path and the error message


def cleanup_audio_files(files_to_keep):
    """Removes audio files from AUDIO_DIR not in the list of files_to_keep."""
    logging.info(f"Audio cleanup running. Keeping {len(files_to_keep)} active file paths.")
    if not os.path.exists(AUDIO_DIR):
        logging.warning(f"Audio directory {AUDIO_DIR} not found during cleanup.")
        return # Nothing to clean if directory doesn't exist
    try:
        removed_count = 0
        kept_count = 0
        for filename in os.listdir(AUDIO_DIR):
            if filename.endswith(".mp3"):
                file_path = os.path.join(AUDIO_DIR, filename)
                if file_path not in files_to_keep:
                    try:
                        os.remove(file_path)
                        logging.info(f"Removed old audio file: {file_path}")
                        removed_count += 1
                    except OSError as e:
                        logging.error(f"Error removing audio file {file_path}: {e}")
                else:
                    kept_count += 1
        logging.info(f"Audio cleanup complete. Kept {kept_count} files, removed {removed_count} files.")
    except Exception as e:
        logging.error(f"Error during audio cleanup scan: {e}")
