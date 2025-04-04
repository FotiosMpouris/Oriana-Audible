# app.py
import streamlit as st
from mainfunctions import (
    fetch_article_content,
    summarize_text,
    generate_audio,
    cleanup_audio_files,
    AUDIO_DIR,
    get_valid_filename # Now used for download filenames too
)
import os
import logging
import re
import time

# --- Page Configuration ---
st.set_page_config(
    page_title="Oriana - Article Summarizer & Reader",
    page_icon="✨",
    layout="wide"
)

# --- Application Title and Logo ---
LOGO_PATH = "orianalogo.png"
if os.path.exists(LOGO_PATH):
    st.image(LOGO_PATH, width=150)
else:
    st.warning("orianalogo.png not found.")

st.title("Oriana: Article Summarizer & Reader")
st.caption("Add articles via URL or paste text, get summaries, and listen or download!")
st.info("ℹ️ Audio generation happens per session. Audio files are not stored permanently.")


# --- Constants & Options ---
MAX_ARTICLES = 5
TTS_VOICES = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
TTS_SPEEDS = {"Normal": 1.0, "Slightly Faster": 1.15, "Faster": 1.25, "Fastest": 1.5} # User-friendly names

# --- Check for OpenAI API Key ---
try:
    openai_api_key = st.secrets["openai"]["api_key"]
    if not openai_api_key or not openai_api_key.startswith("sk-"):
        st.error("OpenAI API key is missing, invalid, or not configured correctly in secrets.")
        st.stop()
except KeyError:
    st.error("OpenAI API key section `[openai]` or key `api_key` not found in Streamlit secrets.")
    st.stop()
except Exception as e:
    st.error(f"An error occurred accessing secrets: {e}")
    st.stop()

# --- Initialize Session State ---
if 'articles' not in st.session_state:
    st.session_state.articles = []
    # {'id': str, 'title': str, 'full_text': str, 'summary': str,
    #  'full_audio_path': str|None, 'summary_audio_path': str|None,
    #  'error': str|None, 'is_manual': bool}
if 'selected_article_id' not in st.session_state:
    st.session_state.selected_article_id = None
if 'processing' not in st.session_state:
    st.session_state.processing = False
if 'selected_voice' not in st.session_state:
    st.session_state.selected_voice = TTS_VOICES[0] # Default voice
if 'selected_speed' not in st.session_state:
    st.session_state.selected_speed = TTS_SPEEDS["Normal"] # Default speed

# --- Helper functions ---
def get_article_index(article_id):
    for i, article in enumerate(st.session_state.articles):
        if article['id'] == article_id:
            return i
    return -1

def get_active_audio_paths():
    paths = set()
    for article in st.session_state.articles:
        for key in ['full_audio_path', 'summary_audio_path']:
             path = article.get(key)
             if path and os.path.exists(path):
                 paths.add(path)
    return paths

def create_manual_id(title):
    if title and title.strip():
         sanitized = re.sub(r'\W+', '_', title.strip().lower())
         return f"manual_{sanitized[:50]}"
    else:
         return f"manual_{int(time.time())}"

# --- Input Section ---
st.sidebar.header("Audio Settings")
st.session_state.selected_voice = st.sidebar.selectbox(
    "Select Voice:", options=TTS_VOICES,
    index=TTS_VOICES.index(st.session_state.selected_voice) # Keep selection
)
selected_speed_name = st.sidebar.select_slider(
    "Select Speed:", options=list(TTS_SPEEDS.keys()),
    value=[k for k, v in TTS_SPEEDS.items() if v == st.session_state.selected_speed][0] # Find key from value
)
st.session_state.selected_speed = TTS_SPEEDS[selected_speed_name]

st.header("Add New Article")
tab1, tab2 = st.tabs(["Add via URL", "Add by Pasting Text"])
# (Input Tab logic remains the same as previous version)
with tab1:
    new_url = st.text_input("Enter URL of the online article:", key="url_input", disabled=st.session_state.processing)
    add_url_button = st.button("Add Article from URL", key="add_url", disabled=st.session_state.processing or not new_url)
    if add_url_button and new_url:
        if len(st.session_state.articles) >= MAX_ARTICLES: st.warning(f"Max {MAX_ARTICLES} articles allowed.")
        elif any(article['id'] == new_url for article in st.session_state.articles): st.warning("URL already added.")
        else:
            st.session_state.processing = True
            st.session_state.processing_target = new_url
            st.rerun()
