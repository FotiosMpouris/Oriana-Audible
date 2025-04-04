# app.py
import streamlit as st
from mainfunctions import (
    fetch_article_content,
    summarize_text,
    generate_audio,
    cleanup_audio_files,
    AUDIO_DIR, # Import the audio directory path
    get_valid_filename # Import helper for manual article ID
)
import os
import logging
import re # For sanitizing title for internal ID
import time # For unique manual IDs if title is empty

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
    st.warning("orianalogo.png not found. Please add it to your repository.")

st.title("Oriana: Article Summarizer & Reader")
st.caption("Add articles via URL or paste text, get summaries, and listen!")
st.info("ℹ️ Note: Audio generation happens per session. Audio files are not stored permanently across app restarts due to server limitations.")


# --- Constants ---
MAX_ARTICLES = 5

# --- Check for OpenAI API Key ---
try:
    # Ensure secrets structure is correct: [openai] api_key = "sk-..."
    openai_api_key = st.secrets["openai"]["api_key"]
    if not openai_api_key or not openai_api_key.startswith("sk-"):
        st.error("OpenAI API key is missing, invalid, or not configured correctly in secrets. Please add `[openai]` section with `api_key = 'sk-...'` to your Streamlit secrets.")
        st.stop()
except KeyError:
    st.error("OpenAI API key section `[openai]` or key `api_key` not found in Streamlit secrets. Please add `[openai]` section with `api_key = 'sk-...'`.")
    st.info("Refer to the deployment instructions for setting up secrets.")
    st.stop()
except Exception as e:
    st.error(f"An error occurred accessing secrets: {e}")
    st.stop()

# --- Initialize Session State ---
if 'articles' not in st.session_state:
    st.session_state.articles = [] # List to store article dictionaries
    # Each dict: {'id': str (url or manual_id), 'title': str, 'full_text': str, 'summary': str,
    #             'full_audio_path': str|None, 'summary_audio_path': str|None, 'error': str|None, 'is_manual': bool}

if 'selected_article_id' not in st.session_state:
    st.session_state.selected_article_id = None

if 'processing' not in st.session_state:
    st.session_state.processing = False # Flag to prevent duplicate processing

# --- Helper function to get article index by ID ---
def get_article_index(article_id):
    for i, article in enumerate(st.session_state.articles):
        if article['id'] == article_id:
            return i
    return -1

# --- Helper function to get currently active audio paths ---
def get_active_audio_paths():
    paths = set()
    for article in st.session_state.articles:
        if article.get('full_audio_path') and os.path.exists(article['full_audio_path']): # Check existence here too
            paths.add(article['full_audio_path'])
        if article.get('summary_audio_path') and os.path.exists(article['summary_audio_path']): # Check existence here too
            paths.add(article['summary_audio_path'])
    return paths

# --- Helper to create a unique ID for manual articles ---
def create_manual_id(title):
    if title and title.strip():
         # Basic sanitization: lowercase, replace spaces/symbols with underscores
         sanitized = re.sub(r'\W+', '_', title.strip().lower())
         # Truncate and add prefix
         return f"manual_{sanitized[:50]}"
    else:
         # Fallback if title is empty
         return f"manual_{int(time.time())}"


# --- Input Section ---
st.header("Add New Article")

tab1, tab2 = st.tabs(["Add via URL", "Add by Pasting Text"])

with tab1:
    new_url = st.text_input("Enter URL of the online article:", key="url_input", disabled=st.session_state.processing)
    add_url_button = st.button("Add Article from URL", key="add_url", disabled=st.session_state.processing or not new_url)

    if add_url_button and new_url:
        if len(st.session_state.articles) >= MAX_ARTICLES:
            st.warning(f"You can only have up to {MAX_ARTICLES} articles loaded. Please delete one first.")
        elif any(article['id'] == new_url for article in st.session_state.articles):
            st.warning("This URL has already been added.")
        else:
            st.session_state.processing = True
            st.session_state.processing_target = new_url # Store what we are processing
            st.rerun()

