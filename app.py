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
import base64 # <-- Added for Base64 encoding

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
**Transform Long Reads into Easy Listens!**

Ever find fascinating articles but lack the time (or energy) to read them? Oriana bridges that gap. Add articles via URL or pasted text, get quick AI-powered summaries, and generate audio versions to listen to anytime, anywhere – perfect for commutes, workouts, or just relaxing.

**Adding Articles:**

*   **Via URL:** Paste the full web address (URL) of an online article into the "URL" box and click **"Add Article from URL"**.
    *   *Heads-up:* Some sites use strong anti-scraping measures or require logins/subscriptions, which might prevent fetching. If you hit an error, the **Paste Text** method is your reliable backup!
*   **Via Pasting Text:** Copy the article text from its source. Paste it into the "Pasted Text" box, give your article a **Title**, and click **"Add Manual Article"**.
    *   *Tip:* Use the **"Clear URL"**, **"Clear Title"**, and **"Clear Text"** buttons to quickly reset the input fields.

**Interacting with Your Articles:**

*   **Select:** Choose an article from the dropdown menu under **"Your Articles"**.
*   **Summarize:** Click **"View Summary Text"** to read the AI-generated summary. This is great for quickly grasping the key points.
*   **Listen:** Click **"▶️ Read Summary"** or **"▶️ Read Full"** to generate audio using the voice and speed selected in the sidebar.
    *   **Generation Time:** This calls the OpenAI API. Summaries are quick, but generating audio for **full articles can take several minutes**, especially for very long ones (like white papers!), as Oriana processes the text in chunks. A spinner will show progress.
    *   **Getting the Audio:** After generation finishes, the app will refresh, and controls will appear below the buttons:
        *   **▶️ Try Playing Directly:** Clicking this attempts to open the audio in a new browser tab or your device's media player. It's convenient for quick listening but **may not work reliably on all mobile devices or for very large audio files** due to browser limitations.
        *   **⬇️ Download MP3:** This is the **most reliable** way to get your audio. It saves the MP3 file directly to your device, perfect for offline listening (in the car, on a plane) or if the "Try Play" link doesn't work. **Recommended for large files and mobile use.**

**Audio Settings (Sidebar):**

*   **Choose Voice & Speed:** Select your preferred **Voice** and playback **Speed** *before* clicking the "Read..." buttons.
*   **Language Note:** The available voices are primarily trained on English. While they *can* read other languages present in the text, the pronunciation might not sound perfectly native (e.g., for Greek text).

**Important Notes & Tips:**

*   **Temporary Files:** Generated audio files **only exist while the app is active in your browser session**. They are **not saved permanently** on the server. Always use the **Download MP3** button to save any audio you want to keep.
*   **Summarization Language:** Oriana attempts to detect the article's language and summarize in that same language.
*   **API Costs:** Remember that generating summaries and audio uses the OpenAI API, which consumes credits associated with the provided API key.
*   **Troubleshooting:**
    *   URL fetch failed? Use the Paste Text method.
    *   Audio generation failed? Check for error messages, ensure your API key is valid and has credits, and try again.
    *   "Try Play" link fails? Use the reliable **Download MP3** button.

