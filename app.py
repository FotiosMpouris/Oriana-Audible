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
import base64

# --- Page Configuration ---
st.set_page_config(
    page_title="Oriana - Article Summarizer & Reader",
    page_icon="✨",
    layout="wide"
)

# --- Custom CSS for Visual Enhancements ---
# Inject CSS to style the 'Try Play' link like a subtle button and add minor tweaks
st.markdown("""
<style>
    /* Style the 'Try Play' link to look like a secondary button */
    .play-link-button {
        display: inline-block;
        padding: 0.3rem 0.75rem; /* Slightly adjust padding */
        background-color: #f0f2f6; /* Light grey background */
        color: #31333F; /* Default text color */
        border: 1px solid rgba(49, 51, 63, 0.2); /* Subtle border */
        border-radius: 0.5rem; /* Match Streamlit button radius */
        text-decoration: none; /* Remove underline */
        margin: 0.1rem 0; /* Add vertical margin */
        font-weight: 400;
        font-size: 0.875rem; /* Match Streamlit button font size */
        text-align: center;
        transition: all 0.2s ease-in-out; /* Smooth transition on hover */
    }
    .play-link-button:hover {
        border-color: #ff4b4b; /* Streamlit primary color border on hover */
        color: #ff4b4b; /* Streamlit primary color text on hover */
        background-color: white; /* Slightly change background */
    }
    /* Ensure columns have some minimal gap */
    .stButton>button {
        margin: 0.1rem 0; /* Add slight margin to regular buttons too */
    }
    /* Center the logo and title */
    div[data-testid="stImage"] {
        text-align: center;
        display: block;
        margin-left: auto;
        margin-right: auto;
        width: 150px; /* Explicit width */
    }
     h1[data-testid="stHeading"] {
        text-align: center;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px; /* Add more space between tabs */
    }

</style>
""", unsafe_allow_html=True)


# --- Application Title and Logo ---
LOGO_PATH = "orianalogo.png"
if os.path.exists(LOGO_PATH):
    st.image(LOGO_PATH, width=150) # Width set here, CSS centers
else:
    st.warning("orianalogo.png not found.")

st.title("✨ Oriana: Article Summarizer & Reader ✨")
st.caption("Turn text into summaries and audio effortlessly.")
st.divider() # Add a visual separator

# --- Instructional Expander ---
# Updated instructions with Oriana Fallaci mention and simplified flow
with st.expander("💡 How to Use Oriana & Important Notes", expanded=False): # Start collapsed
    st.markdown("""
    *Inspired by the spirit of journalists like Oriana Fallaci who sought the core of the story, Oriana helps you access information more easily.*

    Got long articles or documents? Oriana summarizes them and reads them aloud!

    **1. Add Your Content:**

    *   **🌐 Via URL:** Paste a web link, click **"➕ Add Article from URL"**.
        *   *(Note: Some sites block automated fetching. If it fails, use the Paste Text option.)*
    *   **✍️ Via Pasting Text:** Copy text, paste it in, add a **Title**, click **"➕ Add Manual Article"**.
        *   *(Use the "Clear..." buttons to reset fields.)*

    **2. Explore & Listen:**

    *   **Choose:** Select an article from the **"Your Articles"** dropdown.
    *   **Summarize:** Expand **"View Summary Text"** to read the AI-generated key points.
    *   **Generate Audio:**
        *   Choose a **Voice** and **Speed** in the sidebar first.
        *   Click **"▶️ Read Summary"** or **"▶️ Read Full"**.
        *   *(Audio generation takes time, especially for long text. A spinner will appear.)*
    *   **Get Audio:** Once ready, controls appear below the action buttons:
        *   <span class="play-link-button" style="cursor:default; background-color: #e9e9eb;">▶️ Try Playing Directly</span>: Attempts to play in browser/app (best effort, may fail on mobile/large files).
        *   <button style="pointer-events: none; background-color: #f0f2f6; border: 1px solid rgba(49, 51, 63, 0.2); color: #31333F; border-radius: 0.5rem; padding: 0.3rem 0.75rem; font-size: 0.875rem;">⬇️ Download MP3</button>: **Most reliable way.** Saves the file to your device. **Recommended.**

    **Important Points:**

    *   **Audio is Temporary:** Files exist only during your current session. **Download to keep!**
    *   **Language:** Summaries try to match the article language. TTS voices are English-optimized (pronunciation of other languages may vary).
    *   **API Costs:** Uses OpenAI API credits.
    *   **Troubleshooting:** URL fail? Paste text. Play fail? Download!
    """)
