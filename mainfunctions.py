# mainfunctions.py
import requests
from newspaper import Article as NewspaperArticle, Config
from openai import OpenAI
import streamlit as st
import time
import os
import logging
import re # Needed for filename sanitization if not already imported
from urllib.parse import urlparse
from bs4 import BeautifulSoup

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
    # Replace URL-specific characters first if it looks like a URL
    if isinstance(text_input, str) and text_input.startswith(('http://', 'https://')):
        parsed_url = urlparse(text_input)
        # Use netloc and path, replace invalid chars
        filename_base = f"{parsed_url.netloc}{parsed_url.path}"
    else:
        filename_base = str(text_input) # Treat as title or other text

    # Remove or replace characters invalid for filenames
    filename = re.sub(r'[\\/*?:"<>|]', "", filename_base) # Remove invalid chars
    filename = filename.replace(' ', '_').replace('/', '_').replace(':', '_') # Replace others
    # Limit length to avoid issues
    max_len = 100
    return filename[:max_len].strip('_') # Trim leading/trailing underscores

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

    # Define More Realistic Browser Headers
    browser_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36'
    request_headers = {
        'User-Agent': browser_user_agent,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'DNT': '1',
    }

    try:
        # Configure newspaper3k
        config = Config()
        config.browser_user_agent = browser_user_agent
        config.request_timeout = 15
        config.fetch_images = False

        # Initialize Article with config
        article = NewspaperArticle(url, config=config)
        article.download()
        article.parse()

        if not article.text or len(article.text) < 50:
            logging.warning(f"Newspaper3k extracted minimal or no text ({len(article.text or '')} chars) from: {url}. Trying basic requests fallback.")
            raise ValueError("Newspaper3k failed to extract sufficient text.")

        logging.info(f"Successfully fetched title: '{article.title}' from {url} using newspaper3k")
        return {
            "title": article.title if article.title else url,
            "text": article.text
        }, None

    except Exception as newspaper_err:
        logging.warning(f"Newspaper3k failed for {url}: {newspaper_err}. Trying basic requests fallback.")
        # Fallback using requests + BeautifulSoup with Enhanced Headers
        try:
            logging.info(f"Executing requests fallback for: {url} with enhanced headers.")
            response = requests.get(url, timeout=20, headers=request_headers)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')
            page_title = url
            if soup.title and soup.title.string:
                page_title = soup.title.string.strip()

            main_content = soup.find('article') or soup.find('main') or soup.body
            paragraphs = main_content.find_all('p') if main_content else soup.find_all('p')
            fallback_text = '\n'.join([p.get_text(" ", strip=True) for p in paragraphs if p.get_text(strip=True)])

            if fallback_text and len(fallback_text) > 50:
                logging.info(f"Using fallback text extraction for: {url}")
                return {
                    "title": page_title,
                    "text": fallback_text
                }, None
            else:
                 logging.error(f"Fallback failed to extract sufficient paragraph text (found {len(fallback_text)} chars) from: {url}")
                 original_error_msg = f"Newspaper3k error: {newspaper_err}"
                 return None, f"Could not extract substantial content using newspaper3k or basic parsing from: {url}. {original_error_msg}"

        except requests.exceptions.RequestException as req_e:
            logging.error(f"Requests fallback failed for {url}: {req_e}")
            error_detail = f"Error: {req_e}"
            status_code = getattr(getattr(req_e, 'response', None), 'status_code', None)
            if status_code == 403:
                 error_detail = "Access denied (403 Forbidden). Site likely uses advanced bot detection or requires login/subscription."
            elif status_code == 404: error_detail = "Page not found (404)."
            elif status_code: error_detail = f"HTTP Error {status_code}."
            final_error_msg = f"Failed to fetch article content from {url}. {error_detail}"
            if str(newspaper_err) not in final_error_msg: final_error_msg += f" (Initial newspaper error: {newspaper_err})"
            return None, final_error_msg
        except Exception as fallback_parse_err:
            logging.error(f"Fallback parsing failed for {url}: {fallback_parse_err}")
            return None, f"An error occurred during fallback content parsing for {url}. Error: {fallback_parse_err}"


