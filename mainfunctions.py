# mainfunctions.py
import requests
from newspaper import Article as NewspaperArticle  # Renamed to avoid conflict
from openai import OpenAI
import streamlit as st
import time
import os
import logging
from urllib.parse import urlparse # To create valid filenames from URLs

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
    Returns a dictionary {'title': title, 'text': text} or None if fails.
    """
    logging.info(f"Attempting to fetch article from: {url}")
    if not is_valid_url(url):
        logging.error(f"Invalid URL format: {url}")
        return None, "Invalid URL format provided."
        
    try:
        article = NewspaperArticle(url)
        article.download()
        # Set a timeout for parsing to prevent hanging
        article.parse()
        
        if not article.text:
            logging.warning(f"Could not extract text from: {url}")
            # Try fetching with requests as a fallback for basic text
            try:
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'}
                response = requests.get(url, timeout=10, headers=headers)
                response.raise_for_status() # Raise an exception for bad status codes
                # Very basic extraction if newspaper fails
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(response.text, 'html.parser')
                paragraphs = soup.find_all('p')
                fallback_text = '\n'.join([p.get_text() for p in paragraphs])
                if fallback_text:
                     logging.info(f"Using fallback text extraction for: {url}")
                     return {
                         "title": article.title if article.title else url, 
                         "text": fallback_text
                     }, None
                else:
                     return None, f"Could not extract content using newspaper3k or basic parsing from: {url}"
            except requests.exceptions.RequestException as e:
                 logging.error(f"Requests fallback failed for {url}: {e}")
                 return None, f"Failed to fetch the article content after fallback attempt from {url}. Error: {e}"
            except Exception as e:
                 logging.error(f"Fallback parsing failed for {url}: {e}")
                 return None, f"An error occurred during fallback content parsing for {url}."

        logging.info(f"Successfully fetched title: '{article.title}' from {url}")
        return {
            "title": article.title if article.title else url, # Use URL as fallback title
            "text": article.text
        }, None # No error message

    except Exception as e:
        logging.error(f"Error fetching or parsing article {url}: {e}")
        return None, f"Failed to process the article from {url}. Error: {e}"

def summarize_text(text, api_key):
    """
    Summarizes the given text using OpenAI API.
    Returns the summary text or None if fails.
    """
    logging.info("Attempting to summarize text...")
    if not text:
        logging.warning("No text provided for summarization.")
        return None, "Cannot summarize empty text."
        
    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-3.5-turbo", # You can change the model if needed (e.g., "gpt-4")
            messages=[
                {"role": "system", "content": "You are a helpful assistant that summarizes articles concisely."},
                {"role": "user", "content": f"Please summarize the following article content:\n\n{text}"}
            ],
            temperature=0.5, # Adjust for creativity vs. factuality
            max_tokens=200 # Adjust based on desired summary length
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
    if not text:
        logging.warning("No text provided for audio generation.")
        return None, "Cannot generate audio for empty text."

    # Ensure the base filename is safe
    safe_base_filename = get_valid_filename(base_filename) # Use URL or title
    # Create a unique filename to avoid clashes
    unique_filename = f"{safe_base_filename}_{identifier}_{int(time.time())}.mp3"
    filepath = os.path.join(AUDIO_DIR, unique_filename)

    try:
        client = OpenAI(api_key=api_key)
        response = client.audio.speech.create(
            model="tts-1",       # Standard quality, faster
            # model="tts-1-hd",  # Higher quality, slower
            voice="alloy",     # Choose a voice: alloy, echo, fable, onyx, nova, shimmer
            input=text,
            response_format="mp3" # Specify mp3 format
        )

        # Stream the response to the file
        response.stream_to_file(filepath)

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
    try:
        all_audio_files = [os.path.join(AUDIO_DIR, f) for f in os.listdir(AUDIO_DIR) if f.endswith(".mp3")]
        for f in all_audio_files:
            if f not in files_to_keep:
                try:
                    os.remove(f)
                    logging.info(f"Removed old audio file: {f}")
                except OSError as e:
                    logging.error(f"Error removing audio file {f}: {e}")
    except Exception as e:
        logging.error(f"Error during audio cleanup: {e}")
