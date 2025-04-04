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

    filename = re.sub(r'[\\/*?:"<>|]', "", filename_base)
    filename = filename.replace(' ', '_').replace('/', '_').replace(':', '_')
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
    # (This function remains the same as the previous version with enhanced headers)
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
        config.browser_user_agent = browser_user_agent; config.request_timeout = 15; config.fetch_images = False
        article = NewspaperArticle(url, config=config)
        article.download(); article.parse()
        if not article.text or len(article.text) < 50: raise ValueError("Newspaper3k failed to extract sufficient text.")
        logging.info(f"Successfully fetched title: '{article.title}' from {url} using newspaper3k")
        return {"title": article.title if article.title else url, "text": article.text}, None
    except Exception as newspaper_err:
        logging.warning(f"Newspaper3k failed for {url}: {newspaper_err}. Trying fallback.")
        try:
            logging.info(f"Executing requests fallback for: {url} with enhanced headers.")
            response = requests.get(url, timeout=20, headers=request_headers); response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            page_title = soup.title.string.strip() if soup.title and soup.title.string else url
            main_content = soup.find('article') or soup.find('main') or soup.body
            paragraphs = main_content.find_all('p') if main_content else soup.find_all('p')
            fallback_text = '\n'.join([p.get_text(" ", strip=True) for p in paragraphs if p.get_text(strip=True)])
            if fallback_text and len(fallback_text) > 50:
                logging.info(f"Using fallback text extraction for: {url}")
                return {"title": page_title, "text": fallback_text}, None
            else: raise ValueError(f"Fallback extraction failed ({len(fallback_text)} chars)")
        except Exception as fallback_err:
            logging.error(f"Fallback failed for {url}: {fallback_err}")
            status_code = getattr(getattr(fallback_err, 'response', None), 'status_code', None)
            if status_code == 403: error_detail = "Access denied (403 Forbidden). Advanced bot detection/login likely required."
            elif status_code == 404: error_detail = "Page not found (404)."
            elif status_code: error_detail = f"HTTP Error {status_code}."
            else: error_detail = f"Error: {fallback_err}"
            final_error_msg = f"Failed to fetch {url}. {error_detail} (Initial newspaper: {newspaper_err})"
            return None, final_error_msg


def summarize_text(text, api_key):
    """
    Detects language, then summarizes the text using OpenAI API in that language.
    Returns the summary text or None, error_message if fails.
    """
    logging.info("Attempting to detect language and summarize text...")
    if not text or len(text.strip()) < 150:
        logging.warning(f"Text too short ({len(text.strip())} chars) for summarization.")
        return "Content too short to summarize effectively.", None

    try:
        # --- Language Detection ---
        try:
            lang_code = detect(text[:1000]) # Detect based on first 1000 chars
            logging.info(f"Detected language: {lang_code}")
            # Map language code to full name for the prompt (optional, but nicer)
            lang_map = {'el': 'Greek', 'en': 'English', 'es': 'Spanish', 'fr': 'French', 'de': 'German', 'it': 'Italian'} # Add more as needed
            language_name = lang_map.get(lang_code, f"the original language ({lang_code})")
        except LangDetectException:
            logging.warning("Language detection failed. Defaulting to English summary prompt.")
            language_name = "English" # Fallback language

        # --- Prepare Prompt ---
        system_prompt = f"You are a helpful assistant that summarizes articles clearly and in detail, writing the summary in {language_name}."
        user_prompt = f"Please provide a detailed summary of the following article content in {language_name}, covering the key points in about 5-7 sentences:\n\n{text}"

        # --- Call OpenAI ---
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-3.5-turbo", # Consider GPT-4 for better non-English performance
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.6,
            max_tokens=450 # Slightly more tokens for potentially verbose languages
        )
        summary = response.choices[0].message.content.strip()
        logging.info(f"Successfully generated summary in {language_name}.")
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

    # --- Add Warning for Non-English TTS ---
    try:
        text_lang = detect(text[:500])
        if text_lang != 'en':
             logging.warning(f"Text appears to be non-English ({text_lang}). OpenAI TTS may not render '{voice}' voice accurately in this language.")
             # We can't programmatically switch to a non-existent Greek voice.
             # The API call will proceed with the selected (likely English-optimized) voice.
    except LangDetectException:
        logging.warning("Language detection failed for TTS input text.")
        # Proceed anyway

    safe_base_filename = get_valid_filename(base_filename_id)
    unique_filename = f"{safe_base_filename}_{identifier}_{voice}_{int(time.time())}.mp3"
    filepath = os.path.join(AUDIO_DIR, unique_filename)

    try:
        client = OpenAI(api_key=api_key)
        max_tts_chars = 4000
        text_to_speak = text[:max_tts_chars] if len(text) > max_tts_chars else text
        if len(text) > max_tts_chars: logging.warning(f"Truncated text for TTS.")

        response = client.audio.speech.create(
            model="tts-1", voice=voice, speed=speed,
            input=text_to_speak, response_format="mp3"
        )
        response.stream_to_file(filepath)

        if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
             raise OSError(f"Generated audio file missing or empty: {filepath}")

        logging.info(f"Successfully generated audio: {filepath}")
        return filepath, None
    except Exception as e:
        logging.error(f"Error calling OpenAI API for TTS: {e}")
        if os.path.exists(filepath): # Cleanup
            try: os.remove(filepath)
            except OSError as rm_err: logging.error(f"Error removing file {filepath}: {rm_err}")
        return None, f"Failed to generate audio. OpenAI API error: {e}"


def cleanup_audio_files(files_to_keep):
    """Removes audio files from AUDIO_DIR not in the list of files_to_keep."""
    # (This function remains the same)
    logging.info(f"Audio cleanup. Keeping: {files_to_keep}")
    if not os.path.exists(AUDIO_DIR): return
    try:
        removed_count = 0
        kept_count = 0
        for f in os.listdir(AUDIO_DIR):
            if f.endswith(".mp3"):
                f_path = os.path.join(AUDIO_DIR, f)
                if f_path not in files_to_keep:
                    try: os.remove(f_path); logging.info(f"Removed: {f_path}"); removed_count += 1
                    except OSError as e: logging.error(f"Error removing {f_path}: {e}")
                else: kept_count += 1
        logging.info(f"Cleanup done. Kept: {kept_count}, Removed: {removed_count}")
    except Exception as e: logging.error(f"Audio cleanup error: {e}")
