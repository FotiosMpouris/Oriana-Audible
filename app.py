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

# --- Instructional Expander ---
with st.expander("ℹ️ How to Use Oriana & Important Notes"):
    st.markdown("""
    **Adding Articles:**
    *   **Via URL:** Paste the full web address (URL) of an online article and click "Add Article from URL".
        *   *Note:* Some websites (like those requiring login/subscription or using strong anti-bot measures) may block access, resulting in an error. Use the "Paste Text" method as a workaround.
    *   **Via Pasting Text:** Copy the article text from its source, paste it into the "Paste article text" box, provide a Title, and click "Add Manual Article". Use the "Clear" buttons to easily remove previous input.

    **Interacting with Articles:**
    *   Use the dropdown menu under "Your Articles" to select an article.
    *   Click "View Summary" to read the generated summary text.
    *   Click "▶️ Read Summary" or "▶️ Read Full" to generate audio. The app now uses **ElevenLabs** for higher quality audio, falling back to OpenAI if needed.
        *   **Audio Generation:** This calls APIs and may take time (especially for long articles or initial ElevenLabs calls). A spinner will appear.
        *   **Playback/Download:** Once generation finishes, the app reruns. **You may need to click the 'Read...' button again** to display the audio player and the **"⬇️ Download MP3"** button.
        *   **Download Button:** This is the most reliable way to play audio, especially on mobile, or to save it for later.

    **Audio Settings (Sidebar - Fallback):**
    *   The **Voice** and **Speed** selectors currently apply **only if the app needs to fall back to OpenAI TTS** (e.g., due to ElevenLabs quota). The primary ElevenLabs voice is set internally for now.
    *   *Note:* Even the fallback voices are primarily English-trained.

    **Important Notes:**
    *   **Persistence:** Audio files are **not saved permanently** between sessions. Use the Download button.
    *   **Language:** Summaries attempt to match the article language. TTS (audio) quality is best for English (both ElevenLabs and OpenAI fallback).
    *   **Costs:** This app now uses **OpenAI API (Summary)** and **ElevenLabs API (Primary TTS)** or **OpenAI API (Fallback TTS)**, each consuming credits/quota from the respective API keys. Monitor your usage.
    *   **Troubleshooting:** Check errors, API key status/quota. Use Download button if player fails.
    """)

# --- Constants & Options ---
MAX_ARTICLES = 5
# These voices are now primarily for the OpenAI FALLBACK
TTS_VOICES_OPENAI = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
TTS_SPEEDS_OPENAI = {"Normal": 1.0, "Slightly Faster": 1.15, "Faster": 1.25, "Fastest": 1.5}

# --- Check for API Keys ---
openai_api_key = None
elevenlabs_api_key = None
try:
    # Check OpenAI Key
    openai_api_key = st.secrets["openai"]["api_key"]
    if not openai_api_key or not openai_api_key.startswith("sk-"):
        raise ValueError("Invalid OpenAI API Key format or missing")
    # Check ElevenLabs Key
    elevenlabs_api_key = st.secrets["elevenlabs"]["api_key"]
    if not elevenlabs_api_key: # Basic check if key exists
         raise ValueError("ElevenLabs API Key is missing")

except Exception as e:
    st.error(f"API key error in Streamlit secrets: {e}. Please ensure secrets are configured correctly for both [openai] and [elevenlabs] sections.")
    st.stop() # Stop execution if keys are invalid

# --- Initialize Session State ---
st.session_state.setdefault('articles', [])
st.session_state.setdefault('selected_article_id', None)
st.session_state.setdefault('processing', False)
# These now control the FALLBACK OpenAI voice/speed
st.session_state.setdefault('selected_voice_openai', TTS_VOICES_OPENAI[0])
st.session_state.setdefault('selected_speed_openai', TTS_SPEEDS_OPENAI["Normal"])
# Input field states
st.session_state.setdefault('url_input', "")
st.session_state.setdefault('manual_title_input', "")
st.session_state.setdefault('manual_text_input', "")
# Processing state helpers
st.session_state.setdefault('processing_target', None)
st.session_state.setdefault('manual_data', None)
st.session_state.setdefault('last_process_success', None)
st.session_state.setdefault('last_process_error', None)


# --- Callback Functions for Clearing Inputs ---
def clear_url_callback(): st.session_state.url_input = ""
def clear_title_callback(): st.session_state.manual_title_input = ""
def clear_text_callback(): st.session_state.manual_text_input = ""

# --- Helper functions ---
def get_article_index(article_id):
    for i, article in enumerate(st.session_state.articles):
        if article.get('id') == article_id: return i
    return -1

def get_active_audio_paths():
    paths = set()
    for article in st.session_state.articles:
        for key in ['full_audio_path', 'summary_audio_path']:
             path = article.get(key)
             if path and os.path.exists(path): paths.add(path)
    return paths