""")
# --- Constants & Options ---
MAX_ARTICLES = 5
TTS_VOICES = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
TTS_SPEEDS = {"Normal": 1.0, "Slightly Faster": 1.15, "Faster": 1.25, "Fastest": 1.5}

# --- Check for OpenAI API Key ---
try:
    # Ensure secrets handling is robust
    if "openai" not in st.secrets or "api_key" not in st.secrets["openai"]:
         raise KeyError("OpenAI API key not found in secrets.toml. Expected [openai] section with api_key.")
    openai_api_key = st.secrets["openai"]["api_key"]
    if not openai_api_key or not openai_api_key.startswith("sk-"):
        raise ValueError("Invalid API Key format or missing value.")
except (KeyError, ValueError) as e:
    st.error(f"OpenAI API key configuration error in Streamlit secrets: {e}. Please ensure secrets.toml has `[openai]` section with `api_key = 'sk-...'` and it is valid.")
    st.stop() # Stop execution if key is invalid or missing
except Exception as e:
     st.error(f"An unexpected error occurred reading secrets: {e}")
     st.stop()

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
        st.text_input("URL:", key="url_input", label_visibility="collapsed", placeholder="Enter URL of online article", disabled=st.session_state.processing)
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
        st.text_input("Title:", key="manual_title_input", label_visibility="collapsed", placeholder="Enter a Title for the article", disabled=st.session_state.processing)
    with col_title_clear:
        st.button("Clear Title", key="clear_title_btn", help="Clear the Title field",
                  on_click=clear_title_callback, # Use callback
                  disabled=st.session_state.processing)

    # Manual Text Input with Clear Button using Callback
    col_text_input, col_text_clear = st.columns([4, 1])
    with col_text_input:
        st.text_area("Pasted Text:", height=200, key="manual_text_input", label_visibility="collapsed", placeholder="Paste the full article text here", disabled=st.session_state.processing)
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
                    if summary is None and summary_error: # Handle case where summary fails but returns error
                         final_summary = None
                         final_error = f"Summarization failed: {summary_error}"
                    elif summary_error: # Handle case where summary returns but with a non-fatal error message
                         final_summary = summary
                         final_error = f"Processing note: {summary_error}" # e.g., "too short to summarize"
                    else: # Success
                         final_summary = summary
                         final_error = None

                    article_data_to_add = {
                        'id': manual_data['id'], 'title': manual_data['title'], 'full_text': manual_data['text'],
                        'summary': final_summary, 'error': final_error, 'is_manual': True,
                        'full_audio_path': None, 'summary_audio_path': None
                    }
                    if final_error and final_summary is None: process_error_msg = final_error
                    elif not final_error: process_success_message = f"Manual article '{manual_data['title']}' processed."
                    # If final_error exists but summary also exists, don't show top-level error, let it be shown with article

                else: process_error_msg = "Error retrieving valid manual data for processing."
            else: # Process URL
                url_to_process = target_id
                if url_to_process:
                    content_data, fetch_error = fetch_article_content(url_to_process)
                    if fetch_error or not content_data:
                        process_error_msg = f"URL Processing Error: {fetch_error or 'Could not retrieve content.'}"
                    else:
                        summary, summary_error = summarize_text(content_data['text'], openai_api_key)
                        if summary is None and summary_error:
                            final_summary = None
                            combined_error = f"Fetch OK. Summarization failed: {summary_error}"
                        elif summary_error:
                            final_summary = summary
                            combined_error = f"Fetch OK. Summary note: {summary_error}"
                        else:
                            final_summary = summary
                            combined_error = None # Only fetch error matters if it existed before this point

                        # Prioritize fetch error if it occurred
                        final_processing_error = fetch_error or combined_error

                        article_data_to_add = {
                            'id': url_to_process, 'title': content_data['title'], 'full_text': content_data['text'],
                            'summary': final_summary, 'error': final_processing_error, 'is_manual': False,
                            'full_audio_path': None, 'summary_audio_path': None
                         }
                        # Set success/error messages for display after rerun
                        if fetch_error: process_error_msg = f"URL Fetch Error: {fetch_error}"
                        elif final_processing_error and final_summary is None: process_error_msg = f"Summarization error: {summary_error}"
                        elif not final_processing_error: process_success_message = f"Article '{content_data['title']}' processed."

                else: process_error_msg = "Error: No URL target found for processing."

            # Add to state list if data was prepared
            if article_data_to_add:
                 # Check for duplicates again just before adding
                 if not any(a['id'] == article_data_to_add['id'] for a in st.session_state.articles):
                      st.session_state.articles.append(article_data_to_add)
                      st.session_state.selected_article_id = article_data_to_add['id'] # Select the newly added one
                      cleanup_audio_files(get_active_audio_paths()) # Cleanup old audio
                 else:
                      process_warning_msg = f"Article with ID '{article_data_to_add['id']}' already exists, skipping add."
                      logging.warning(process_warning_msg)
                      st.session_state.last_process_warning = process_warning_msg # Use a different state var?

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
             # Clear inputs only on successful add or specific user action
             # if process_success_message:
             #      st.session_state.url_input = "" # Maybe clear only the one used?
             #      st.session_state.manual_title_input = ""
             #      st.session_state.manual_text_input = ""
             st.rerun() # Rerun to exit processing state and show results

# --- Display Processing Results (if any from last run) ---
if 'last_process_success' in st.session_state and st.session_state.last_process_success:
    st.success(st.session_state.last_process_success)
    del st.session_state.last_process_success # Clear after showing
if 'last_process_error' in st.session_state and st.session_state.last_process_error:
    st.error(st.session_state.last_process_error)
    del st.session_state.last_process_error # Clear after showing
# Consider adding the warning display if used:
# if 'last_process_warning' in st.session_state and st.session_state.last_process_warning:
#     st.warning(st.session_state.last_process_warning)
#     del st.session_state.last_process_warning

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
            # Display processing errors non-intrusively if they occurred (even if summary exists)
            if article_data.get('error'):
                 st.warning(f"Processing Note: {article_data['error']}")

            # Expander for Summary Text
            with st.expander("View Summary Text"):
                 # Provide clearer message if summary is None or empty
                 summary_text_display = article_data.get('summary')
                 if summary_text_display:
                      st.write(summary_text_display)
                 else:
                      st.info("No summary could be generated for this article (e.g., text too short, or processing error occurred).")

            # --- Action Buttons ---
            col1, col2, col3 = st.columns([1, 1, 1])
            # Generate a unique prefix for button keys based on sanitized ID
            button_key_prefix = get_valid_filename(article_data.get('id', f'no_id_{selected_index}'))[:20]

            with col1:
                # Disable button if no summary text exists
                read_summary_button = st.button(
                    "▶️ Read Summary",
                    key=f"sum_{button_key_prefix}",
                    disabled=st.session_state.processing or not article_data.get('summary')
                )
                if not article_data.get('summary'):
                     col1.caption("(Summary unavailable)")


            with col2:
                 # Disable button if no full text exists
                 read_full_button = st.button(
                      "▶️ Read Full",
                      key=f"full_{button_key_prefix}",
                      disabled=st.session_state.processing or not article_data.get('full_text')
                 )
                 # Display proactive warning for long text only if button not active
                 full_text_len = len(article_data.get('full_text', ''))
                 if full_text_len > 4000 and not read_full_button: # Use 4000 as threshold aligns with TTS chunking
                     col2.caption("⚠️ Full text is long.")
                 elif not article_data.get('full_text'):
                     col2.caption("(Full text unavailable)")


            with col3:
                delete_button = st.button("🗑️ Delete", key=f"del_{button_key_prefix}", disabled=st.session_state.processing)

            # --- Audio Handling Placeholders ---
            # Placeholder for status messages (like errors or 'generating')
            audio_status_placeholder = st.empty()
            # Placeholder for the play/download controls
            audio_controls_placeholder = st.empty()

            # --- MODIFIED handle_audio_request Function (Key Logic) ---
            # This function encapsulates generating or finding audio and displaying controls
            def handle_audio_request(text_type, text_content):
                """Generates or retrieves audio, displays controls (Try Play Link + Download)."""
                audio_path_key = f"{text_type}_audio_path" # e.g., 'summary_audio_path'
                audio_path = article_data.get(audio_path_key)
                audio_ready = False
                audio_bytes = None
                play_link_html = "" # Initialize play link HTML

                # 1. Check if valid audio already exists in this session
                if audio_path and os.path.exists(audio_path):
                    try:
                        with open(audio_path, "rb") as f:
                            audio_bytes = f.read()
                        if audio_bytes: # Ensure file wasn't empty
                            audio_ready = True
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
                    is_valid_summary = text_type == "summary" and text_content # Simplified check - empty handled by generate_audio
                    is_valid_full = text_type == "full" and text_content
                    if not (is_valid_summary or is_valid_full):
                         audio_status_placeholder.warning(f"No valid {text_type} text available to generate audio.")
                         return # Don't proceed with generation

                    # Proceed with generation
                    audio_status_placeholder.info(f"Generating {text_type} audio... (May take time for long text)")
                    with st.spinner(f"Generating {text_type} audio... This can take a while for long articles."):
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
                    # Clear status messages now that controls are shown
                    audio_status_placeholder.empty()

                    # --- Prepare Base64 Link for "Try Play" ---
                    try:
                        b64 = base64.b64encode(audio_bytes).decode()
                        # target="_blank" attempts to open in new tab/context
                        # Add download attribute as a hint for browsers, though behavior varies
                        play_link_html = f'<a href="data:audio/mpeg;base64,{b64}" target="_blank" download="{get_valid_filename(article_data["title"])}_{text_type}.mp3">▶️ Try Playing Directly</a>'
                    except Exception as e:
                        logging.error(f"Error creating Base64 play link: {e}")
                        play_link_html = "<i>Error creating play link.</i>"

                    # --- Use columns for layout within the audio_controls_placeholder ---
                    col_play, col_download = audio_controls_placeholder.columns([1, 1])

                    with col_play:
                        col_play.markdown(play_link_html, unsafe_allow_html=True)
                        # Add a caption warning about potential issues, especially size/mobile
                        col_play.caption("(Opens in new tab/player. May fail on large files or some mobile browsers)")

                    with col_download:
                        download_filename = f"{get_valid_filename(article_data['title'])}_{text_type}.mp3"
                        col_download.download_button(
                            label=f"⬇️ Download MP3", # Consistent label
                            data=audio_bytes,
                            file_name=download_filename,
                            mime="audio/mpeg",
                            key=f"dl_{button_key_prefix}_{text_type}" # Unique key for download button
                        )

            # --- Trigger Audio Handling Based on Button Clicks ---
            # Check which button was pressed *this script run* (will be True if clicked in previous run)
            active_audio_request = None
            if read_summary_button:
                active_audio_request = ("summary", article_data.get('summary'))
            elif read_full_button: # Use elif to prevent both triggering in one cycle
                active_audio_request = ("full", article_data.get('full_text'))

            if active_audio_request:
                 handle_audio_request(active_audio_request[0], active_audio_request[1])
            else:
                 # --- If no generation button clicked, proactively check for existing audio ---
                 # This helps display controls immediately if audio was generated previously in the session
                 # Check which audio (summary or full) might already exist and display controls for it.
                 # Prioritize showing controls for 'full' if both exist? Or maybe the last one generated?
                 # Let's check both and potentially display controls for whichever is found first (summary preferred slightly)
                 summary_audio_path = article_data.get('summary_audio_path')
                 full_audio_path = article_data.get('full_audio_path')

                 displayed_controls = False
                 if summary_audio_path and os.path.exists(summary_audio_path):
                     handle_audio_request("summary", article_data.get('summary')) # Call handler to display controls
                     displayed_controls = True
                 # If summary audio didn't exist or failed, check full audio path
                 if not displayed_controls and full_audio_path and os.path.exists(full_audio_path):
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
                    audio_status_placeholder.empty()
                    audio_controls_placeholder.empty() # Clear the controls area too
                    st.rerun()
                else:
                    st.error("Could not find the article to delete (index mismatch). Please refresh.")

# --- End of Script ---
# Optional: Add a footer or final cleanup call if needed
# cleanup_audio_files(get_active_audio_paths()) # Run cleanup periodically? Maybe on session end? (Not straightforward in Streamlit)