st.divider() # Add a visual separator

# --- Constants & Options ---
MAX_ARTICLES = 5
TTS_VOICES = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
TTS_SPEEDS = {"Normal": 1.0, "Slightly Faster": 1.15, "Faster": 1.25, "Fastest": 1.5}

# --- Check for OpenAI API Key (Functional code unchanged) ---
try:
    if "openai" not in st.secrets or "api_key" not in st.secrets["openai"]:
         raise KeyError("OpenAI API key not found in secrets.toml. Expected [openai] section with api_key.")
    openai_api_key = st.secrets["openai"]["api_key"]
    if not openai_api_key or not openai_api_key.startswith("sk-"):
        raise ValueError("Invalid API Key format or missing value.")
except (KeyError, ValueError) as e:
    st.error(f"OpenAI API key configuration error in Streamlit secrets: {e}. Please ensure secrets.toml has `[openai]` section with `api_key = 'sk-...'` and it is valid.")
    st.stop()
except Exception as e:
     st.error(f"An unexpected error occurred reading secrets: {e}")
     st.stop()

# --- Initialize Session State (Functional code unchanged) ---
st.session_state.setdefault('articles', [])
st.session_state.setdefault('selected_article_id', None)
st.session_state.setdefault('processing', False)
st.session_state.setdefault('selected_voice', TTS_VOICES[0])
st.session_state.setdefault('selected_speed', TTS_SPEEDS["Normal"])
st.session_state.setdefault('url_input', "")
st.session_state.setdefault('manual_title_input', "")
st.session_state.setdefault('manual_text_input', "")
st.session_state.setdefault('processing_target', None)
st.session_state.setdefault('manual_data', None)

# --- Callback Functions for Clearing Inputs (Functional code unchanged) ---
def clear_url_callback():
    st.session_state.url_input = ""
def clear_title_callback():
    st.session_state.manual_title_input = ""
def clear_text_callback():
    st.session_state.manual_text_input = ""

# --- Helper functions (Functional code unchanged) ---
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
    if title and title.strip():
         sanitized = re.sub(r'\W+', '_', title.strip().lower())
         base_id = f"manual_{sanitized[:50]}"
    else: base_id = f"manual_{int(time.time())}"
    existing_ids = {a['id'] for a in st.session_state.articles}
    final_id = base_id; count = 1
    while final_id in existing_ids:
        final_id = f"{base_id}_{count}"; count += 1
    return final_id

# --- Sidebar Audio Settings (Functional code unchanged) ---
st.sidebar.header("🎧 Audio Settings")
st.session_state.selected_voice = st.sidebar.selectbox(
    "Select Voice:", options=TTS_VOICES,
    index=TTS_VOICES.index(st.session_state.selected_voice),
    key="voice_selector"
)
current_speed_name = [k for k, v in TTS_SPEEDS.items() if v == st.session_state.selected_speed][0]
selected_speed_name = st.sidebar.select_slider(
    "Select Speed:", options=list(TTS_SPEEDS.keys()),
    value=current_speed_name,
    key="speed_selector"
)
st.session_state.selected_speed = TTS_SPEEDS[selected_speed_name]
st.sidebar.warning("Note: Voices are primarily English-trained.")

# --- Main Input Area ---
st.subheader("Step 1: Add Article Content")
# Use icons in tabs
tab1, tab2 = st.tabs(["🌐 Add via URL", "✍️ Add by Pasting Text"])