with tab2:
    manual_title = st.text_input("Enter a Title for the article:", key="manual_title_input", disabled=st.session_state.processing)
    manual_text = st.text_area("Paste the full article text here:", height=250, key="manual_text_input", disabled=st.session_state.processing)
    add_manual_button = st.button("Add Manual Article Text", key="add_manual", disabled=st.session_state.processing or not manual_text or not manual_title)

    if add_manual_button and manual_text and manual_title:
        if len(st.session_state.articles) >= MAX_ARTICLES:
            st.warning(f"You can only have up to {MAX_ARTICLES} articles loaded. Please delete one first.")
        else:
            manual_id = create_manual_id(manual_title)
            if any(article['id'] == manual_id for article in st.session_state.articles):
                 # If title collision, make ID more unique
                 manual_id = f"{manual_id}_{int(time.time())}"

            if any(article['id'] == manual_id for article in st.session_state.articles): # Double check after adding timestamp
                 st.warning("An article with a very similar title already exists. Please modify the title.")
            else:
                 st.session_state.processing = True
                 st.session_state.processing_target = manual_id # Store what we are processing
                 st.session_state.manual_data = {"title": manual_title, "text": manual_text, "id": manual_id} # Store data needed
                 st.rerun()


# --- Processing Logic ---
if st.session_state.processing:
    target_id = st.session_state.get('processing_target') # Get the ID/URL being processed

    # Determine if it's URL or Manual processing
    is_manual_processing = target_id and target_id.startswith("manual_")
    spinner_message = f"Processing article..."
    if not is_manual_processing and target_id:
         spinner_message = f"Processing URL: {target_id[:50]}..."
    elif is_manual_processing:
         manual_title = st.session_state.get("manual_data", {}).get("title", "Pasted Text")
         spinner_message = f"Processing Manual Text: '{manual_title[:50]}'..."


    with st.spinner(spinner_message):
        article_data_to_add = None
        try:
            if is_manual_processing:
                # --- Process Manual Text ---
                manual_data = st.session_state.get("manual_data")
                if manual_data:
                    article_title = manual_data['title']
                    article_text = manual_data['text']
                    article_id = manual_data['id']

                    summary, summary_error = summarize_text(article_text, openai_api_key)
                    if summary_error:
                        st.error(f"Error summarizing article: {summary_error}")
                        summary = "Summary could not be generated." # Still add article

                    article_data_to_add = {
                        'id': article_id,
                        'title': article_title,
                        'full_text': article_text,
                        'summary': summary,
                        'full_audio_path': None,
                        'summary_audio_path': None,
                        'error': summary_error, # Only summary error possible here
                        'is_manual': True
                    }
                    st.success(f"Manual article '{article_title}' added successfully!")
                else:
                    st.error("Error retrieving manual data for processing.") # Should not happen

            else:
                # --- Process URL ---
                url_to_process = target_id
                if url_to_process:
                    content_data, fetch_error = fetch_article_content(url_to_process)

                    if fetch_error or not content_data:
                        st.error(f"Error processing URL: {fetch_error or 'Could not retrieve content.'}")
                        # Optionally add a placeholder article showing the error
                        # For now, we just show error and stop processing this item
                    else:
                        article_title = content_data['title']
                        article_text = content_data['text']

                        summary, summary_error = summarize_text(article_text, openai_api_key)
                        if summary_error:
                            st.error(f"Error summarizing article: {summary_error}")
                            summary = "Summary could not be generated."

                        article_data_to_add = {
                            'id': url_to_process, # Use URL as ID for URL articles
                            'title': article_title,
                            'full_text': article_text,
                            'summary': summary,
                            'full_audio_path': None,
                            'summary_audio_path': None,
                            'error': fetch_error or summary_error,
                            'is_manual': False
                        }
                        st.success(f"Article '{article_title}' added successfully!")
                else:
                     st.error("Error: No URL target found for processing.") # Should not happen


            # --- Add to Session State if successful ---
            if article_data_to_add:
                 st.session_state.articles.append(article_data_to_add)
                 st.session_state.selected_article_id = article_data_to_add['id'] # Select the new one
                 # Run cleanup for any old, unused audio files (from previous runs in this session)
                 cleanup_audio_files(get_active_audio_paths())


        except Exception as e:
            st.error(f"An unexpected error occurred during processing: {e}")
            logging.error(f"Unexpected error processing {target_id}: {e}", exc_info=True)
        finally:
            # Reset processing flags and clear temporary data
            st.session_state.processing = False
            st.session_state.processing_target = None
            st.session_state.manual_data = None # Clear manual data cache
            st.rerun() # Rerun to clear spinner and update UI


# --- Display and Interact with Articles ---
st.header("Your Articles")