def create_manual_id(title):
    # (Same robust ID creation logic as before)
    if title and title.strip():
        sanitized = re.sub(r'\W+', '_', title.strip().lower())
        base_id = f"manual_{sanitized[:50]}"; existing_ids = {a['id'] for a in st.session_state.articles}
        final_id = base_id; count = 1
        while final_id in existing_ids: final_id = f"{base_id}_{count}"; count += 1
        return final_id
    else:
        base_id = f"manual_{int(time.time())}"; existing_ids = {a['id'] for a in st.session_state.articles}
        final_id = base_id; count = 1
        while final_id in existing_ids: final_id = f"{base_id}_{count}"; count += 1
        return final_id


# --- Sidebar Audio Settings (Now Primarily for OpenAI Fallback) ---
st.sidebar.header("Audio Settings (for OpenAI Fallback)")
st.session_state.selected_voice_openai = st.sidebar.selectbox(
    "Fallback Voice:", options=TTS_VOICES_OPENAI,
    index=TTS_VOICES_OPENAI.index(st.session_state.selected_voice_openai),
    key="voice_selector_openai",
    help="Select the voice used if ElevenLabs fails or quota is exceeded."
)
# Find user-friendly name for current fallback speed
current_speed_name_openai = [k for k, v in TTS_SPEEDS_OPENAI.items() if v == st.session_state.selected_speed_openai][0]
selected_speed_name_openai = st.sidebar.select_slider(
    "Fallback Speed:", options=list(TTS_SPEEDS_OPENAI.keys()),
    value=current_speed_name_openai,
    key="speed_selector_openai",
    help="Select the speed used if ElevenLabs fails or quota is exceeded."
)
st.session_state.selected_speed_openai = TTS_SPEEDS_OPENAI[selected_speed_name_openai] # Store float value
st.sidebar.info("Primary audio uses ElevenLabs (default voice). These settings apply to the OpenAI fallback.")


# --- Main Input Area ---
# (Input Tabs and Add button logic remain the same, using callbacks for Clear)
st.header("Add New Article")
tab1, tab2 = st.tabs(["Add via URL", "Add by Pasting Text"])
with tab1:
    col_url_input, col_url_clear = st.columns([4, 1])
    with col_url_input: st.text_input("URL Input:", key="url_input", label_visibility="collapsed", placeholder="Enter URL", disabled=st.session_state.processing)
    with col_url_clear: st.button("Clear URL", key="clear_url_btn", help="Clear URL input", on_click=clear_url_callback, disabled=st.session_state.processing)
    add_url_button = st.button("Add Article from URL", key="add_url", disabled=st.session_state.processing or not st.session_state.url_input)
    if add_url_button:
        url_to_add = st.session_state.url_input
        if len(st.session_state.articles) >= MAX_ARTICLES: st.warning(f"Max {MAX_ARTICLES} articles.")
        elif any(a.get('id') == url_to_add for a in st.session_state.articles): st.warning("URL already added.")
        else: st.session_state.processing = True; st.session_state.processing_target = url_to_add; st.rerun()
with tab2:
    col_title_input, col_title_clear = st.columns([4, 1])
    with col_title_input: st.text_input("Title Input:", key="manual_title_input", label_visibility="collapsed", placeholder="Enter Title", disabled=st.session_state.processing)
    with col_title_clear: st.button("Clear Title", key="clear_title_btn", help="Clear Title", on_click=clear_title_callback, disabled=st.session_state.processing)
    col_text_input, col_text_clear = st.columns([4, 1])
    with col_text_input: st.text_area("Text Input:", height=200, key="manual_text_input", label_visibility="collapsed", placeholder="Paste article text", disabled=st.session_state.processing)
    with col_text_clear: st.button("Clear Text", key="clear_text_btn", help="Clear Text", on_click=clear_text_callback, disabled=st.session_state.processing)
    add_manual_button = st.button("Add Manual Article", key="add_manual", disabled=st.session_state.processing or not st.session_state.manual_text_input or not st.session_state.manual_title_input)
    if add_manual_button:
         if len(st.session_state.articles) >= MAX_ARTICLES: st.warning(f"Max {MAX_ARTICLES} articles.")
         else:
            manual_id = create_manual_id(st.session_state.manual_title_input)
            st.session_state.manual_data = {"title": st.session_state.manual_title_input, "text": st.session_state.manual_text_input, "id": manual_id}
            st.session_state.processing = True; st.session_state.processing_target = manual_id; st.rerun()

