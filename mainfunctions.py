# mainfunctions.py
import requests
from newspaper import Article as NewspaperArticle, Config # Import Config
from openai import OpenAI
import streamlit as st
import time
import os
import logging
from urllib.parse import urlparse # To create valid filenames from URLs
from bs4 import BeautifulSoup # Make sure BeautifulSoup is imported for fallback

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Configuration ---
# Directory to store temporary audio files (Streamlit Cloud has ephemeral storage)
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

def get_valid_filename(url):
    """Creates a safe filename from a URL."""
    parsed_url = urlparse(url)
    # Use netloc and path, replace invalid chars
    filename = f"{parsed_url.netloc}{parsed_url.path}".replace('/', '_').replace('\\', '_').replace(':', '_').replace('*', '_').replace('?', '_').replace('"', '_').replace('<', '_').replace('>', '_').replace('|', '_')
    # Limit length to avoid issues
    max_len = 100
    return filename[:max_len]

# --- Core Functions ---

def fetch_article_content(url):
    """
    Fetches and extracts the main content and title of an article from a URL.
    Returns a dictionary {'title': title, 'text': text} or None, error_message if fails.
    """
    logging.info(f"Attempting to fetch article from: {url}")
    if not is_valid_url(url):
        logging.error(f"Invalid URL format: {url}")
        return None, "Invalid URL format provided."

    # --- Define More Realistic Browser Headers ---
    browser_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36' # Slightly newer UA
    request_headers = {
        'User-Agent': browser_user_agent,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br', # Let requests handle decompression
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'DNT': '1', # Do Not Track
        # 'Referer': urlparse(url).scheme + "://" + urlparse(url).netloc + "/", # Sometimes adding a Referer helps, but can also cause issues. Uncomment cautiously.
    }

    try:
        # --- Configure newspaper3k ---
        config = Config()
        config.browser_user_agent = browser_user_agent # Use the same UA
        config.request_timeout = 15
        config.fetch_images = False # Keep disabled

        # --- Initialize Article with config ---
        # Note: newspaper3k might not use all headers from our dict, primarily UA
        article = NewspaperArticle(url, config=config)
        article.download() # This might still fail with 403
        article.parse()

        # Check if text is substantial enough
        if not article.text or len(article.text) < 50: # Added minimum length check
            logging.warning(f"Newspaper3k extracted minimal or no text ({len(article.text or '')} chars) from: {url}. Trying basic requests fallback.")
            raise ValueError("Newspaper3k failed to extract sufficient text.") # Raise exception to trigger fallback

        logging.info(f"Successfully fetched title: '{article.title}' from {url} using newspaper3k")
        return {
            "title": article.title if article.title else url, # Use URL as fallback title
            "text": article.text
        }, None

    # Catching specific exceptions can be better, but broad Exception first
    # Then try fallback for certain types of errors (like download/parse failures)
    except Exception as newspaper_err:
        logging.warning(f"Newspaper3k failed for {url}: {newspaper_err}. Trying basic requests fallback.")
        # --- Fallback using requests + BeautifulSoup with Enhanced Headers ---
        try:
            logging.info(f"Executing requests fallback for: {url} with enhanced headers.")
            # --- Use Enhanced Headers in Fallback Request ---
            response = requests.get(url, timeout=20, headers=request_headers) # Increased timeout slightly
            response.raise_for_status() # Still raise for bad status codes

            soup = BeautifulSoup(response.text, 'html.parser')

            # Try to get title from <title> tag
            page_title = url # Default title is URL
            if soup.title and soup.title.string:
                page_title = soup.title.string.strip()

            # Basic paragraph extraction - find main content area if possible
            main_content = soup.find('article') or soup.find('main') or soup.body # Fallback to body
            if main_content:
                paragraphs = main_content.find_all('p')
            else:
                 paragraphs = soup.find_all('p') # If no main area found, search all 'p' tags

            fallback_text = '\n'.join([p.get_text(" ", strip=True) for p in paragraphs if p.get_text(strip=True)]) # Added strip=True

            if fallback_text and len(fallback_text) > 50: # Check fallback text length too
                logging.info(f"Using fallback text extraction for: {url}")
                return {
                    "title": page_title,
                    "text": fallback_text
                }, None
            else:
                 logging.error(f"Fallback failed to extract sufficient paragraph text (found {len(fallback_text)} chars) from: {url}")
                 # Construct error message based on original error if possible
                 original_error_msg = f"Newspaper3k error: {newspaper_err}"
                 return None, f"Could not extract substantial content using newspaper3k or basic parsing from: {url}. {original_error_msg}"

        except requests.exceptions.RequestException as req_e:
            logging.error(f"Requests fallback failed for {url}: {req_e}")
            # Make error message more informative based on status code
            error_detail = f"Error: {req_e}"
            status_code = getattr(getattr(req_e, 'response', None), 'status_code', None)
            if status_code == 403:
                 error_detail = "Access denied (403 Forbidden). Site likely uses advanced bot detection (e.g., JavaScript checks, IP blocking) or requires login/subscription."
            elif status_code == 404:
                 error_detail = "Page not found (404)."
            elif status_code:
                 error_detail = f"HTTP Error {status_code}."

            final_error_msg = f"Failed to fetch article content from {url}. {error_detail}"
            # Include original newspaper error if different and informative
            if str(newspaper_err) not in final_error_msg:
                 final_error_msg += f" (Initial newspaper error: {newspaper_err})"

            return None, final_error_msg
        except Exception as fallback_parse_err:
            logging.error(f"Fallback parsing failed for {url}: {fallback_parse_err}")
            return None, f"An error occurred during fallback content parsing for {url}. Error: {fallback_parse_err}"


