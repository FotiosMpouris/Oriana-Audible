# app.py
import streamlit as st
from mainfunctions import (
    fetch_article_content,
    summarize_text,
    generate_audio,
    cleanup_audio_files,
    AUDIO_DIR,
    get_valid_filename
)
import os
import logging
import re
import time
# Note: langdetect is used in mainfunctions, no need to import here unless used directly

# --- Page Configuration ---
st.set_page_config(
    page_title="Oriana - Article Summarizer & Reader",
    page_icon="✨",
    layout="wide"
)

# --- Application Title and Logo ---
LOGO_PATH = "orianalogo.png"
if os.path.exists(LOGO_PATH): st.image(LOGO_PATH, width=150)
else: st.warning("orianalogo.png not found.")

st.title("Oriana: Article Summarizer & Reader")
st.caption("Add articles via URL or paste text, get summaries, and listen or download!")

# --- Instructional Expander ---
with st.expander("ℹ️ How to Use Oriana & Important Notes"):
    st.markdown("""
    **Adding Articles:**
    *   **Via URL:** Paste the full web address (URL) of an online article and click "Add Article from URL".
        *   *Note:* Some websites (like those requiring login/subscription or using strong anti-bot measures) may block access, resulting in an error.
    *   **Via Pasting Text:** Copy the article text from its source, paste it into the "Paste article text" box, provide a Title, and click "Add Manual Article".

    **Interacting with Articles:**
    *   Use the dropdown menu under "Your Articles" to select an article.
    *   Click "View Summary" to read the generated summary text.
    *   Click "▶️ Read Summary" or "▶️ Read Full" to generate audio using the settings in the sidebar.
        *   **Audio Generation:** This calls the OpenAI API and may take a few moments (especially for full articles). A spinner will appear.
        *   **Playback:** Once generated *in the current session*, the audio player *should* appear below the buttons. **Click the 'Read...' button again** to make the player/download button visible if it doesn't show immediately after the spinner disappears (this is due to how Streamlit reruns).
        *   **Download:** Use the "⬇️ Download MP3" button to save the audio file to your device. This is the most reliable way to play on mobile or save for later.
    *   **Audio Settings (Sidebar):** Choose a voice and playback speed *before* generating audio.

    **Important Notes:**
    *   **Persistence:** Audio files are **not saved permanently**. They only exist during your current browser session. If you close the app or it restarts, you will need to regenerate the audio. Use the Download button to save files.
    *   **Language Support:**
        *   **Summaries:** Oriana attempts to detect the language of the article and provide a summary *in that language* (e.g., Greek text should result in a Greek summary).
        *   **Audio (TTS):** The available voices (Alloy, Echo, etc.) are primarily **English-trained**. While they *may attempt* to read non-English text (like Greek), the pronunciation and accent may sound unnatural or incorrect. There are currently no specific non-English voices available in this app.
    *   **Costs:** Using this app makes calls to the OpenAI API (for summarization and audio generation), which consumes credits associated with the provided API key.
    *   **Troubleshooting:** If an article fails, try the "Paste Text" method. If audio fails, check the error message; ensure your API key is valid and has credits.
    """)

# --- Constants & Options ---
MAX_ARTICLES = 5
TTS_VOICES = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
TTS_SPEEDS = {"Normal": 1.0, "Slightly Faster": 1.15, "Faster": 1.25, "Fastest": 1.5}

# --- Check for OpenAI API Key ---
try: # (Same key check logic as before)
    openai_api_key = st.secrets["openai"]["api_key"]
    if not openai_api_key or not openai_api_key.startswith("sk-"): raise ValueError("Invalid API Key format")
except Exception as e:
    st.error(f"OpenAI API key error in secrets: {e}. Please ensure `[openai]` section with `api_key = 'sk-...'` exists and is valid.")
    st.stop()

# --- Initialize Session State ---
# (Initialize state keys as before, ensuring defaults are set)
if 'articles' not in st.session_state: st.session_state.articles = []
if 'selected_article_id' not in st.session_state: st.session_state.selected_article_id = None
if 'processing' not in st.session_state: st.session_state.processing = False
if 'selected_voice' not in st.session_state: st.session_state.selected_voice = TTS_VOICES[0]
if 'selected_speed' not in st.session_state: st.session_state.selected_speed = TTS_SPEEDS["Normal"]
# Initialize keys for input fields if they don't exist, needed for clear buttons
if 'url_input' not in st.session_state: st.session_state.url_input = ""
if 'manual_title_input' not in st.session_state: st.session_state.manual_title_input = ""
if 'manual_text_input' not in st.session_state: st.session_state.manual_text_input = ""