def summarize_text(text, api_key):
    """
    Summarizes the given text using OpenAI API. Requests a more robust summary.
    Returns the summary text or None, error_message if fails.
    """
    logging.info("Attempting to summarize text...")
    if not text or len(text.strip()) < 150: # Increased minimum length for better summary
        logging.warning(f"Text too short ({len(text.strip())} chars) for robust summarization.")
        return "Content too short to summarize effectively.", None

    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that summarizes articles clearly and in detail."},
                # --- Updated Prompt for more robust summary ---
                {"role": "user", "content": f"Please provide a detailed summary of the following article content, covering the key points in about 5-7 sentences:\n\n{text}"}
            ],
            temperature=0.6, # Slightly higher for more elaborate summary
            max_tokens=400 # Increased max_tokens for longer summary
        )
        summary = response.choices[0].message.content.strip()
        logging.info("Successfully generated summary.")
        return summary, None
    except Exception as e:
        logging.error(f"Error calling OpenAI API for summarization: {e}")
        return None, f"Failed to summarize the text. OpenAI API error: {e}"


def generate_audio(text, api_key, base_filename_id, identifier, voice="alloy", speed=1.0):
    """
    Generates audio from text using OpenAI TTS API with specified voice and speed.
    Saves it to a unique file based on base_filename_id.
    Returns the path to the saved audio file or None, error_message if fails.
    """
    logging.info(f"Attempting to generate audio for: {base_filename_id}_{identifier} (Voice: {voice}, Speed: {speed})")
    if not text or not text.strip():
        logging.warning("No text provided for audio generation.")
        return None, "Cannot generate audio for empty text."

    # Ensure the base filename is safe using the helper
    safe_base_filename = get_valid_filename(base_filename_id)
    unique_filename = f"{safe_base_filename}_{identifier}_{voice}_{int(time.time())}.mp3" # Add voice to filename
    filepath = os.path.join(AUDIO_DIR, unique_filename)

    try:
        client = OpenAI(api_key=api_key)
        max_tts_chars = 4000
        if len(text) > max_tts_chars:
             logging.warning(f"Text for TTS exceeds {max_tts_chars} chars. Truncating.")
             text_to_speak = text[:max_tts_chars]
        else:
             text_to_speak = text

        response = client.audio.speech.create(
            model="tts-1",       # Consider tts-1-hd for higher quality if needed
            # --- Use passed voice and speed parameters ---
            voice=voice,
            speed=speed,
            # ---
            input=text_to_speak,
            response_format="mp3"
        )

        response.stream_to_file(filepath)

        if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
             logging.error(f"Audio file generation appeared successful but file is missing or empty: {filepath}")
             if os.path.exists(filepath): os.remove(filepath) # Cleanup empty file
             return None, "Failed to create a valid audio file."

        logging.info(f"Successfully generated audio and saved to: {filepath}")
        return filepath, None
    except Exception as e:
        logging.error(f"Error calling OpenAI API for TTS: {e}")
        if os.path.exists(filepath): # Cleanup potentially corrupted file
            try: os.remove(filepath)
            except OSError as rm_err: logging.error(f"Error removing potentially corrupt audio file {filepath}: {rm_err}")
        # Check for specific OpenAI errors if possible
        if "invalid voice" in str(e).lower():
            return None, f"Failed to generate audio: Invalid voice selected ('{voice}'). Please choose a valid voice."
        return None, f"Failed to generate audio. OpenAI API error: {e}"


def cleanup_audio_files(files_to_keep):
    """Removes audio files from AUDIO_DIR not in the list of files_to_keep."""
    # (This function remains the same as the previous correct version)
    logging.info(f"Running audio cleanup. Keeping: {files_to_keep}")
    if not os.path.exists(AUDIO_DIR):
        logging.warning(f"Audio directory {AUDIO_DIR} not found during cleanup.")
        return

    try:
        all_audio_files = [os.path.join(AUDIO_DIR, f) for f in os.listdir(AUDIO_DIR) if f.endswith(".mp3")]
        kept_files_count = 0
        removed_files_count = 0
        for f_path in all_audio_files:
            if f_path not in files_to_keep:
                try:
                    os.remove(f_path)
                    logging.info(f"Removed old audio file: {f_path}")
                    removed_files_count += 1
                except OSError as e:
                    logging.error(f"Error removing audio file {f_path}: {e}")
            else:
                kept_files_count += 1
        logging.info(f"Audio cleanup complete. Kept {kept_files_count} files, removed {removed_files_count} files.")

    except Exception as e:
        logging.error(f"Error during audio cleanup scan: {e}")
