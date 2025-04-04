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
# Ensure this entire block is present
with st.expander("ℹ️ How to Use Oriana & Important Notes"):
    st.markdown("""
    **Adding Articles:**
    *   **Via URL:** Paste the full web address (URL) of an online article and click "Add Article from URL".
        *   *Note:* Some websites (like those requiring login/subscription or using strong anti-bot measures) may block access, resulting in an error. Use the "Paste Text" method as a workaround.
    *   **Via Pasting Text:** Copy the article text from its source, paste it into the "Paste article text" box, provide a Title, and click "Add Manual Article". Use the "Clear" buttons to easily remove previous input.

    **Interacting with Articles:**
    *   Use the dropdown menu under "Your Articles" to select an article.
    *   Click "View Summary" to read the generated summary text.
    *   Click "▶️ Read Summary" or "▶️ Read Full" to generate audio using the settings in the sidebar.
        *   **Audio Generation:** This calls the OpenAI API and may take a few moments (especially for full articles). A spinner will appear.
        *   **Playback/Download:** Once generation finishes, the app reruns. **You may need to click the 'Read...' button again** to display the audio player (if your browser supports it) and the essential **"⬇️ Download MP3"** button.
        *   **Download Button:** This is the most reliable way to play audio, especially on mobile, or to save it for later (e.g., listening in the car).

    **Audio Settings (Sidebar):**
    *   Choose a **Voice** and playback **Speed** *before* generating audio.
    *   *Note:* The voices are primarily English-trained and may not sound natural for other languages (like Greek).

    **Important Notes:**
    *   **Persistence:** Audio files are **not saved permanently** between sessions. They exist only while the app is running in your browser. Use the Download button to save files you want to keep.
    *   **Language:** Oriana tries to summarize in the article's original language. TTS (audio) works best for English.
    *   **Costs:** This app uses OpenAI API calls (summary, audio), consuming credits from the provided API key.
    *   **Troubleshooting:** If URL fetching fails, use Paste Text. If audio fails, check errors, API key status, and try again. Use the Download button if the player gives errors.
    """)

# --- Constants & Options ---
MAX_ARTICLES = 5
TTS_VOICES = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
TTS_SPEEDS = {"Normal": 1.0, "Slightly Faster": 1.15, "Faster": 1.25, "Fastest": 1.5}

# --- Check for OpenAI API Key ---
try:
    openai_api_key = st.secrets["openai"]["api_key"]
    if not openai_api_key or not openai_api_key.startswith("sk-"):
        raise ValueError("Invalid API Key format or missing")
except Exception as e:
    st.error(f"OpenAI API key error in Streamlit secrets: {e}. Please ensure `[openai]` section with `api_key = 'sk-...'` exists and is valid.")
    st.stop() # Stop execution if key is invalid

# --- Initialize Session State ---
# Using .setdefault is a concise way to initialize if key doesn't exist
st.session_state.setdefault('articles', [])
st.session_state.setdefault('selected_article_id', None)
st.session_state.setdefault('processing', False)
st.session_state.setdefault('selected_voice', TTS_VOICES[0])
st.session_state.setdefault('selected_speed', TTS_SPEEDS["Normal"])
# Ensure input field states are initialized for reliable clearing
st.session_state.setdefault('url_input', "")
st.session_state.setdefault('manual_title_input', "")
st.session_state.setdefault('manual_text_input', "")
st.session_state.setdefault('processing_target', None) # Track what's being processed
st.session_state.setdefault('manual_data', None) # Temp store for manual input data


# --- Callback Functions for Clearing Inputs ---
# These functions are called via on_click and modify state *before* rerun
def clear_url_callback():
    st.session_state.url_input = ""

def clear_title_callback():
    st.session_state.manual_title_input = ""

def clear_text_callback():
    st.session_state.manual_text_input = ""

# --- Helper functions ---
# Ensure these are present and correct
def get_article_index(article_id):
    """Finds the index of an article in the session state list by its ID."""
    for i, article in enumerate(st.session_state.articles):
        if article.get('id') == article_id:
            return i
    return -1 # Return -1 if not found

def get_active_audio_paths():
    """Gets a set of full paths for existing audio files stored in session state."""
    paths = set()
    for article in st.session_state.articles:
        for key in ['full_audio_path', 'summary_audio_path']:
             path = article.get(key)
             # Important: Check existence on disk as files are ephemeral
             if path and os.path.exists(path):
                 paths.add(path)
    return paths