# --- Helper functions ---
# (get_article_index, get_active_audio_paths, create_manual_id remain the same)
def get_article_index(article_id): # ... as before ...
    for i, article in enumerate(st.session_state.articles):
        if article['id'] == article_id: return i
    return -1
def get_active_audio_paths(): # ... as before ...
    paths = set(); # ... logic to find existing paths ...
    return paths
def create_manual_id(title): # ... as before ...
    if title and title.strip(): sanitized = re.sub(r'\W+', '_', title.strip().lower()); return f"manual_{sanitized[:50]}"
    else: return f"manual_{int(time.time())}"

# --- Input Section ---
st.sidebar.header("Audio Settings")
st.session_state.selected_voice = st.sidebar.selectbox( "Select Voice:", options=TTS_VOICES, index=TTS_VOICES.index(st.session_state.selected_voice))
selected_speed_name = st.sidebar.select_slider( "Select Speed:", options=list(TTS_SPEEDS.keys()), value=[k for k, v in TTS_SPEEDS.items() if v == st.session_state.selected_speed][0])
st.session_state.selected_speed = TTS_SPEEDS[selected_speed_name]
st.sidebar.warning("Note: Voices are primarily English-trained and may not sound natural for other languages.") # Added TTS warning

st.header("Add New Article")
tab1, tab2 = st.tabs(["Add via URL", "Add by Pasting Text"])

with tab1:
    # --- URL Input with Clear Button ---
    col_url_input, col_url_clear = st.columns([4, 1])
    with col_url_input:
        new_url = st.text_input("Enter URL:", key="url_input", label_visibility="collapsed", placeholder="Enter URL of online article", disabled=st.session_state.processing)
    with col_url_clear:
        clear_url_button = st.button("Clear", key="clear_url", help="Clear the URL input field", disabled=st.session_state.processing)
        if clear_url_button:
            st.session_state.url_input = "" # Clear the state variable
            st.rerun() # Rerun to update the UI element

    add_url_button = st.button("Add Article from URL", key="add_url", disabled=st.session_state.processing or not st.session_state.url_input) # Check state key
    # (Add URL logic remains the same)
    if add_url_button and st.session_state.url_input: # Check state key
        if len(st.session_state.articles) >= MAX_ARTICLES: st.warning(f"Max {MAX_ARTICLES} articles.")
        elif any(article['id'] == st.session_state.url_input for article in st.session_state.articles): st.warning("URL already added.")
        else:
            st.session_state.processing = True
            st.session_state.processing_target = st.session_state.url_input
            st.rerun()

with tab2:
    # --- Manual Title Input with Clear Button ---
    col_title_input, col_title_clear = st.columns([4, 1])
    with col_title_input:
        manual_title = st.text_input("Enter Title:", key="manual_title_input", label_visibility="collapsed", placeholder="Enter a Title for the article", disabled=st.session_state.processing)
    with col_title_clear:
        clear_title_button = st.button("Clear", key="clear_title", help="Clear the Title field", disabled=st.session_state.processing)
        if clear_title_button:
            st.session_state.manual_title_input = ""
            st.rerun()

    # --- Manual Text Input with Clear Button ---
    col_text_input, col_text_clear = st.columns([4, 1])
    with col_text_input:
        manual_text = st.text_area("Paste text:", height=200, key="manual_text_input", label_visibility="collapsed", placeholder="Paste the full article text here", disabled=st.session_state.processing)
    with col_text_clear:
        clear_text_button = st.button("Clear", key="clear_text", help="Clear the Pasted Text field", disabled=st.session_state.processing)
        if clear_text_button:
            st.session_state.manual_text_input = ""
            st.rerun()

    add_manual_button = st.button("Add Manual Article", key="add_manual", disabled=st.session_state.processing or not st.session_state.manual_text_input or not st.session_state.manual_title_input) # Check state keys
    # (Add Manual logic remains the same)
    if add_manual_button and st.session_state.manual_text_input and st.session_state.manual_title_input: # Check state keys
         if len(st.session_state.articles) >= MAX_ARTICLES: st.warning(f"Max {MAX_ARTICLES} articles.")
         else:
            manual_id = create_manual_id(st.session_state.manual_title_input)
            if any(a['id'] == manual_id for a in st.session_state.articles): manual_id = f"{manual_id}_{int(time.time())}" # Make unique
            if any(a['id'] == manual_id for a in st.session_state.articles): st.warning("Similar title exists.")
            else:
                 st.session_state.processing = True
                 st.session_state.processing_target = manual_id
                 st.session_state.manual_data = {"title": st.session_state.manual_title_input, "text": st.session_state.manual_text_input, "id": manual_id}
                 st.rerun()