def summarize_text(text, api_key):
    """
    Summarizes the given text using OpenAI API.
    Returns the summary text or None if fails.
    """
    logging.info("Attempting to summarize text...")
    if not text or len(text.strip()) < 100: # Add length check here too
        logging.warning(f"Text too short ({len(text.strip())} chars) for meaningful summarization.")
        return "Content too short to summarize effectively.", None # Return message, no error

    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-3.5-turbo", # You can change the model if needed (e.g., "gpt-4")
            messages=[
                {"role": "system", "content": "You are a helpful assistant that summarizes articles concisely and accurately."},
                {"role": "user", "content": f"Please summarize the following article content in 2-4 clear sentences:\n\n{text}"} # Adjusted prompt
            ],
            temperature=0.5, # Adjust for creativity vs. factuality
            max_tokens=250 # Increased slightly for flexibility
        )
        summary = response.choices[0].message.content.strip()
        logging.info("Successfully generated summary.")
        return summary, None
    except Exception as e:
        logging.error(f"Error calling OpenAI API for summarization: {e}")
        return None, f"Failed to summarize the text. OpenAI API error: {e}"


def generate_audio(text, api_key, base_filename, identifier):
    """
    Generates audio from text using OpenAI TTS API and saves it to a unique file.
    Returns the path to the saved audio file or None if fails.
    """
    logging.info(f"Attempting to generate audio for: {base_filename}_{identifier}")
    if not text or not text.strip():
        logging.warning("No text provided for audio generation.")
        return None, "Cannot generate audio for empty text."

    # Ensure the base filename is safe
    safe_base_filename = get_valid_filename(base_filename) # Use URL or title
    # Create a unique filename to avoid clashes
    unique_filename = f"{safe_base_filename}_{identifier}_{int(time.time())}.mp3"
    filepath = os.path.join(AUDIO_DIR, unique_filename)

    try:
        client = OpenAI(api_key=api_key)
        # Ensure text isn't excessively long (OpenAI TTS has limits, ~4096 chars)
        # Simple truncation - better approach might be chunking, but adds complexity
        max_tts_chars = 4000
        if len(text) > max_tts_chars:
             logging.warning(f"Text for TTS exceeds {max_tts_chars} chars. Truncating.")
             text_to_speak = text[:max_tts_chars]
             # Optionally, add an indication that it was truncated
             # text_to_speak += "\n[Content truncated due to length limit for audio generation]"
        else:
             text_to_speak = text

        response = client.audio.speech.create(
            model="tts-1",       # Standard quality, faster
            # model="tts-1-hd",  # Higher quality, slower
            voice="alloy",     # Choose a voice: alloy, echo, fable, onyx, nova, shimmer
            input=text_to_speak,
            response_format="mp3" # Specify mp3 format
        )

        # Stream the response to the file
        response.stream_to_file(filepath)

        # Check if file was actually created and has size
        if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
             logging.error(f"Audio file generation appeared successful but file is missing or empty: {filepath}")
             # Clean up empty file if it exists
             if os.path.exists(filepath):
                 try:
                     os.remove(filepath)
                 except OSError:
                     pass # Ignore error during cleanup
             return None, "Failed to create a valid audio file."


        logging.info(f"Successfully generated audio and saved to: {filepath}")
        return filepath, None
    except Exception as e:
        logging.error(f"Error calling OpenAI API for TTS: {e}")
        # Clean up potentially corrupted file if creation failed mid-way
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except OSError as rm_err:
                 logging.error(f"Error removing potentially corrupt audio file {filepath}: {rm_err}")
        return None, f"Failed to generate audio. OpenAI API error: {e}"


def cleanup_audio_files(files_to_keep):
    """Removes audio files from AUDIO_DIR not in the list of files_to_keep."""
    logging.info(f"Running audio cleanup. Keeping: {files_to_keep}")
    if not os.path.exists(AUDIO_DIR):
        logging.warning(f"Audio directory {AUDIO_DIR} not found during cleanup.")
        return # Nothing to clean if directory doesn't exist

    try:
        all_audio_files = [os.path.join(AUDIO_DIR, f) for f in os.listdir(AUDIO_DIR) if f.endswith(".mp3")]
        kept_files_count = 0
        removed_files_count = 0
        for f_path in all_audio_files:
            # Check if the *full path* is in the set of paths to keep
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