with tab1:
    col_url_input, col_url_clear = st.columns([4, 1])
    with col_url_input:
        st.text_input("URL:", key="url_input", label_visibility="collapsed", placeholder="Enter URL of online article", disabled=st.session_state.processing)
    with col_url_clear:
        # Add icon to clear button? Maybe not standard. Keep simple.
        st.button("Clear", key="clear_url_btn", help="Clear the URL input field",
                  on_click=clear_url_callback, disabled=st.session_state.processing)

    # Make Add button primary and add icon
    add_url_button = st.button("➕ Add Article from URL", key="add_url", type="primary",
                               disabled=st.session_state.processing or not st.session_state.url_input)
    if add_url_button: # Logic unchanged
        url_to_add = st.session_state.url_input
        if len(st.session_state.articles) >= MAX_ARTICLES: st.warning(f"Maximum {MAX_ARTICLES} articles allowed.")
        elif any(a.get('id') == url_to_add for a in st.session_state.articles): st.warning("This URL has already been added.")
        else:
            st.session_state.processing = True
            st.session_state.processing_target = url_to_add
            st.rerun()

with tab2:
    col_title_input, col_title_clear = st.columns([4, 1])
    with col_title_input:
        st.text_input("Title:", key="manual_title_input", label_visibility="collapsed", placeholder="Enter a Title for the article", disabled=st.session_state.processing)
    with col_title_clear:
        st.button("Clear", key="clear_title_btn", help="Clear the Title field",
                  on_click=clear_title_callback, disabled=st.session_state.processing)

    col_text_input, col_text_clear = st.columns([4, 1])
    with col_text_input:
        st.text_area("Pasted Text:", height=200, key="manual_text_input", label_visibility="collapsed", placeholder="Paste the full article text here", disabled=st.session_state.processing)
    with col_text_clear:
        st.button("Clear", key="clear_text_btn", help="Clear the Pasted Text field",
                  on_click=clear_text_callback, disabled=st.session_state.processing)

    # Make Add button primary and add icon
    add_manual_button = st.button("➕ Add Manual Article", key="add_manual", type="primary",
                                  disabled=st.session_state.processing or not st.session_state.manual_text_input or not st.session_state.manual_title_input)
    if add_manual_button: # Logic unchanged
         if len(st.session_state.articles) >= MAX_ARTICLES: st.warning(f"Maximum {MAX_ARTICLES} articles allowed.")
         else:
            manual_title = st.session_state.manual_title_input
            manual_text = st.session_state.manual_text_input
            manual_id = create_manual_id(manual_title)
            st.session_state.manual_data = {"title": manual_title, "text": manual_text, "id": manual_id}
            st.session_state.processing = True
            st.session_state.processing_target = manual_id
            st.rerun()