# --- Processing Logic ---
# (Remains the same as previous version - handles URL/Manual based on target_id)
if st.session_state.processing:
    target_id = st.session_state.get('processing_target')
    is_manual_processing = target_id and target_id.startswith("manual_")
    # (Spinner logic...)
    with st.spinner(f"Processing {target_id[:60]}..."):
        article_data_to_add = None
        try:
            if is_manual_processing:
                manual_data = st.session_state.get("manual_data")
                if manual_data:
                    # Process manual data, call summarize_text (which now detects lang)
                    summary, error = summarize_text(manual_data['text'], openai_api_key)
                    # Create article_data_to_add dict...
                    article_data_to_add = { # Simplified representation
                        'id': manual_data['id'], 'title': manual_data['title'], 'full_text': manual_data['text'],
                        'summary': summary, 'error': error, 'is_manual': True,
                        'full_audio_path': None, 'summary_audio_path': None
                    }
                    if error: st.error(f"Summarization error: {error}")
                    st.success(f"Manual article '{manual_data['title']}' added!")
                else: st.error("Manual data missing.")
            else: # Process URL
                url_to_process = target_id
                if url_to_process:
                    content_data, fetch_error = fetch_article_content(url_to_process)
                    if fetch_error or not content_data: st.error(f"URL Error: {fetch_error or 'No content.'}")
                    else:
                         # Process URL data, call summarize_text (which detects lang)
                         summary, summary_error = summarize_text(content_data['text'], openai_api_key)
                         # Create article_data_to_add dict...
                         article_data_to_add = { # Simplified representation
                            'id': url_to_process, 'title': content_data['title'], 'full_text': content_data['text'],
                            'summary': summary, 'error': fetch_error or summary_error, 'is_manual': False,
                            'full_audio_path': None, 'summary_audio_path': None
                         }
                         if summary_error: st.error(f"Summarization error: {summary_error}")
                         st.success(f"Article '{content_data['title']}' added!")
                else: st.error("URL target missing.")

            # Add to state if processed
            if article_data_to_add:
                 st.session_state.articles.append(article_data_to_add)
                 st.session_state.selected_article_id = article_data_to_add['id']
                 cleanup_audio_files(get_active_audio_paths())

        except Exception as e: st.error(f"Processing error: {e}"); logging.error(f"Processing error: {e}", exc_info=True)
        finally: # Reset state
            st.session_state.processing = False; st.session_state.processing_target = None; st.session_state.manual_data = None
            st.rerun()


# --- Display and Interact with Articles ---
st.header("Your Articles")
if not st.session_state.articles:
    st.info("No articles added yet.")