if not st.session_state.articles:
    st.info("No articles added yet. Use the inputs above.")
else:
    # Create options for the selectbox: Use Title (ID as fallback)
    article_options = {
        article['id']: f"{article['title']} ({'Pasted Text' if article['is_manual'] else article['id'][:30]}...)"
        for article in st.session_state.articles
    }

    # Ensure selection is valid
    current_ids = list(article_options.keys())
    if st.session_state.selected_article_id not in current_ids:
         # If previous selection deleted/invalid, select the first one if available
         st.session_state.selected_article_id = current_ids[0] if current_ids else None

    selected_id = st.selectbox(
        "Choose an article to interact with:",
        options=current_ids,
        format_func=lambda article_id: article_options.get(article_id, "Unknown Article"),
        index=current_ids.index(st.session_state.selected_article_id) if st.session_state.selected_article_id in current_ids else 0,
        key="article_selector"
    )

    # Update selected article in session state if changed
    if selected_id != st.session_state.selected_article_id:
        st.session_state.selected_article_id = selected_id
        st.rerun() # Rerun to update the display for the newly selected article

    # --- Display Selected Article Details and Actions ---
    if st.session_state.selected_article_id:
        selected_index = get_article_index(st.session_state.selected_article_id)

        if selected_index != -1:
            # Use a copy to avoid direct modification issues during iteration? No, direct is needed for updates.
            article_data = st.session_state.articles[selected_index]

            st.subheader(f"Selected: {article_data['title']}")
            if not article_data['is_manual']:
                 st.caption(f"URL: {article_data['id']}")
            else:
                 st.caption("Source: Manually Pasted Text")

            if article_data.get('error') and not article_data['is_manual']: # Only show fetch/summary errors for URLs initially
                 st.warning(f"Note during processing: {article_data['error']}")

            # Display Summary Text
            with st.expander("View Summary"):
                 st.write(article_data['summary'] if article_data['summary'] else "No summary available.")

            # Action Buttons
            col1, col2, col3 = st.columns([1, 1, 1])

            # --- Unique keys for buttons based on article ID ---
            button_key_prefix = get_valid_filename(article_data['id'])[:20] # Use sanitized ID part for key

            with col1:
                read_summary_button = st.button("▶️ Read Summary", key=f"sum_{button_key_prefix}", disabled=st.session_state.processing)
            with col2:
                 read_full_button = st.button("▶️ Read Full Article", key=f"full_{button_key_prefix}", disabled=st.session_state.processing)
                 if len(article_data.get('full_text', '')) > 3500:
                     st.caption("⚠️ Reading the full article may take time/fail if very long.")
            with col3:
                delete_button = st.button("🗑️ Delete Article", key=f"del_{button_key_prefix}", disabled=st.session_state.processing)

            # --- Audio Generation and Playback Logic ---
            audio_placeholder = st.empty() # Placeholder to display the audio player
            audio_status_placeholder = st.empty() # Placeholder for status messages

            # --- Generate/Play Summary Audio ---
            if read_summary_button:
                 summary_text = article_data['summary']
                 if summary_text and summary_text not in ["Summary could not be generated.", "Content too short to summarize effectively."]:
                     audio_path = article_data.get('summary_audio_path')
                     # Check if path exists AND file exists on disk (important for ephemeral storage)
                     if audio_path and os.path.exists(audio_path):
                          try:
                              with open(audio_path, "rb") as audio_file:
                                   audio_bytes = audio_file.read()
                              audio_placeholder.audio(audio_bytes, format="audio/mp3")
                              audio_status_placeholder.success("Playing summary audio.")
                          except FileNotFoundError:
                               audio_status_placeholder.warning("Audio file not found (session may have restarted). Regenerating...")
                               st.session_state.articles[selected_index]['summary_audio_path'] = None # Reset path
                               st.rerun() # Trigger regeneration on next cycle
                          except Exception as e:
                               audio_status_placeholder.error(f"Error playing audio: {e}")
                     else:
                          # Generate audio if path doesn't exist or file is gone
                          with st.spinner("Generating summary audio..."):
                              try:
                                  # Use article ID (URL or manual ID) for base filename
                                  base_filename = article_data['id']
                                  filepath, audio_error = generate_audio(summary_text, openai_api_key, base_filename, "summary")
                                  if audio_error:
                                      audio_status_placeholder.error(f"Could not generate summary audio: {audio_error}")
                                      st.session_state.articles[selected_index]['summary_audio_path'] = None # Ensure path is None on failure
                                  elif filepath:
                                      st.session_state.articles[selected_index]['summary_audio_path'] = filepath
                                      # Rerun immediately to play the newly generated audio
                                      st.rerun()
                                  else: # Should be covered by audio_error, but safety check
                                       audio_status_placeholder.error("Audio generation failed unexpectedly.")
                                       st.session_state.articles[selected_index]['summary_audio_path'] = None


                              except Exception as e:
                                  audio_status_placeholder.error(f"Error during summary audio generation: {e}")
                                  logging.error(f"TTS generation failed for summary of {article_data['id']}: {e}", exc_info=True)
                                  st.session_state.articles[selected_index]['summary_audio_path'] = None # Ensure path is None on failure

                 else:
                    audio_status_placeholder.warning("No summary available or content too short to generate audio.")


            # --- Generate/Play Full Article Audio ---
            if read_full_button:
                 full_text = article_data['full_text']
                 if full_text:
                     audio_path = article_data.get('full_audio_path')
                     # Check if path exists AND file exists on disk
                     if audio_path and os.path.exists(audio_path):
                          try:
                              with open(audio_path, "rb") as audio_file:
                                   audio_bytes = audio_file.read()
                              audio_placeholder.audio(audio_bytes, format="audio/mp3")
                              audio_status_placeholder.success("Playing full article audio.")
                          except FileNotFoundError:
                               audio_status_placeholder.warning("Audio file not found (session may have restarted). Regenerating...")
                               st.session_state.articles[selected_index]['full_audio_path'] = None # Reset path
                               st.rerun() # Trigger regeneration
                          except Exception as e:
                               audio_status_placeholder.error(f"Error playing audio: {e}")
                     else:
                          # Generate audio
                          with st.spinner("Generating full article audio... This might take some time."):
                              try:
                                  base_filename = article_data['id']
                                  filepath, audio_error = generate_audio(full_text, openai_api_key, base_filename, "full")
                                  if audio_error:
                                      audio_status_placeholder.error(f"Could not generate full audio: {audio_error}")
                                      st.session_state.articles[selected_index]['full_audio_path'] = None
                                  elif filepath:
                                      st.session_state.articles[selected_index]['full_audio_path'] = filepath
                                      st.rerun() # Rerun to play
                                  else:
                                       audio_status_placeholder.error("Full audio generation failed unexpectedly.")
                                       st.session_state.articles[selected_index]['full_audio_path'] = None

                              except Exception as e:
                                  audio_status_placeholder.error(f"Error during full audio generation: {e}")
                                  logging.error(f"TTS generation failed for full text of {article_data['id']}: {e}", exc_info=True)
                                  st.session_state.articles[selected_index]['full_audio_path'] = None
                 else:
                    audio_status_placeholder.warning("No full article text available to generate audio.")


            # Delete Article Logic
            if delete_button:
                id_to_delete = article_data['id']
                logging.info(f"Attempting to delete article: {id_to_delete}")

                # Find the article again to be safe (index might change)
                index_to_delete = get_article_index(id_to_delete)
                if index_to_delete != -1:
                    deleted_article_data = st.session_state.articles.pop(index_to_delete)
                    st.success(f"Article '{deleted_article_data['title']}' deleted.")

                    # Clean up associated audio files immediately IF THEY EXIST
                    paths_to_delete = []
                    if deleted_article_data.get('full_audio_path'):
                         paths_to_delete.append(deleted_article_data['full_audio_path'])
                    if deleted_article_data.get('summary_audio_path'):
                         paths_to_delete.append(deleted_article_data['summary_audio_path'])

                    for path in paths_to_delete:
                         if path and os.path.exists(path): # Check existence before trying delete
                             try:
                                 os.remove(path)
                                 logging.info(f"Deleted associated audio file: {path}")
                             except OSError as e:
                                 logging.error(f"Error deleting audio file {path}: {e}")

                    # Reset selection and rerun
                    st.session_state.selected_article_id = None
                    st.rerun()
                else:
                    st.error("Could not find the article to delete. Please refresh.")

# --- Footer/Cleanup Info ---
# Explicit cleanup happens on adding/deleting. Ephemeral storage handles the rest.
# st.sidebar.button("Clean up unused audio files", on_click=lambda: cleanup_audio_files(get_active_audio_paths())) # Optional manual button
