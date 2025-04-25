# app.py (Rewritten with ElevenLabs Integration)
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
# CSS for general layout and minor button adjustments
st.markdown("""
<style>
    /* Ensure columns have some minimal gap and standard buttons look consistent */
    .stButton>button {
        margin: 0.1rem 0;
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
    /* Style the embedded audio player slightly */
    audio {
        width: 100%; /* Make player responsive */
        margin-bottom: 0.5rem; /* Add space below player */
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
st.caption("Distilling text into summaries and audio narratives. Now with enhanced audio!")
st.divider() # Add a visual separator

# --- Instructional Expander ---
# Rewritten instructions with more sophisticated tone and revised Fallaci mention
with st.expander("💡 Oriana: Concept & Usage Guide", expanded=False): # Start collapsed
    st.markdown("""
    *In tribute to the relentless pursuit of truth exemplified by journalists like Oriana Fallaci, this application aims to make information more accessible by transforming written content.*

    Oriana allows you to condense lengthy articles or documents into concise summaries and convert them into spoken audio, enabling consumption during commutes, exercise, or any time your eyes need a rest. This version prioritizes high-quality audio generation via ElevenLabs, with OpenAI as a reliable fallback.

    **Workflow:**

    **1. Ingest Content:**

    *   **🌐 From the Web (URL):** Provide a direct link to an online article and select **"➕ Add Article from URL"**.
        *   *(Note: Success depends on the target website's structure and permissions. Direct text pasting is a reliable alternative if fetching fails.)*
    *   **✍️ From Clipboard (Paste Text):** Copy the desired text, paste it into the designated area, assign a **Title**, and select **"➕ Add Manual Article"**.
        *   *(Utilize the "Clear" buttons adjacent to input fields for quick resets.)*

    **2. Engage with the Article:**

    *   **Selection:** Choose an article from the **"Your Articles"** dropdown menu. The details will load below.
    *   **Review Summary:** Expand the **"📄 View Summary Text"** section to read the AI-generated synopsis.
    *   **Generate Audio:**
        *   First, configure your preferred **Fallback Voice (OpenAI)** and **Speed** via the sidebar settings. *(Note: The primary audio engine uses a default high-quality voice from ElevenLabs. Speed setting primarily affects the fallback engine).*
        *   Click **"▶️ Read Summary"** or **"▶️ Read Full"** to initiate audio synthesis.
        *   *(Process Alert: Audio generation, particularly for extensive texts requiring chunking, involves API calls (primarily ElevenLabs, potentially OpenAI) and may take several minutes. A progress indicator will be displayed.)*
    *   **Access Audio:** Upon completion, the app refreshes, revealing audio controls:
        *   **Embedded Player:** An audio player will appear directly within the app interface for immediate playback. While convenient, **performance on mobile devices or with exceptionally large audio files (many minutes long) might be inconsistent** due to browser memory and processing limitations.
        *   **⬇️ Download MP3:** This button provides the most dependable method to obtain the audio. It saves the generated MP3 file to your device, ensuring offline access and optimal playback regardless of file size or device constraints. **Highly recommended, especially for full articles or mobile usage.**

    **Key Considerations:**

    *   **Audio Persistence:** Generated audio files are ephemeral and exist only within your current browser session. **To retain audio, you must download the MP3.**
    *   **Language Nuances:** Summarization attempts to mirror the source language. TTS voices (both ElevenLabs and OpenAI) perform best with English; pronunciation of foreign words or non-English text may vary.
    *   **API Usage:** This application utilizes **ElevenLabs** and **OpenAI API services** for text-to-speech and summarization, incurring costs based on usage against the configured API keys. Fallback to OpenAI TTS occurs if ElevenLabs encounters specific issues (e.g., quota limits).
    *   **Troubleshooting:** If URL fetching encounters issues, resort to pasting text. If embedded playback is problematic, utilize the Download MP3 option.
    """)
st.divider() # Add a visual separator

# --- Constants & Options ---
MAX_ARTICLES = 5
TTS_VOICES_OPENAI = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"] # For Fallback
TTS_SPEEDS = {"Normal": 1.0, "Slightly Faster": 1.15, "Faster": 1.25, "Fastest": 1.5} # Primarily for Fallback
DEFAULT_ELEVENLABS_VOICE_ID = "KDImLuG6RkuyuX5httC7" # Example - Choose a preferred default voice ID

# --- Check for API Keys ---
# OpenAI API Key Check (Unchanged)
try:
    if "openai" not in st.secrets or "api_key" not in st.secrets["openai"]:
         raise KeyError("OpenAI API key not found in secrets.toml. Expected [openai] section with api_key.")
    openai_api_key = st.secrets["openai"]["api_key"]
    if not openai_api_key or not openai_api_key.startswith("sk-"):
        raise ValueError("Invalid OpenAI API Key format or missing value.")
except (KeyError, ValueError) as e:
    st.error(f"OpenAI API key configuration error in Streamlit secrets: {e}. Please ensure secrets.toml has `[openai]` section with `api_key = 'sk-...'` and it is valid.")
    st.stop()
except Exception as e:
     st.error(f"An unexpected error occurred reading OpenAI secrets: {e}")
     st.stop()

# ElevenLabs API Key Check (NEW)
try:
    if "elevenlabs" not in st.secrets or "api_key" not in st.secrets["elevenlabs"]:
         raise KeyError("ElevenLabs API key not found in secrets.toml. Expected [elevenlabs] section with api_key.")
    elevenlabs_api_key = st.secrets["elevenlabs"]["api_key"]
    if not elevenlabs_api_key: # Add more specific format checks if needed
        raise ValueError("ElevenLabs API Key value missing.")
except (KeyError, ValueError) as e:
    st.error(f"ElevenLabs API key configuration error in Streamlit secrets: {e}. Please ensure secrets.toml has `[elevenlabs]` section with `api_key = 'YOUR_KEY_HERE'` and it is valid.")
    st.stop()
except Exception as e:
     st.error(f"An unexpected error occurred reading ElevenLabs secrets: {e}")
     st.stop()

# --- Initialize Session State (Functional code unchanged, added default voice) ---
st.session_state.setdefault('articles', [])
st.session_state.setdefault('selected_article_id', None)
st.session_state.setdefault('processing', False)
st.session_state.setdefault('selected_voice_openai', TTS_VOICES_OPENAI[0]) # Renamed key for clarity
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

# --- Sidebar Audio Settings (Updated labels for clarity) ---
st.sidebar.header("🎧 Audio Settings")
#st.sidebar.info(f"Primary TTS uses ElevenLabs (Voice: {DEFAULT_ELEVENLABS_VOICE_ID}). Settings below apply to the OpenAI fallback.")
st.sidebar.info(f"Primary TTS uses ElevenLabs (Voice: Grace). Settings below apply to the OpenAI fallback.")
st.session_state.selected_voice_openai = st.sidebar.selectbox(
    "Select Fallback Voice (OpenAI):", options=TTS_VOICES_OPENAI,
    index=TTS_VOICES_OPENAI.index(st.session_state.selected_voice_openai),
    key="voice_selector_openai" # Updated key
)
current_speed_name = [k for k, v in TTS_SPEEDS.items() if v == st.session_state.selected_speed][0]
selected_speed_name = st.sidebar.select_slider(
    "Select Fallback Speed:", options=list(TTS_SPEEDS.keys()),
    value=current_speed_name,
    key="speed_selector"
)
st.session_state.selected_speed = TTS_SPEEDS[selected_speed_name]
st.sidebar.warning("Note: Both TTS engines perform best with English.")

# --- Main Input Area (Functional code unchanged) ---
st.subheader("Step 1: Add Article Content")
tab1, tab2 = st.tabs(["🌐 Add via URL", "✍️ Add by Pasting Text"])

with tab1:
    col_url_input, col_url_clear = st.columns([4, 1])
    with col_url_input:
        st.text_input("URL:", key="url_input", label_visibility="collapsed", placeholder="Enter URL of online article", disabled=st.session_state.processing)
    with col_url_clear:
        st.button("Clear", key="clear_url_btn", help="Clear the URL input field",
                  on_click=clear_url_callback, disabled=st.session_state.processing)

    add_url_button = st.button("➕ Add Article from URL", key="add_url", type="primary",
                               disabled=st.session_state.processing or not st.session_state.url_input)
    if add_url_button:
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

    add_manual_button = st.button("➕ Add Manual Article", key="add_manual", type="primary",
                                  disabled=st.session_state.processing or not st.session_state.manual_text_input or not st.session_state.manual_title_input)
    if add_manual_button:
         if len(st.session_state.articles) >= MAX_ARTICLES: st.warning(f"Maximum {MAX_ARTICLES} articles allowed.")
         else:
            manual_title = st.session_state.manual_title_input
            manual_text = st.session_state.manual_text_input
            manual_id = create_manual_id(manual_title)
            st.session_state.manual_data = {"title": manual_title, "text": manual_text, "id": manual_id}
            st.session_state.processing = True
            st.session_state.processing_target = manual_id
            st.rerun()

# --- Processing Logic (Summarization part unchanged) ---
if st.session_state.processing:
    target_id = st.session_state.get('processing_target')
    is_manual_processing = target_id and target_id.startswith("manual_")
    spinner_message = f"Processing {target_id[:60]}..." if target_id else "Processing..."
    process_success_message = None
    process_error_msg = None

    with st.spinner(spinner_message):
        article_data_to_add = None
        try:
            # Fetch & Summarize Logic (remains the same, uses only OpenAI API key)
            if is_manual_processing:
                manual_data = st.session_state.get("manual_data")
                if manual_data and manual_data.get('text'):
                    summary, summary_error = summarize_text(manual_data['text'], openai_api_key) # Still uses OpenAI key
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
                        summary, summary_error = summarize_text(content_data['text'], openai_api_key) # Still uses OpenAI key
                        if summary is None and summary_error: final_summary, combined_error = None, f"Fetch OK. Summarization failed: {summary_error}"
                        elif summary_error: final_summary, combined_error = summary, f"Fetch OK. Summary note: {summary_error}"
                        else: final_summary, combined_error = summary, None
                        final_processing_error = fetch_error or combined_error
                        article_data_to_add = {'id': url_to_process, 'title': content_data['title'], 'full_text': content_data['text'], 'summary': final_summary, 'error': final_processing_error, 'is_manual': False, 'full_audio_path': None, 'summary_audio_path': None}
                        if fetch_error: process_error_msg = f"URL Fetch Error: {fetch_error}"
                        elif final_processing_error and final_summary is None: process_error_msg = f"Summarization error: {summary_error}"
                        elif not final_processing_error: process_success_message = f"Article '{content_data['title']}' processed."
                else: process_error_msg = "Error: No URL target found for processing."

            # Add article data to session state (unchanged)
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
    st.success(f"✅ {st.session_state.last_process_success}")
    del st.session_state.last_process_success
if 'last_process_error' in st.session_state and st.session_state.last_process_error:
    st.error(f"❌ {st.session_state.last_process_error}")
    del st.session_state.last_process_error
if 'last_process_warning' in st.session_state and st.session_state.last_process_warning:
     st.warning(f"⚠️ {st.session_state.last_process_warning}")
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
        "Choose article:",
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

            st.subheader(f"📄 {article_data.get('title', 'No Title')}")
            st.caption(f"Source: {'Manually Pasted Text' if article_data.get('is_manual', False) else article_data.get('id', 'Unknown URL')}")
            if article_data.get('error'):
                 st.warning(f"Processing Note: {article_data['error']}")

            with st.expander("🧐 View Summary Text"):
                 summary_text_display = article_data.get('summary')
                 if summary_text_display: st.write(summary_text_display)
                 else: st.info("No summary could be generated for this article.")

            st.markdown("**Generate Audio:**")
            col1, col2, col3 = st.columns([1, 1, 1])
            button_key_prefix = get_valid_filename(article_data.get('id', f'no_id_{selected_index}'))[:20]

            with col1:
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
                 delete_button = st.button("🗑️ Delete Article", key=f"del_{button_key_prefix}",
                                           disabled=st.session_state.processing)

            st.divider()

            # --- Audio Handling Placeholders (Unchanged) ---
            audio_status_placeholder = st.empty()
            audio_controls_placeholder = st.empty()

            # --- UPDATED handle_audio_request Function ---
            # Passes both API keys and selected fallback options to generate_audio
            def handle_audio_request(text_type, text_content):
                audio_path_key = f"{text_type}_audio_path"
                audio_path = article_data.get(audio_path_key)
                audio_ready = False
                audio_bytes = None

                # 1. Check cache (Unchanged)
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

                # 2. Generate if needed (Updated call to generate_audio)
                if not audio_ready:
                    is_valid_summary = text_type == "summary" and text_content
                    is_valid_full = text_type == "full" and text_content
                    if not (is_valid_summary or is_valid_full):
                         audio_status_placeholder.warning(f"No valid {text_type} text available to generate audio.")
                         return

                    audio_status_placeholder.info(f"Generating {text_type} audio (using ElevenLabs primary)... (May take time for long text)")
                    with st.spinner(f"Generating {text_type} audio... This can take a while for long articles."):
                        try:
                            # **MODIFIED CALL:** Pass both keys and relevant voice/speed settings
                            filepath, audio_error = generate_audio(
                                text=text_content,
                                openai_api_key=openai_api_key,        # Pass OpenAI key for potential fallback
                                elevenlabs_api_key=elevenlabs_api_key,# Pass ElevenLabs key for primary attempt
                                base_filename_id=article_data['id'],
                                identifier=text_type,
                                elevenlabs_voice_id=DEFAULT_ELEVENLABS_VOICE_ID, # Pass default EL voice
                                openai_voice=st.session_state.selected_voice_openai, # Pass selected OpenAI voice for fallback
                                openai_speed=st.session_state.selected_speed       # Pass selected speed for fallback
                            )
                            if audio_error:
                                audio_status_placeholder.error(f"Audio Generation Error: {audio_error}")
                                st.session_state.articles[selected_index][audio_path_key] = None
                            elif filepath:
                                st.session_state.articles[selected_index][audio_path_key] = filepath
                                st.rerun() # Rerun to update the UI and display controls
                            else:
                                audio_status_placeholder.error(f"{text_type.capitalize()} audio generation failed unexpectedly.")
                                st.session_state.articles[selected_index][audio_path_key] = None
                            return # Exit after generation attempt (success or fail)
                        except Exception as e:
                            audio_status_placeholder.error(f"Unexpected Generation Error: {e}")
                            logging.error(f"TTS Exception for {text_type} of {article_data['id']}: {e}", exc_info=True)
                            st.session_state.articles[selected_index][audio_path_key] = None
                            return # Exit after unexpected error

                # 3. Display Embedded Player and Download Button (Unchanged)
                if audio_ready and audio_bytes:
                    audio_status_placeholder.empty() # Clear status messages

                    col_player, col_download = audio_controls_placeholder.columns([3, 1])

                    with col_player:
                        try:
                            b64 = base64.b64encode(audio_bytes).decode()
                            audio_html = f"""
                            <audio controls>
                                <source src="data:audio/mpeg;base64,{b64}" type="audio/mpeg">
                                Your browser does not support the audio element. Please use the download button.
                            </audio>
                            """
                            col_player.markdown(audio_html, unsafe_allow_html=True)
                            col_player.caption("Playback within the app may struggle on mobile or with very long audio. Use Download if needed.")
                        except Exception as player_e:
                            col_player.error(f"Error displaying audio player: {player_e}. Please use the Download button.")

                    with col_download:
                        col_download.write("")
                        download_filename = f"{get_valid_filename(article_data['title'])}_{text_type}.mp3"
                        col_download.download_button(
                            label=f"⬇️ Download MP3",
                            data=audio_bytes,
                            file_name=download_filename,
                            mime="audio/mpeg",
                            key=f"dl_{button_key_prefix}_{text_type}",
                            help="Save the audio file to your device (Recommended)"
                        )

            # --- Trigger Audio Handling (Functional code unchanged) ---
            active_audio_request = None
            if read_summary_button: active_audio_request = ("summary", article_data.get('summary'))
            elif read_full_button: active_audio_request = ("full", article_data.get('full_text'))

            if active_audio_request:
                 handle_audio_request(active_audio_request[0], active_audio_request[1])
            else:
                 # Check if audio already exists and display it if no button was clicked
                 summary_audio_path = article_data.get('summary_audio_path')
                 full_audio_path = article_data.get('full_audio_path')
                 displayed_controls = False
                 # Prioritize showing summary audio if available
                 if summary_audio_path and os.path.exists(summary_audio_path):
                     handle_audio_request("summary", article_data.get('summary'))
                     displayed_controls = True
                 # If summary not shown, show full audio if available
                 if not displayed_controls and full_audio_path and os.path.exists(full_audio_path):
                     handle_audio_request("full", article_data.get('full_text'))


            # --- Delete Logic (Functional code unchanged) ---
            if delete_button:
                id_to_delete = article_data['id']
                logging.info(f"Attempting to delete article: {id_to_delete}")
                index_to_delete = get_article_index(id_to_delete)
                if index_to_delete != -1:
                    deleted_article_data = st.session_state.articles.pop(index_to_delete)
                    st.success(f"✅ Article '{deleted_article_data.get('title', 'Untitled')}' deleted.")
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
                else: st.error("❌ Could not find the article to delete (index mismatch). Please refresh.")

# --- End of Script ---
st.divider()
st.caption("Oriana App - v1.3 (ElevenLabs Integration)")