else: # (Article selection logic remains the same)
    article_options = { a['id']: f"{a['title']} ({'Pasted' if a['is_manual'] else a['id'][:30]}...)" for a in st.session_state.articles }
    current_ids = list(article_options.keys())
    if st.session_state.selected_article_id not in current_ids: st.session_state.selected_article_id = current_ids[0] if current_ids else None
    selected_id = st.selectbox("Choose article:", options=current_ids, format_func=lambda id: article_options.get(id, "Unknown"), index=current_ids.index(st.session_state.selected_article_id) if st.session_state.selected_article_id in current_ids else 0, key="article_selector")
    if selected_id != st.session_state.selected_article_id: st.session_state.selected_article_id = selected_id; st.rerun()

    if st.session_state.selected_article_id:
        selected_index = get_article_index(st.session_state.selected_article_id)
        if selected_index != -1:
            article_data = st.session_state.articles[selected_index]
            st.subheader(f"Selected: {article_data['title']}")
            st.caption(f"Source: {'Pasted Text' if article_data['is_manual'] else article_data['id']}")
            if article_data.get('error') and not article_data['is_manual']: st.warning(f"Processing Note: {article_data['error']}")

            with st.expander("View Summary"): st.write(article_data['summary'] or "No summary.")

            # --- Action Buttons ---
            col1, col2, col3 = st.columns([1, 1, 1])
            button_key_prefix = get_valid_filename(article_data['id'])[:20]
            with col1: read_summary_button = st.button("▶️ Read Summary", key=f"sum_{button_key_prefix}", disabled=st.session_state.processing)
            with col2: read_full_button = st.button("▶️ Read Full", key=f"full_{button_key_prefix}", disabled=st.session_state.processing)
            with col3: delete_button = st.button("🗑️ Delete", key=f"del_{button_key_prefix}", disabled=st.session_state.processing)
            if len(article_data.get('full_text', '')) > 3500 and not read_full_button: col2.caption("⚠️ Full text long.")

            # --- Audio Handling Placeholders ---
            audio_player_placeholder = st.empty()
            audio_status_placeholder = st.empty()
            download_placeholder = st.empty()

            # --- handle_audio_request Function (Key Logic) ---
            # (This function remains largely the same as previous version, handles generation, playback attempt, and download button)
            def handle_audio_request(text_type, text_content):
                audio_path_key = f"{text_type}_audio_path"
                audio_path = article_data.get(audio_path_key)

                if audio_path and os.path.exists(audio_path): # If audio exists
                     try:
                         with open(audio_path, "rb") as f: audio_bytes = f.read()
                         audio_player_placeholder.audio(audio_bytes, format="audio/mp3") # Try to play
                         audio_status_placeholder.success(f"Audio ready for {text_type}.")
                         download_filename = f"{get_valid_filename(article_data['title'])}_{text_type}.mp3"
                         download_placeholder.download_button(f"⬇️ Download {text_type.capitalize()}", audio_bytes, download_filename, "audio/mpeg", key=f"dl_{button_key_prefix}_{text_type}")
                         return True
                     except Exception as e:
                         audio_status_placeholder.warning(f"Could not load existing audio ({e}). Regenerating might be needed.")
                         st.session_state.articles[selected_index][audio_path_key] = None # Invalidate path
                         # Don't rerun automatically, let user click again if needed
                         return False
                else: # If audio needs generation
                     audio_status_placeholder.info(f"Generating {text_type} audio...")
                     with st.spinner(f"Generating {text_type} audio..."):
                         try:
                             filepath, audio_error = generate_audio(
                                 text_content, openai_api_key, article_data['id'], text_type,
                                 voice=st.session_state.selected_voice, speed=st.session_state.selected_speed
                             )
                             if audio_error: audio_status_placeholder.error(f"Audio Error: {audio_error}"); st.session_state.articles[selected_index][audio_path_key] = None
                             elif filepath: st.session_state.articles[selected_index][audio_path_key] = filepath; st.rerun() # Rerun needed to show player/download
                             else: audio_status_placeholder.error("Generation failed."); st.session_state.articles[selected_index][audio_path_key] = None
                             return False
                         except Exception as e:
                             audio_status_placeholder.error(f"Generation Error: {e}"); st.session_state.articles[selected_index][audio_path_key] = None
                             return False

            # --- Trigger Audio Handling ---
            if read_summary_button:
                summary_text = article_data['summary']
                if summary_text and summary_text not in ["Summary could not be generated.", "Content too short to summarize effectively."]:
                    handle_audio_request("summary", summary_text)
                else: audio_status_placeholder.warning("No summary available/valid.")
            elif read_full_button: # Use elif to prevent both triggering in one run if clicked fast
                full_text = article_data['full_text']
                if full_text: handle_audio_request("full", full_text)
                else: audio_status_placeholder.warning("No full text available.")
            else:
                 # --- If button wasn't clicked, check if audio exists and show download/player ---
                 # Check summary audio path
                 summary_audio_path = article_data.get('summary_audio_path')
                 if summary_audio_path and os.path.exists(summary_audio_path):
                     try:
                         with open(summary_audio_path, "rb") as f: audio_bytes = f.read()
                         # Don't auto-play, just show download button if exists and wasn't just generated
                         download_filename = f"{get_valid_filename(article_data['title'])}_summary.mp3"
                         download_placeholder.download_button(f"⬇️ Download Summary", audio_bytes, download_filename, "audio/mpeg", key=f"dl_{button_key_prefix}_summary_exist")
                     except Exception: pass # Ignore if reading fails here
                 # Check full audio path (only show one download button at a time ideally, maybe the last generated one?)
                 # For simplicity, let's only proactively show the download button if *requested* via handle_audio_request


            # --- Delete Logic ---
            # (Remains the same as previous version)
            if delete_button:
                id_to_delete = article_data['id']; logging.info(f"Deleting: {id_to_delete}")
                index_to_delete = get_article_index(id_to_delete)
                if index_to_delete != -1:
                    deleted = st.session_state.articles.pop(index_to_delete); st.success(f"Deleted: '{deleted['title']}'")
                    paths = [p for p in [deleted.get('full_audio_path'), deleted.get('summary_audio_path')] if p]
                    for path in paths: # Cleanup audio files
                        if os.path.exists(path): try: os.remove(path) except Exception as e: logging.error(f"Delete error {path}: {e}")
                    st.session_state.selected_article_id = None
                    audio_player_placeholder.empty(); audio_status_placeholder.empty(); download_placeholder.empty() # Clear UI elements
                    st.rerun()
                else: st.error("Could not find article to delete.")