with tab2:
    manual_title = st.text_input("Enter a Title:", key="manual_title_input", disabled=st.session_state.processing)
    manual_text = st.text_area("Paste article text:", height=250, key="manual_text_input", disabled=st.session_state.processing)
    add_manual_button = st.button("Add Manual Article", key="add_manual", disabled=st.session_state.processing or not manual_text or not manual_title)
    if add_manual_button and manual_text and manual_title:
        if len(st.session_state.articles) >= MAX_ARTICLES: st.warning(f"Max {MAX_ARTICLES} articles allowed.")
        else:
            manual_id = create_manual_id(manual_title)
            if any(article['id'] == manual_id for article in st.session_state.articles): manual_id = f"{manual_id}_{int(time.time())}"
            if any(article['id'] == manual_id for article in st.session_state.articles): st.warning("Similar title exists. Modify title.")
            else:
                 st.session_state.processing = True
                 st.session_state.processing_target = manual_id
                 st.session_state.manual_data = {"title": manual_title, "text": manual_text, "id": manual_id}
                 st.rerun()

# --- Processing Logic ---
# (Remains the same as previous version - handles URL and Manual)
if st.session_state.processing:
    target_id = st.session_state.get('processing_target')
    is_manual_processing = target_id and target_id.startswith("manual_")
    spinner_message = "Processing..."
    # (Spinner message logic...)

    with st.spinner(spinner_message):
        article_data_to_add = None
        try:
            if is_manual_processing:
                manual_data = st.session_state.get("manual_data")
                if manual_data:
                    article_title = manual_data['title']
                    article_text = manual_data['text']
                    article_id = manual_data['id']
                    summary, summary_error = summarize_text(article_text, openai_api_key) # Get robust summary
                    if summary_error:
                        st.error(f"Summarization Error: {summary_error}")
                        summary = "Summary could not be generated."
                    article_data_to_add = {'id': article_id, 'title': article_title, 'full_text': article_text, 'summary': summary, 'full_audio_path': None, 'summary_audio_path': None, 'error': summary_error, 'is_manual': True}
                    st.success(f"Manual article '{article_title}' added!")
                else: st.error("Error retrieving manual data.")
            else: # Process URL
                url_to_process = target_id
                if url_to_process:
                    content_data, fetch_error = fetch_article_content(url_to_process)
                    if fetch_error or not content_data:
                        st.error(f"URL Processing Error: {fetch_error or 'Could not retrieve content.'}")
                    else:
                        article_title = content_data['title']
                        article_text = content_data['text']
                        summary, summary_error = summarize_text(article_text, openai_api_key) # Robust summary
                        if summary_error:
                            st.error(f"Summarization Error: {summary_error}")
                            summary = "Summary could not be generated."
                        article_data_to_add = {'id': url_to_process, 'title': article_title, 'full_text': article_text, 'summary': summary, 'full_audio_path': None, 'summary_audio_path': None, 'error': fetch_error or summary_error, 'is_manual': False}
                        st.success(f"Article '{article_title}' added!")
                else: st.error("Error: No URL target found.")

            if article_data_to_add:
                 st.session_state.articles.append(article_data_to_add)
                 st.session_state.selected_article_id = article_data_to_add['id']
                 cleanup_audio_files(get_active_audio_paths())

        except Exception as e:
            st.error(f"Unexpected processing error: {e}")
            logging.error(f"Processing error for {target_id}: {e}", exc_info=True)
        finally:
            st.session_state.processing = False
            st.session_state.processing_target = None
            st.session_state.manual_data = None
            st.rerun()


# --- Display and Interact with Articles ---
st.header("Your Articles")
if not st.session_state.articles:
    st.info("No articles added yet.")