def create_manual_id(title):
    """Creates a unique ID for manually added articles, handling potential collisions."""
    if title and title.strip():
         sanitized = re.sub(r'\W+', '_', title.strip().lower())
         base_id = f"manual_{sanitized[:50]}"
         existing_ids = {a['id'] for a in st.session_state.articles}
         final_id = base_id
         count = 1
         # Append count until unique ID is found
         while final_id in existing_ids:
             final_id = f"{base_id}_{count}"
             count += 1
         return final_id
    else: # Fallback if title is empty or only whitespace
         # Ensure this fallback is also unique if called multiple times quickly
         base_id = f"manual_{int(time.time())}"
         existing_ids = {a['id'] for a in st.session_state.articles}
         final_id = base_id
         count = 1
         while final_id in existing_ids:
             final_id = f"{base_id}_{count}"
             count += 1
         return final_id


# --- Sidebar Audio Settings ---
st.sidebar.header("Audio Settings")
st.session_state.selected_voice = st.sidebar.selectbox(
    "Select Voice:", options=TTS_VOICES,
    index=TTS_VOICES.index(st.session_state.selected_voice), # Maintain selection
    key="voice_selector" # Add key for stability
)
# Find the user-friendly name corresponding to the stored speed value
current_speed_name = [k for k, v in TTS_SPEEDS.items() if v == st.session_state.selected_speed][0]
selected_speed_name = st.sidebar.select_slider(
    "Select Speed:", options=list(TTS_SPEEDS.keys()),
    value=current_speed_name, # Set slider to current speed name
    key="speed_selector" # Add key for stability
)
st.session_state.selected_speed = TTS_SPEEDS[selected_speed_name] # Update state with the float value
st.sidebar.warning("Note: Voices are primarily English-trained.")

# --- Main Input Area ---
st.header("Add New Article")
tab1, tab2 = st.tabs(["Add via URL", "Add by Pasting Text"])

with tab1:
    # URL Input with Clear Button using Callback
    col_url_input, col_url_clear = st.columns([4, 1])
    with col_url_input:
        st.text_input("URL Input:", key="url_input", label_visibility="collapsed", placeholder="Enter URL of online article", disabled=st.session_state.processing)
    with col_url_clear:
        st.button("Clear URL", key="clear_url_btn", help="Clear the URL input field",
                  on_click=clear_url_callback, # Use callback
                  disabled=st.session_state.processing)

    add_url_button = st.button("Add Article from URL", key="add_url", disabled=st.session_state.processing or not st.session_state.url_input)
    if add_url_button: # Logic runs if button was true in the *previous* run
        url_to_add = st.session_state.url_input
        if len(st.session_state.articles) >= MAX_ARTICLES:
            st.warning(f"Maximum {MAX_ARTICLES} articles allowed.")
        elif any(article.get('id') == url_to_add for article in st.session_state.articles):
            st.warning("This URL has already been added.")
        else:
            st.session_state.processing = True
            st.session_state.processing_target = url_to_add
            st.rerun() # Initiate processing state

with tab2:
    # Manual Title Input with Clear Button using Callback
    col_title_input, col_title_clear = st.columns([4, 1])
    with col_title_input:
        st.text_input("Title Input:", key="manual_title_input", label_visibility="collapsed", placeholder="Enter a Title for the article", disabled=st.session_state.processing)
    with col_title_clear:
        st.button("Clear Title", key="clear_title_btn", help="Clear the Title field",
                  on_click=clear_title_callback, # Use callback
                  disabled=st.session_state.processing)

    # Manual Text Input with Clear Button using Callback
    col_text_input, col_text_clear = st.columns([4, 1])
    with col_text_input:
        st.text_area("Text Input:", height=200, key="manual_text_input", label_visibility="collapsed", placeholder="Paste the full article text here", disabled=st.session_state.processing)
    with col_text_clear:
        st.button("Clear Text", key="clear_text_btn", help="Clear the Pasted Text field",
                  on_click=clear_text_callback, # Use callback
                  disabled=st.session_state.processing)

    add_manual_button = st.button("Add Manual Article", key="add_manual", disabled=st.session_state.processing or not st.session_state.manual_text_input or not st.session_state.manual_title_input)
    if add_manual_button: # Logic runs if button was true in the *previous* run
         if len(st.session_state.articles) >= MAX_ARTICLES:
             st.warning(f"Maximum {MAX_ARTICLES} articles allowed.")
         else:
            # Ensure state has latest values before creating ID and data
            manual_title = st.session_state.manual_title_input
            manual_text = st.session_state.manual_text_input
            manual_id = create_manual_id(manual_title)
            # Store data needed for processing
            st.session_state.manual_data = {"title": manual_title, "text": manual_text, "id": manual_id}
            st.session_state.processing = True
            st.session_state.processing_target = manual_id
            st.rerun() # Initiate processing state