# --- Processing Logic ---
# (This block remains the same - it adds article data to state)
if st.session_state.processing:
    target_id = st.session_state.get('processing_target')
    is_manual = target_id and target_id.startswith("manual_")
    spinner_msg = f"Processing {target_id[:60]}..." if target_id else "Processing..."
    success_msg, error_msg = None, None
    new_article_data = None
    with st.spinner(spinner_msg):
        try:
            if is_manual:
                m_data = st.session_state.get("manual_data")
                if m_data and m_data.get('text'):
                    summary, s_err = summarize_text(m_data['text'], openai_api_key)
                    new_article_data = {'id': m_data['id'], 'title': m_data['title'], 'full_text': m_data['text'], 'summary': summary, 'error': s_err, 'is_manual': True, 'full_audio_path': None, 'summary_audio_path': None}
                    if s_err: error_msg = f"Summary Error: {s_err}"
                    else: success_msg = f"Manual article '{m_data['title']}' added."
                else: error_msg = "Manual data missing."
            else: # URL Processing
                url = target_id
                if url:
                    content, f_err = fetch_article_content(url)
                    if f_err or not content: error_msg = f"URL Error: {f_err or 'No content.'}"
                    else:
                        summary, s_err = summarize_text(content['text'], openai_api_key)
                        new_article_data = {'id': url, 'title': content['title'], 'full_text': content['text'], 'summary': summary, 'error': f_err or s_err, 'is_manual': False, 'full_audio_path': None, 'summary_audio_path': None}
                        if s_err: error_msg = f"Summary Error: {s_err}"
                        if not f_err and not s_err: success_msg = f"Article '{content['title']}' added."
                        elif f_err: error_msg = f"URL Fetch Error: {f_err}" # Prioritize fetch error msg
                else: error_msg = "URL target missing."
            if new_article_data:
                st.session_state.articles.append(new_article_data)
                st.session_state.selected_article_id = new_article_data['id']
                cleanup_audio_files(get_active_audio_paths())
        except Exception as e: error_msg = f"Unexpected processing error: {e}"; logging.error(f"Processing Error: {e}", exc_info=True)
        finally: # Reset state and store messages for display after rerun
            st.session_state.processing = False; st.session_state.processing_target = None; st.session_state.manual_data = None
            st.session_state.last_process_success = success_msg; st.session_state.last_process_error = error_msg
            st.rerun()

# --- Display Processing Results ---
# (This block remains the same)
if st.session_state.get('last_process_success'): st.success(st.session_state.pop('last_process_success'));
if st.session_state.get('last_process_error'): st.error(st.session_state.pop('last_process_error'));

# --- Display and Interact with Articles ---
st.header("Your Articles")
if not st.session_state.articles:
    st.info("No articles added yet.")