# --- Processing Logic (Functional code unchanged) ---
if st.session_state.processing:
    target_id = st.session_state.get('processing_target')
    is_manual_processing = target_id and target_id.startswith("manual_")
    spinner_message = f"Processing {target_id[:60]}..." if target_id else "Processing..."
    process_success_message = None
    process_error_msg = None

    with st.spinner(spinner_message):
        article_data_to_add = None
        try:
            if is_manual_processing:
                manual_data = st.session_state.get("manual_data")
                if manual_data and manual_data.get('text'):
                    summary, summary_error = summarize_text(manual_data['text'], openai_api_key)
                    if summary is None and summary_error: final_summary, final_error = None, f"Summarization failed: {summary_error}"
                    elif summary_error: final_summary, final_error = summary, f"Processing note: {summary_error}"
                    else: final_summary, final_error = summary, None
                    article_data_to_add = {'id': manual_data['id'], 'title': manual_data['title'], 'full_text': manual_data['text'], 'summary': final_summary, 'error': final_error, 'is_manual': True, 'full_audio_path': None, 'summary_audio_path': None}
                    if final_error and final_summary is None: process_error_msg = final_error
                    elif not final_error: process_success_message = f"Manual article '{manual_data['title']}' processed."
                else: process_error_msg = "Error retrieving valid manual data for processing."
            else:
                url_to_process = target_id
                if url_to_process:
                    content_data, fetch_error = fetch_article_content(url_to_process)
                    if fetch_error or not content_data: process_error_msg = f"URL Processing Error: {fetch_error or 'Could not retrieve content.'}"
                    else:
                        summary, summary_error = summarize_text(content_data['text'], openai_api_key)
                        if summary is None and summary_error: final_summary, combined_error = None, f"Fetch OK. Summarization failed: {summary_error}"
                        elif summary_error: final_summary, combined_error = summary, f"Fetch OK. Summary note: {summary_error}"
                        else: final_summary, combined_error = summary, None
                        final_processing_error = fetch_error or combined_error
                        article_data_to_add = {'id': url_to_process, 'title': content_data['title'], 'full_text': content_data['text'], 'summary': final_summary, 'error': final_processing_error, 'is_manual': False, 'full_audio_path': None, 'summary_audio_path': None}
                        if fetch_error: process_error_msg = f"URL Fetch Error: {fetch_error}"
                        elif final_processing_error and final_summary is None: process_error_msg = f"Summarization error: {summary_error}"
                        elif not final_processing_error: process_success_message = f"Article '{content_data['title']}' processed."
                else: process_error_msg = "Error: No URL target found for processing."
            if article_data_to_add:
                 if not any(a['id'] == article_data_to_add['id'] for a in st.session_state.articles):
                      st.session_state.articles.append(article_data_to_add)
                      st.session_state.selected_article_id = article_data_to_add['id']
                      cleanup_audio_files(get_active_audio_paths())
                 else:
                      process_warning_msg = f"Article with ID '{article_data_to_add['id']}' already exists, skipping add."
                      logging.warning(process_warning_msg)
                      st.session_state.last_process_warning = process_warning_msg
        except Exception as e:
            process_error_msg = f"An unexpected error occurred during processing: {e}"
            logging.error(f"Unexpected error processing {target_id}: {e}", exc_info=True)
        finally:
             st.session_state.processing = False
             st.session_state.processing_target = None
             st.session_state.manual_data = None
             st.session_state.last_process_success = process_success_message
             st.session_state.last_process_error = process_error_msg
             st.rerun()

# --- Display Processing Results (Functional code unchanged) ---
if 'last_process_success' in st.session_state and st.session_state.last_process_success:
    st.success(st.session_state.last_process_success)
    del st.session_state.last_process_success
if 'last_process_error' in st.session_state and st.session_state.last_process_error:
    st.error(st.session_state.last_process_error)
    del st.session_state.last_process_error
if 'last_process_warning' in st.session_state and st.session_state.last_process_warning:
     st.warning(st.session_state.last_process_warning)
     del st.session_state.last_process_warning

st.divider() # Add separator

# --- Display and Interact with Articles ---
st.subheader("Step 2: Interact with Your Articles")
if not st.session_state.articles:
    st.info("No articles added yet. Use Step 1 above.")