# --- Processing Logic ---
# This block runs when st.session_state.processing is True
if st.session_state.processing:
    target_id = st.session_state.get('processing_target')
    is_manual_processing = target_id and target_id.startswith("manual_")
    spinner_message = f"Processing {target_id[:60]}..." if target_id else "Processing..."
    process_success_message = None # Store success message
    process_error_msg = None # Store error message

    with st.spinner(spinner_message):
        article_data_to_add = None # Prepare dict for new article data
        try:
            if is_manual_processing:
                manual_data = st.session_state.get("manual_data")
                if manual_data and manual_data.get('text'): # Ensure text exists
                    summary, summary_error = summarize_text(manual_data['text'], openai_api_key)
                    article_data_to_add = {
                        'id': manual_data['id'], 'title': manual_data['title'], 'full_text': manual_data['text'],
                        'summary': summary, 'error': summary_error, 'is_manual': True,
                        'full_audio_path': None, 'summary_audio_path': None
                    }
                    if summary_error: process_error_msg = f"Summarization error: {summary_error}"
                    else: process_success_message = f"Manual article '{manual_data['title']}' processed."
                else: process_error_msg = "Error retrieving valid manual data for processing."
            else: # Process URL
                url_to_process = target_id
                if url_to_process:
                    content_data, fetch_error = fetch_article_content(url_to_process)
                    if fetch_error or not content_data:
                        process_error_msg = f"URL Processing Error: {fetch_error or 'Could not retrieve content.'}"
                    else:
                        summary, summary_error = summarize_text(content_data['text'], openai_api_key)
                        article_data_to_add = {
                            'id': url_to_process, 'title': content_data['title'], 'full_text': content_data['text'],
                            'summary': summary, 'error': fetch_error or summary_error, 'is_manual': False,
                            'full_audio_path': None, 'summary_audio_path': None
                         }
                        if summary_error: process_error_msg = f"Summarization error: {summary_error}"
                        # Only set success if no specific error occurred during URL processing either
                        if not fetch_error and not summary_error:
                             process_success_message = f"Article '{content_data['title']}' processed."
                        elif fetch_error: # If fetch failed, report that primarily
                             process_error_msg = f"URL Fetch Error: {fetch_error}"

                else: process_error_msg = "Error: No URL target found for processing."

            # Add to state list if data was prepared
            if article_data_to_add:
                 st.session_state.articles.append(article_data_to_add)
                 st.session_state.selected_article_id = article_data_to_add['id'] # Select the newly added one
                 cleanup_audio_files(get_active_audio_paths()) # Cleanup old audio

        except Exception as e:
            # Catch any unexpected errors during the processing block
            process_error_msg = f"An unexpected error occurred during processing: {e}"
            logging.error(f"Unexpected error processing {target_id}: {e}", exc_info=True)
        finally:
             # Reset processing flags *before* potential rerun
             st.session_state.processing = False
             st.session_state.processing_target = None
             st.session_state.manual_data = None
             # Store messages to display *after* rerun clears spinner
             st.session_state.last_process_success = process_success_message
             st.session_state.last_process_error = process_error_msg
             st.rerun() # Rerun to exit processing state and show results

# --- Display Processing Results (if any from last run) ---
if 'last_process_success' in st.session_state and st.session_state.last_process_success:
    st.success(st.session_state.last_process_success)
    del st.session_state.last_process_success # Clear after showing
if 'last_process_error' in st.session_state and st.session_state.last_process_error:
    st.error(st.session_state.last_process_error)
    del st.session_state.last_process_error # Clear after showing


# --- Display and Interact with Articles ---
st.header("Your Articles")
if not st.session_state.articles:
    st.info("No articles added yet. Use the sections above.")