else:
    # Article Selection Dropdown (Remains the same)
    article_options = { a['id']: f"{a.get('title','Untitled')} ({'Pasted' if a.get('is_manual', False) else a.get('id', 'No ID')[:30]}...)" for a in st.session_state.articles }
    current_ids = list(article_options.keys())
    if st.session_state.selected_article_id not in current_ids: st.session_state.selected_article_id = current_ids[0] if current_ids else None
    selected_id = st.selectbox("Choose article:", options=current_ids, format_func=lambda id: article_options.get(id, "?"), index=current_ids.index(st.session_state.selected_article_id) if st.session_state.selected_article_id in current_ids else 0, key="article_selector", label_visibility="collapsed")
    if selected_id != st.session_state.selected_article_id: st.session_state.selected_article_id = selected_id; st.rerun()

    # --- Display Selected Article ---
    if st.session_state.selected_article_id:
        selected_index = get_article_index(st.session_state.selected_article_id)
        if selected_index != -1:
            article_data = st.session_state.articles[selected_index]
            st.subheader(f"{article_data.get('title', 'No Title')}")
            st.caption(f"Source: {'Pasted Text' if article_data.get('is_manual', False) else article_data.get('id', 'Unknown URL')}")
            if article_data.get('error') and not article_data.get('summary'): st.warning(f"Processing Note: {article_data['error']}")
            with st.expander("View Summary Text"): st.write(article_data.get('summary', "No summary."))

            # Action Buttons (Remains the same)
            col1, col2, col3 = st.columns([1, 1, 1])
            button_key_prefix = get_valid_filename(article_data.get('id', f'no_id_{selected_index}'))[:20]
            with col1: read_summary_button = st.button("▶️ Read Summary", key=f"sum_{button_key_prefix}", disabled=st.session_state.processing)
            with col2: read_full_button = st.button("▶️ Read Full", key=f"full_{button_key_prefix}", disabled=st.session_state.processing)
            with col3: delete_button = st.button("🗑️ Delete", key=f"del_{button_key_prefix}", disabled=st.session_state.processing)
            if len(article_data.get('full_text', '')) > 3500 and not read_full_button: col2.caption("⚠️ Full text long.")

            # --- Audio Handling Placeholders ---
            audio_player_placeholder = st.empty()
            audio_status_placeholder = st.empty()
            download_placeholder = st.empty()

            # --- handle_audio_request Function (UPDATED CALL SIGNATURE) ---
            def handle_audio_request(text_type, text_content):
                """Generates or retrieves audio, displays player/download."""
                audio_path_key = f"{text_type}_audio_path"
                audio_path = article_data.get(audio_path_key)
                audio_ready = False; audio_bytes = None

                # 1. Check for existing valid audio
                if audio_path and os.path.exists(audio_path):
                    try:
                        with open(audio_path, "rb") as f: audio_bytes = f.read()
                        if audio_bytes: audio_ready = True; audio_status_placeholder.success(f"Audio ready.")
                        else: os.remove(audio_path); st.session_state.articles[selected_index][audio_path_key] = None; audio_path = None; logging.warning("Removed empty audio file."); audio_status_placeholder.warning("Invalid audio file found.")
                    except Exception as e: audio_status_placeholder.warning(f"Load Error ({e}). Regen needed."); st.session_state.articles[selected_index][audio_path_key] = None; audio_path = None

                # 2. Generate audio if not ready
                if not audio_ready:
                    # Check validity before generation call
                    is_valid_summary = text_type == "summary" and text_content and text_content not in ["Summary could not be generated.", "Content too short to summarize effectively.", "Content too short to summarize."]
                    is_valid_full = text_type == "full" and text_content
                    if not (is_valid_summary or is_valid_full):
                        audio_status_placeholder.warning(f"No valid {text_type} text for audio."); return

                    audio_status_placeholder.info(f"Generating {text_type} audio...")
                    with st.spinner(f"Generating {text_type} audio..."):
                        try:
                            # --- UPDATED CALL TO mainfunctions.generate_audio ---
                            filepath, audio_error = generate_audio(
                                text=text_content,
                                elevenlabs_api_key=elevenlabs_api_key,  # Pass EL key
                                openai_api_key=openai_api_key,        # Pass OpenAI key
                                base_filename_id=article_data['id'],
                                identifier=text_type,
                                # Pass parameters for OpenAI fallback
                                voice_openai=st.session_state.selected_voice_openai,
                                speed_openai=st.session_state.selected_speed_openai
                            )
                            # --- END OF UPDATED CALL ---

                            if audio_error: audio_status_placeholder.error(f"Audio Error: {audio_error}"); st.session_state.articles[selected_index][audio_path_key] = None
                            elif filepath: st.session_state.articles[selected_index][audio_path_key] = filepath; st.rerun() # Rerun needed
                            else: audio_status_placeholder.error("Generation failed."); st.session_state.articles[selected_index][audio_path_key] = None
                            return # Exit after attempt
                        except Exception as e: audio_status_placeholder.error(f"Gen Error: {e}"); st.session_state.articles[selected_index][audio_path_key] = None; return

                # 3. Display controls if audio is ready
                if audio_ready and audio_bytes:
                    try: audio_player_placeholder.audio(audio_bytes, format="audio/mp3")
                    except Exception as player_e: audio_player_placeholder.warning(f"Player Error: {player_e}. Use Download.")
                    download_filename = f"{get_valid_filename(article_data['title'])}_{text_type}.mp3"
                    download_placeholder.download_button(f"⬇️ Download {text_type.capitalize()}", audio_bytes, download_filename, "audio/mpeg", key=f"dl_{button_key_prefix}_{text_type}")

            # --- Trigger Audio Handling ---
            # (This logic block remains the same)
            if read_summary_button: handle_audio_request("summary", article_data.get('summary'))
            elif read_full_button: handle_audio_request("full", article_data.get('full_text'))
            else: # Proactively check existing
                 summary_path = article_data.get('summary_audio_path')
                 full_path = article_data.get('full_audio_path')
                 if summary_path and os.path.exists(summary_path): handle_audio_request("summary", article_data.get('summary'))
                 elif full_path and os.path.exists(full_path): handle_audio_request("full", article_data.get('full_text'))

            # --- Delete Logic ---
            # (This block remains the same)
            if delete_button:
                id_to_delete = article_data['id']; logging.info(f"Deleting: {id_to_delete}")
                index_to_delete = get_article_index(id_to_delete)
                if index_to_delete != -1:
                    deleted = st.session_state.articles.pop(index_to_delete); st.success(f"Deleted: '{deleted.get('title', 'Untitled')}'")
                    paths = [p for p in [deleted.get('full_audio_path'), deleted.get('summary_audio_path')] if p]
                    for path in paths:
                        if path and os.path.exists(path):
                            try: os.remove(path); logging.info(f"Deleted audio file: {path}")
                            except Exception as e: logging.error(f"Delete error {path}: {e}")
                    st.session_state.selected_article_id = None; audio_player_placeholder.empty(); audio_status_placeholder.empty(); download_placeholder.empty()
                    st.rerun()
                else: st.error("Could not find article to delete.")