else:
    # Article Selection Dropdown (Functional code unchanged)
    article_options = { a['id']: f"{a['title']} ({'Pasted' if a.get('is_manual', False) else a.get('id', 'Unknown ID')[:30]}...)" for a in st.session_state.articles }
    current_ids = list(article_options.keys())
    if st.session_state.selected_article_id not in current_ids:
        st.session_state.selected_article_id = current_ids[0] if current_ids else None

    selected_id = st.selectbox(
        "Choose article:", # Simplified label
        options=current_ids,
        format_func=lambda article_id: article_options.get(article_id, "Unknown Article"),
        index=current_ids.index(st.session_state.selected_article_id) if st.session_state.selected_article_id in current_ids else 0,
        key="article_selector",
        label_visibility="collapsed"
    )
    if selected_id != st.session_state.selected_article_id:
        st.session_state.selected_article_id = selected_id
        st.rerun()

    # --- Display Selected Article Details and Actions ---
    if st.session_state.selected_article_id:
        selected_index = get_article_index(st.session_state.selected_article_id)
        if selected_index != -1:
            article_data = st.session_state.articles[selected_index]

            st.subheader(f"{article_data.get('title', 'No Title')}")
            st.caption(f"Source: {'Manually Pasted Text' if article_data.get('is_manual', False) else article_data.get('id', 'Unknown URL')}")
            if article_data.get('error'):
                 st.warning(f"Processing Note: {article_data['error']}")

            with st.expander("📄 View Summary Text"): # Add icon
                 summary_text_display = article_data.get('summary')
                 if summary_text_display: st.write(summary_text_display)
                 else: st.info("No summary could be generated for this article.")

            st.markdown("**Generate Audio:**") # Add sub-heading for clarity
            col1, col2, col3 = st.columns([1, 1, 1])
            button_key_prefix = get_valid_filename(article_data.get('id', f'no_id_{selected_index}'))[:20]

            with col1:
                # Add icons to buttons
                read_summary_button = st.button(
                    "▶️ Read Summary", key=f"sum_{button_key_prefix}",
                    disabled=st.session_state.processing or not article_data.get('summary')
                )
                if not article_data.get('summary'): col1.caption("(Summary unavailable)")

            with col2:
                 read_full_button = st.button(
                      "▶️ Read Full", key=f"full_{button_key_prefix}",
                      disabled=st.session_state.processing or not article_data.get('full_text')
                 )
                 full_text_len = len(article_data.get('full_text', ''))
                 if full_text_len > 4000 and not read_full_button: col2.caption("⚠️ Full text is long.")
                 elif not article_data.get('full_text'): col2.caption("(Full text unavailable)")

            with col3:
                 # Use secondary type for delete to make it less prominent? Optional.
                 delete_button = st.button("🗑️ Delete Article", key=f"del_{button_key_prefix}",
                                           disabled=st.session_state.processing)

            st.divider() # Separate actions from controls

            # --- Audio Handling Placeholders ---
            audio_status_placeholder = st.empty()
            audio_controls_placeholder = st.empty()

            # --- handle_audio_request Function (Functional code unchanged, but uses CSS class) ---
            def handle_audio_request(text_type, text_content):
                audio_path_key = f"{text_type}_audio_path"
                audio_path = article_data.get(audio_path_key)
                audio_ready = False
                audio_bytes = None
                play_link_html = ""

                if audio_path and os.path.exists(audio_path):
                    try:
                        with open(audio_path, "rb") as f: audio_bytes = f.read()
                        if audio_bytes: audio_ready = True
                        else:
                             os.remove(audio_path)
                             st.session_state.articles[selected_index][audio_path_key] = None
                             audio_path = None
                             logging.warning(f"Removed empty audio file: {audio_path}")
                             audio_status_placeholder.warning("Previous audio file was invalid. Please generate again.")
                    except Exception as e:
                        audio_status_placeholder.warning(f"Could not load existing audio file ({e}). Regenerating might be needed.")
                        st.session_state.articles[selected_index][audio_path_key] = None
                        audio_path = None

                if not audio_ready:
                    is_valid_summary = text_type == "summary" and text_content
                    is_valid_full = text_type == "full" and text_content
                    if not (is_valid_summary or is_valid_full):
                         audio_status_placeholder.warning(f"No valid {text_type} text available to generate audio.")
                         return

                    audio_status_placeholder.info(f"Generating {text_type} audio... (May take time for long text)")
                    with st.spinner(f"Generating {text_type} audio... This can take a while for long articles."):
                        try:
                            filepath, audio_error = generate_audio(text_content, openai_api_key, article_data['id'], text_type, voice=st.session_state.selected_voice, speed=st.session_state.selected_speed)
                            if audio_error:
                                audio_status_placeholder.error(f"Audio Generation Error: {audio_error}")
                                st.session_state.articles[selected_index][audio_path_key] = None
                            elif filepath:
                                st.session_state.articles[selected_index][audio_path_key] = filepath
                                st.rerun()
                            else:
                                audio_status_placeholder.error(f"{text_type.capitalize()} audio generation failed unexpectedly.")
                                st.session_state.articles[selected_index][audio_path_key] = None
                            return
                        except Exception as e:
                            audio_status_placeholder.error(f"Unexpected Generation Error: {e}")
                            logging.error(f"TTS Exception for {text_type} of {article_data['id']}: {e}", exc_info=True)
                            st.session_state.articles[selected_index][audio_path_key] = None
                            return

                if audio_ready and audio_bytes:
                    audio_status_placeholder.empty()
                    try:
                        b64 = base64.b64encode(audio_bytes).decode()
                        # Apply the CSS class here!
                        play_link_html = f'<a href="data:audio/mpeg;base64,{b64}" target="_blank" class="play-link-button" download="{get_valid_filename(article_data["title"])}_{text_type}.mp3">▶️ Try Playing Directly</a>'
                    except Exception as e:
                        logging.error(f"Error creating Base64 play link: {e}")
                        play_link_html = "<i>Error creating play link.</i>"

                    col_play, col_download = audio_controls_placeholder.columns([1, 1])
                    with col_play:
                        col_play.markdown(play_link_html, unsafe_allow_html=True)
                        col_play.caption("(Opens in new tab/player)") # Simplified caption
                    with col_download:
                        download_filename = f"{get_valid_filename(article_data['title'])}_{text_type}.mp3"
                        col_download.download_button(
                            label=f"⬇️ Download MP3", data=audio_bytes, file_name=download_filename, mime="audio/mpeg",
                            key=f"dl_{button_key_prefix}_{text_type}", help="Save the audio file to your device (Recommended)" # Add tooltip
                        )

            # --- Trigger Audio Handling (Functional code unchanged) ---
            active_audio_request = None
            if read_summary_button: active_audio_request = ("summary", article_data.get('summary'))
            elif read_full_button: active_audio_request = ("full", article_data.get('full_text'))
            if active_audio_request: handle_audio_request(active_audio_request[0], active_audio_request[1])
            else:
                 summary_audio_path = article_data.get('summary_audio_path')
                 full_audio_path = article_data.get('full_audio_path')
                 displayed_controls = False
                 if summary_audio_path and os.path.exists(summary_audio_path):
                     handle_audio_request("summary", article_data.get('summary'))
                     displayed_controls = True
                 if not displayed_controls and full_audio_path and os.path.exists(full_audio_path):
                     handle_audio_request("full", article_data.get('full_text'))

            # --- Delete Logic (Functional code unchanged) ---
            if delete_button:
                id_to_delete = article_data['id']
                logging.info(f"Attempting to delete article: {id_to_delete}")
                index_to_delete = get_article_index(id_to_delete)
                if index_to_delete != -1:
                    deleted_article_data = st.session_state.articles.pop(index_to_delete)
                    st.success(f"Article '{deleted_article_data.get('title', 'Untitled')}' deleted.")
                    paths_to_delete = [deleted_article_data.get('full_audio_path'), deleted_article_data.get('summary_audio_path')]
                    for path in paths_to_delete:
                        if path and isinstance(path, str) and os.path.exists(path):
                            try:
                                os.remove(path); logging.info(f"Deleted associated audio file: {path}")
                            except Exception as e: logging.error(f"Error deleting audio file {path}: {e}")
                    st.session_state.selected_article_id = None
                    audio_status_placeholder.empty()
                    audio_controls_placeholder.empty()
                    st.rerun()
                else: st.error("Could not find the article to delete (index mismatch). Please refresh.")

# --- End of Script ---
st.divider()
st.caption("Oriana App - v1.1 (Visual Enhancements)")