else:
    # Article Selection Dropdown
    article_options = { a['id']: f"{a['title']} ({'Pasted' if a.get('is_manual', False) else a.get('id', 'Unknown ID')[:30]}...)" for a in st.session_state.articles }
    current_ids = list(article_options.keys())
    # Ensure selection is valid or default to first
    if st.session_state.selected_article_id not in current_ids:
        st.session_state.selected_article_id = current_ids[0] if current_ids else None

    selected_id = st.selectbox(
        "Choose article to view/read:",
        options=current_ids,
        format_func=lambda article_id: article_options.get(article_id, "Unknown Article"),
        index=current_ids.index(st.session_state.selected_article_id) if st.session_state.selected_article_id in current_ids else 0,
        key="article_selector",
        label_visibility="collapsed" # Hide redundant label
    )
    # Update selected article in session state if changed by user
    if selected_id != st.session_state.selected_article_id:
        st.session_state.selected_article_id = selected_id
        st.rerun() # Rerun to update the display for the newly selected article

    # --- Display Selected Article Details and Actions ---
    if st.session_state.selected_article_id:
        selected_index = get_article_index(st.session_state.selected_article_id)
        if selected_index != -1:
            # Get the data for the selected article
            article_data = st.session_state.articles[selected_index]

            # Display Title and Source more clearly
            st.subheader(f"{article_data.get('title', 'No Title')}")
            st.caption(f"Source: {'Manually Pasted Text' if article_data.get('is_manual', False) else article_data.get('id', 'Unknown URL')}")
            # Display processing errors non-intrusively if summary failed
            if article_data.get('error') and not article_data.get('summary'):
                 st.warning(f"Processing Note: {article_data['error']}")

            # Expander for Summary Text
            with st.expander("View Summary Text"):
                 summary_text_display = article_data.get('summary', "No summary generated or available.")
                 st.write(summary_text_display)

            # --- Action Buttons ---
            col1, col2, col3 = st.columns([1, 1, 1])
            # Generate a unique prefix for button keys based on sanitized ID
            button_key_prefix = get_valid_filename(article_data.get('id', f'no_id_{selected_index}'))[:20]

            with col1:
                read_summary_button = st.button("▶️ Read Summary", key=f"sum_{button_key_prefix}", disabled=st.session_state.processing)
            with col2:
                 read_full_button = st.button("▶️ Read Full", key=f"full_{button_key_prefix}", disabled=st.session_state.processing)
            with col3:
                delete_button = st.button("🗑️ Delete", key=f"del_{button_key_prefix}", disabled=st.session_state.processing)

            # Display proactive warning for long text only if button not active
            if len(article_data.get('full_text', '')) > 3500 and not read_full_button:
                 col2.caption("⚠️ Full text long.")

            # --- Audio Handling Placeholders ---
            audio_player_placeholder = st.empty()
            audio_status_placeholder = st.empty()
            download_placeholder = st.empty()

            # --- handle_audio_request Function (Key Logic) ---
            # This function encapsulates generating or finding audio and displaying controls
            def handle_audio_request(text_type, text_content):
                """Generates or retrieves audio, displays player/download."""
                audio_path_key = f"{text_type}_audio_path" # e.g., 'summary_audio_path'
                audio_path = article_data.get(audio_path_key)
                audio_ready = False
                audio_bytes = None

                # 1. Check if valid audio already exists in this session
                if audio_path and os.path.exists(audio_path):
                    try:
                        with open(audio_path, "rb") as f:
                            audio_bytes = f.read()
                        if audio_bytes: # Ensure file wasn't empty
                            audio_ready = True
                            audio_status_placeholder.success(f"Audio ready for {text_type}.")
                        else: # File exists but is empty
                             os.remove(audio_path) # Clean up empty file
                             st.session_state.articles[selected_index][audio_path_key] = None # Invalidate path
                             audio_path = None
                             logging.warning(f"Removed empty audio file: {audio_path}")
                             audio_status_placeholder.warning("Previous audio file was invalid. Please generate again.")
                    except Exception as e:
                        # Error reading existing file
                        audio_status_placeholder.warning(f"Could not load existing audio file ({e}). Regenerating might be needed.")
                        st.session_state.articles[selected_index][audio_path_key] = None # Invalidate the path
                        audio_path = None # Force regeneration if button clicked again

                # 2. If audio not ready (doesn't exist or failed to load), generate it
                if not audio_ready:
                    # Check if text content is valid before trying to generate
                    is_valid_summary = text_type == "summary" and text_content and text_content not in ["Summary could not be generated.", "Content too short to summarize effectively."]
                    is_valid_full = text_type == "full" and text_content
                    if not (is_valid_summary or is_valid_full):
                         audio_status_placeholder.warning(f"No valid {text_type} text available to generate audio.")
                         return # Don't proceed with generation

                    # Proceed with generation
                    audio_status_placeholder.info(f"Generating {text_type} audio...")
                    with st.spinner(f"Generating {text_type} audio..."):
                        try:
                            filepath, audio_error = generate_audio(
                                text_content, openai_api_key, article_data['id'], text_type,
                                voice=st.session_state.selected_voice, speed=st.session_state.selected_speed
                            )
                            # Handle generation results
                            if audio_error:
                                audio_status_placeholder.error(f"Audio Generation Error: {audio_error}")
                                st.session_state.articles[selected_index][audio_path_key] = None
                            elif filepath:
                                # Update state with the new path
                                st.session_state.articles[selected_index][audio_path_key] = filepath
                                # Must rerun for the app to find the new file path in the next script execution
                                st.rerun()
                            else: # Should not happen if audio_error is None, but safety check
                                audio_status_placeholder.error(f"{text_type.capitalize()} audio generation failed unexpectedly.")
                                st.session_state.articles[selected_index][audio_path_key] = None
                            # Exit function after generation attempt; rerun handles display
                            return

                        except Exception as e:
                            # Catch unexpected errors during the API call or file saving
                            audio_status_placeholder.error(f"Unexpected Generation Error: {e}")
                            logging.error(f"TTS Exception for {text_type} of {article_data['id']}: {e}", exc_info=True)
                            st.session_state.articles[selected_index][audio_path_key] = None
                            # Exit function on error
                            return

                # 3. If audio is ready (either existed or was just generated in previous run), display controls
                if audio_ready and audio_bytes:
                    try:
                        # Attempt to display the built-in player
                        audio_player_placeholder.audio(audio_bytes, format="audio/mp3")
                    except Exception as player_e:
                        # Catch potential errors with st.audio itself (e.g., unsupported format/codec on browser)
                        audio_player_placeholder.warning(f"Audio player failed: {player_e}. Please use the Download button.")

                    # Always show download button if audio bytes are available
                    download_filename = f"{get_valid_filename(article_data['title'])}_{text_type}.mp3"
                    download_placeholder.download_button(
                        label=f"⬇️ Download {text_type.capitalize()} MP3",
                        data=audio_bytes,
                        file_name=download_filename,
                        mime="audio/mpeg",
                        key=f"dl_{button_key_prefix}_{text_type}" # Unique key for download button
                    )

            # --- Trigger Audio Handling Based on Button Clicks ---
            # Check which button was pressed *this script run* (will be True if clicked in previous run)
            if read_summary_button:
                handle_audio_request("summary", article_data.get('summary'))
            elif read_full_button: # Use elif to prevent both triggering in one cycle
                handle_audio_request("full", article_data.get('full_text'))
            else:
                 # --- If no generation button clicked, proactively check for existing audio ---
                 # This helps display controls immediately if audio was generated previously in the session
                 summary_audio_path = article_data.get('summary_audio_path')
                 full_audio_path = article_data.get('full_audio_path')
                 # Check summary audio path first
                 if summary_audio_path and os.path.exists(summary_audio_path):
                     handle_audio_request("summary", article_data.get('summary')) # Call handler to display controls
                 # If summary audio didn't exist or failed, check full audio path
                 elif full_audio_path and os.path.exists(full_audio_path):
                     handle_audio_request("full", article_data.get('full_text')) # Call handler to display controls

            # --- Delete Logic ---
            if delete_button:
                id_to_delete = article_data['id']
                logging.info(f"Attempting to delete article: {id_to_delete}")
                index_to_delete = get_article_index(id_to_delete)
                if index_to_delete != -1:
                    deleted_article_data = st.session_state.articles.pop(index_to_delete)
                    st.success(f"Article '{deleted_article_data.get('title', 'Untitled')}' deleted.")

                    # Clean up associated audio files from disk
                    paths_to_delete = [
                        deleted_article_data.get('full_audio_path'),
                        deleted_article_data.get('summary_audio_path')
                    ]
                    for path in paths_to_delete:
                        # Check if path is valid and file exists before trying to delete
                        if path and isinstance(path, str) and os.path.exists(path):
                            try:
                                os.remove(path)
                                logging.info(f"Deleted associated audio file: {path}")
                            except Exception as e:
                                logging.error(f"Error deleting audio file {path}: {e}")

                    # Reset selection, clear UI elements, and rerun
                    st.session_state.selected_article_id = None
                    audio_player_placeholder.empty()
                    audio_status_placeholder.empty()
                    download_placeholder.empty()
                    st.rerun()
                else:
                    st.error("Could not find the article to delete (index mismatch). Please refresh.")

# --- End of Script ---