else:
    article_options = { a['id']: f"{a['title']} ({'Pasted' if a['is_manual'] else a['id'][:30]}...)" for a in st.session_state.articles }
    current_ids = list(article_options.keys())
    if st.session_state.selected_article_id not in current_ids:
         st.session_state.selected_article_id = current_ids[0] if current_ids else None

    selected_id = st.selectbox(
        "Choose article:",
        options=current_ids,
        format_func=lambda article_id: article_options.get(article_id, "Unknown"),
        index=current_ids.index(st.session_state.selected_article_id) if st.session_state.selected_article_id in current_ids else 0,
        key="article_selector"
    )
    if selected_id != st.session_state.selected_article_id:
        st.session_state.selected_article_id = selected_id
        st.rerun()

    if st.session_state.selected_article_id:
        selected_index = get_article_index(st.session_state.selected_article_id)
        if selected_index != -1:
            article_data = st.session_state.articles[selected_index]
            st.subheader(f"Selected: {article_data['title']}")
            st.caption(f"Source: {'Pasted Text' if article_data['is_manual'] else article_data['id']}")
            if article_data.get('error') and not article_data['is_manual']: st.warning(f"Processing Note: {article_data['error']}")

            with st.expander("View Summary"): st.write(article_data['summary'] or "No summary.")

            col1, col2, col3 = st.columns([1, 1, 1])
            button_key_prefix = get_valid_filename(article_data['id'])[:20]

            with col1: read_summary_button = st.button("▶️ Read Summary", key=f"sum_{button_key_prefix}", disabled=st.session_state.processing)
            with col2: read_full_button = st.button("▶️ Read Full", key=f"full_{button_key_prefix}", disabled=st.session_state.processing)
            with col3: delete_button = st.button("🗑️ Delete", key=f"del_{button_key_prefix}", disabled=st.session_state.processing)
            if len(article_data.get('full_text', '')) > 3500 and not read_full_button: # Show warning proactively
                 col2.caption("⚠️ Full text long, audio may take time/fail.")


            # --- Audio Generation, Playback, and Download ---
            audio_player_placeholder = st.empty()
            audio_status_placeholder = st.empty()
            download_placeholder = st.empty()

            # Function to handle audio generation and state update
            def handle_audio_request(text_type, text_content):
                audio_path_key = f"{text_type}_audio_path" # 'summary_audio_path' or 'full_audio_path'
                audio_path = article_data.get(audio_path_key)

                # Check if valid audio exists
                if audio_path and os.path.exists(audio_path):
                     try:
                         with open(audio_path, "rb") as f: audio_bytes = f.read()
                         # Display Player
                         audio_player_placeholder.audio(audio_bytes, format="audio/mp3")
                         audio_status_placeholder.success(f"Playing {text_type} audio.")
                         # Display Download Button
                         download_filename = f"{get_valid_filename(article_data['title'])}_{text_type}.mp3"
                         download_placeholder.download_button(
                             label=f"⬇️ Download {text_type.capitalize()} MP3",
                             data=audio_bytes,
                             file_name=download_filename,
                             mime="audio/mpeg",
                             key=f"dl_{button_key_prefix}_{text_type}"
                         )
                         return True # Indicate success
                     except FileNotFoundError:
                         audio_status_placeholder.warning("Audio file missing. Regenerating...")
                         st.session_state.articles[selected_index][audio_path_key] = None
                         st.rerun()
                         return False
                     except Exception as e:
                         audio_status_placeholder.error(f"Error reading/playing audio: {e}")
                         return False
                else:
                     # Generate Audio
                     audio_status_placeholder.info(f"Generating {text_type} audio...")
                     with st.spinner(f"Generating {text_type} audio..."):
                         try:
                             filepath, audio_error = generate_audio(
                                 text_content,
                                 openai_api_key,
                                 article_data['id'],
                                 text_type,
                                 voice=st.session_state.selected_voice, # Use selected voice
                                 speed=st.session_state.selected_speed  # Use selected speed
                             )
                             if audio_error:
                                 audio_status_placeholder.error(f"Could not generate {text_type} audio: {audio_error}")
                                 st.session_state.articles[selected_index][audio_path_key] = None
                             elif filepath:
                                 st.session_state.articles[selected_index][audio_path_key] = filepath
                                 st.rerun() # Rerun to trigger playback/download button display
                             else:
                                 audio_status_placeholder.error(f"{text_type.capitalize()} audio generation failed.")
                                 st.session_state.articles[selected_index][audio_path_key] = None
                             return False # Generation happened, but need rerun to play

                         except Exception as e:
                             audio_status_placeholder.error(f"Error during {text_type} audio generation: {e}")
                             logging.error(f"TTS failed for {text_type} of {article_data['id']}: {e}", exc_info=True)
                             st.session_state.articles[selected_index][audio_path_key] = None
                             return False


            # Trigger audio handling
            if read_summary_button:
                summary_text = article_data['summary']
                if summary_text and summary_text not in ["Summary could not be generated.", "Content too short to summarize effectively."]:
                    handle_audio_request("summary", summary_text)
                else:
                    audio_status_placeholder.warning("No summary available or content too short.")

            if read_full_button:
                full_text = article_data['full_text']
                if full_text:
                    handle_audio_request("full", full_text)
                else:
                    audio_status_placeholder.warning("No full article text available.")

            # Display existing audio player/download if button wasn't clicked this run
            # Check which audio was last generated or should be shown based on state
            # This part is tricky with Streamlit's rerun model. The handle_audio_request
            # function now includes showing the player/button if audio exists.

            # Delete Article Logic
            if delete_button:
                id_to_delete = article_data['id']
                logging.info(f"Attempting to delete article: {id_to_delete}")
                index_to_delete = get_article_index(id_to_delete)
                if index_to_delete != -1:
                    deleted_article_data = st.session_state.articles.pop(index_to_delete)
                    st.success(f"Article '{deleted_article_data['title']}' deleted.")
                    paths_to_delete = [p for p in [deleted_article_data.get('full_audio_path'), deleted_article_data.get('summary_audio_path')] if p]
                    for path in paths_to_delete:
                         if os.path.exists(path):
                             try: os.remove(path); logging.info(f"Deleted audio: {path}")
                             except OSError as e: logging.error(f"Error deleting audio {path}: {e}")
                    st.session_state.selected_article_id = None
                    # Clear placeholders on delete
                    audio_player_placeholder.empty()
                    audio_status_placeholder.empty()
                    download_placeholder.empty()
                    st.rerun()
                else:
                    st.error("Could not find article to delete.")
