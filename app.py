# app.py
import streamlit as st
from mainfunctions import (
    fetch_article_content, 
    summarize_text, 
    generate_audio,
    cleanup_audio_files,
    AUDIO_DIR # Import the audio directory path
)
import os
import logging

# --- Page Configuration ---
st.set_page_config(
    page_title="Oriana - Article Summarizer & Reader",
    page_icon="✨", # You can use an emoji or provide a path to a favicon
    layout="wide"
)

# --- Application Title and Logo ---
# Ensure orianalogo.png is in the root of your GitHub repository
LOGO_PATH = "orianalogo.png"
if os.path.exists(LOGO_PATH):
    st.image(LOGO_PATH, width=150) 
else:
    st.warning("orianalogo.png not found. Please add it to your repository.")

st.title("Oriana: Article Summarizer & Reader")
st.caption("Upload article URLs, get summaries, and listen to them!")

# --- Constants ---
MAX_ARTICLES = 5

# --- Check for OpenAI API Key ---
try:
    openai_api_key = st.secrets["openai"]["api_key"]
    if not openai_api_key:
        st.error("OpenAI API key is missing. Please add it to your Streamlit secrets.")
        st.stop()
except KeyError:
    st.error("OpenAI API key not found in secrets.toml. Please add `[openai]` section with `api_key = 'YOUR_KEY'`.")
    st.info("Refer to the deployment instructions for setting up secrets.")
    st.stop()
except Exception as e:
    st.error(f"An error occurred accessing secrets: {e}")
    st.stop()

# --- Initialize Session State ---
if 'articles' not in st.session_state:
    st.session_state.articles = [] # List to store article dictionaries
    # Each dict: {'url': str, 'title': str, 'full_text': str, 'summary': str, 
    #             'full_audio_path': str|None, 'summary_audio_path': str|None, 'error': str|None}

if 'selected_article_url' not in st.session_state:
    st.session_state.selected_article_url = None

if 'processing' not in st.session_state:
    st.session_state.processing = False # Flag to prevent duplicate processing

# --- Helper function to get article index by URL ---
def get_article_index(url):
    for i, article in enumerate(st.session_state.articles):
        if article['url'] == url:
            return i
    return -1

# --- Helper function to get currently active audio paths ---
def get_active_audio_paths():
    paths = set()
    for article in st.session_state.articles:
        if article.get('full_audio_path'):
            paths.add(article['full_audio_path'])
        if article.get('summary_audio_path'):
            paths.add(article['summary_audio_path'])
    return paths

# --- Input Section ---
st.header("Add New Article")
new_url = st.text_input("Enter URL of the online article:", key="url_input")
add_button = st.button("Add Article", disabled=st.session_state.processing)

if add_button and new_url:
    if len(st.session_state.articles) >= MAX_ARTICLES:
        st.warning(f"You can only have up to {MAX_ARTICLES} articles loaded. Please delete one first.")
    elif any(article['url'] == new_url for article in st.session_state.articles):
        st.warning("This URL has already been added.")
    else:
        st.session_state.processing = True
        st.rerun() # Rerun to show spinner and disable button immediately

if st.session_state.processing and not add_button: # Check if processing was triggered
    with st.spinner(f"Processing article: {new_url}... This may take a moment."):
        try:
            # 1. Fetch Content
            content_data, fetch_error = fetch_article_content(new_url)
            
            if fetch_error or not content_data:
                st.error(f"Error fetching article: {fetch_error or 'Could not retrieve content.'}")
                st.session_state.processing = False
                st.rerun()

            else:
                article_title = content_data['title']
                article_text = content_data['text']
                
                # Check if text is reasonably long before summarizing
                if len(article_text) < 100: # Adjust threshold as needed
                     st.warning(f"Article content seems very short ({len(article_text)} characters). Summary might not be meaningful.")
                     summary = "Content too short to summarize effectively."
                     summary_error = None
                else:
                     # 2. Summarize Text
                     summary, summary_error = summarize_text(article_text, openai_api_key)
                
                if summary_error:
                    st.error(f"Error summarizing article: {summary_error}")
                    # Still add the article, but note the summary error
                    summary = "Summary could not be generated."

                # 3. Add to session state (audio generated on demand)
                st.session_state.articles.append({
                    'url': new_url,
                    'title': article_title,
                    'full_text': article_text,
                    'summary': summary,
                    'full_audio_path': None, # Generated when requested
                    'summary_audio_path': None, # Generated when requested
                    'error': fetch_error or summary_error # Store first error encountered
                })
                st.success(f"Article '{article_title}' added successfully!")
                # Select the newly added article by default
                st.session_state.selected_article_url = new_url
                
                # Run cleanup for any old, unused audio files
                cleanup_audio_files(get_active_audio_paths())

        except Exception as e:
            st.error(f"An unexpected error occurred while adding the article: {e}")
            logging.error(f"Unexpected error processing {new_url}: {e}", exc_info=True)
        finally:
            # Reset processing flag and clear input AFTER potential rerun
            st.session_state.processing = False
            # Clear the input field by resetting its key IF the processing finished
            # This requires a slightly more complex state management or manual clear instruction
            # For now, let's just rerun. The user can clear it manually if needed.
            st.rerun()


# --- Display and Interact with Articles ---
st.header("Your Articles")

if not st.session_state.articles:
    st.info("No articles added yet. Use the input above to add some.")
else:
    # Create options for the selectbox: Use Title (URL as fallback)
    article_options = {article['url']: f"{article['title']} ({article['url'][:30]}...)" for article in st.session_state.articles}
    
    # Ensure selection is valid
    if st.session_state.selected_article_url not in article_options:
         # If previous selection was deleted or list is new, select the first one if available
         st.session_state.selected_article_url = next(iter(article_options), None)

    selected_url = st.selectbox(
        "Choose an article to interact with:",
        options=list(article_options.keys()),
        format_func=lambda url: article_options[url],
        index=list(article_options.keys()).index(st.session_state.selected_article_url) if st.session_state.selected_article_url else 0,
        key="article_selector"
    )
    
    # Update selected article in session state if changed
    if selected_url != st.session_state.selected_article_url:
        st.session_state.selected_article_url = selected_url
        st.rerun() # Rerun to update the display for the newly selected article

    # --- Display Selected Article Details and Actions ---
    if st.session_state.selected_article_url:
        selected_index = get_article_index(st.session_state.selected_article_url)

        if selected_index != -1:
            article_data = st.session_state.articles[selected_index]

            st.subheader(f"Selected: {article_data['title']}")
            st.caption(f"URL: {article_data['url']}")

            if article_data.get('error'):
                 st.warning(f"Note: An error occurred during processing: {article_data['error']}")

            # Display Summary Text
            with st.expander("View Summary"):
                 st.write(article_data['summary'] if article_data['summary'] else "No summary available.")

            # Action Buttons
            col1, col2, col3 = st.columns([1, 1, 1])

            with col1:
                read_summary_button = st.button("▶️ Read Summary", key=f"sum_{article_data['url']}")
            with col2:
                 read_full_button = st.button("▶️ Read Full Article", key=f"full_{article_data['url']}")
                 if len(article_data.get('full_text', '')) > 3500: # Add warning for potentially long TTS generation
                     st.caption("⚠️ Reading the full article might take a while to generate.")
            with col3:
                delete_button = st.button("🗑️ Delete Article", key=f"del_{article_data['url']}")

            # --- Audio Generation and Playback Logic ---
            audio_placeholder = st.empty() # Placeholder to display the audio player

            # Generate and play Summary Audio
            if read_summary_button:
                 if article_data['summary'] and article_data['summary'] != "Summary could not be generated." and article_data['summary'] != "Content too short to summarize effectively.":
                     if not article_data.get('summary_audio_path') or not os.path.exists(article_data['summary_audio_path']):
                         with st.spinner("Generating summary audio..."):
                             try:
                                 # Generate a base filename from the URL or title
                                 base_filename = article_data['url'] # Or article_data['title']
                                 filepath, audio_error = generate_audio(article_data['summary'], openai_api_key, base_filename, "summary")
                                 if audio_error:
                                     st.error(f"Could not generate summary audio: {audio_error}")
                                 else:
                                     st.session_state.articles[selected_index]['summary_audio_path'] = filepath
                                     # Rerun to update the state and potentially play audio if logic allows
                                     st.rerun()
                             except Exception as e:
                                 st.error(f"Error generating summary audio: {e}")
                                 logging.error(f"TTS generation failed for summary of {article_data['url']}: {e}", exc_info=True)
                     
                     # Play audio if path exists
                     audio_path = st.session_state.articles[selected_index].get('summary_audio_path')
                     if audio_path and os.path.exists(audio_path):
                          try:
                              with open(audio_path, "rb") as audio_file:
                                   audio_bytes = audio_file.read()
                              audio_placeholder.audio(audio_bytes, format="audio/mp3")
                              st.success("Playing summary audio.")
                          except FileNotFoundError:
                               st.error("Audio file not found. Please try generating again.")
                               st.session_state.articles[selected_index]['summary_audio_path'] = None # Reset path
                          except Exception as e:
                               st.error(f"Error playing audio: {e}")
                     elif not article_data.get('summary_audio_path'): # If generation failed above, show message
                         st.warning("Summary audio could not be generated or found.")
                 else:
                    st.warning("No summary available or content was too short to generate audio.")


            # Generate and play Full Article Audio
            if read_full_button:
                if article_data['full_text']:
                    # Check character limit for TTS (OpenAI has limits, often around 4096 chars per request)
                    # For simplicity here, we'll try anyway, but in a production app, you might chunk text.
                    if len(article_data['full_text']) > 4000:
                        st.warning("Full text is very long. Audio generation might fail or take a very long time. Consider summarizing.")
                        # Optionally, you could disable the button or implement chunking here.
                    
                    if not article_data.get('full_audio_path') or not os.path.exists(article_data['full_audio_path']):
                        with st.spinner("Generating full article audio... This might take a while."):
                            try:
                                base_filename = article_data['url'] # Or article_data['title']
                                filepath, audio_error = generate_audio(article_data['full_text'], openai_api_key, base_filename, "full")
                                if audio_error:
                                    st.error(f"Could not generate full audio: {audio_error}")
                                else:
                                    st.session_state.articles[selected_index]['full_audio_path'] = filepath
                                    st.rerun()
                            except Exception as e:
                                st.error(f"Error generating full audio: {e}")
                                logging.error(f"TTS generation failed for full text of {article_data['url']}: {e}", exc_info=True)

                    # Play audio if path exists
                    audio_path = st.session_state.articles[selected_index].get('full_audio_path')
                    if audio_path and os.path.exists(audio_path):
                         try:
                             with open(audio_path, "rb") as audio_file:
                                 audio_bytes = audio_file.read()
                             audio_placeholder.audio(audio_bytes, format="audio/mp3")
                             st.success("Playing full article audio.")
                         except FileNotFoundError:
                              st.error("Audio file not found. Please try generating again.")
                              st.session_state.articles[selected_index]['full_audio_path'] = None # Reset path
                         except Exception as e:
                              st.error(f"Error playing audio: {e}")
                    elif not article_data.get('full_audio_path'): # If generation failed above, show message
                         st.warning("Full article audio could not be generated or found.")
                else:
                   st.warning("No full article text available to generate audio.")


            # Delete Article Logic
            if delete_button:
                url_to_delete = article_data['url']
                logging.info(f"Attempting to delete article: {url_to_delete}")
                
                # Find the article again to be safe (index might change)
                index_to_delete = get_article_index(url_to_delete)
                if index_to_delete != -1:
                    deleted_article_data = st.session_state.articles.pop(index_to_delete)
                    st.success(f"Article '{deleted_article_data['title']}' deleted.")

                    # Clean up associated audio files immediately
                    paths_to_delete = []
                    if deleted_article_data.get('full_audio_path'):
                         paths_to_delete.append(deleted_article_data['full_audio_path'])
                    if deleted_article_data.get('summary_audio_path'):
                         paths_to_delete.append(deleted_article_data['summary_audio_path'])
                    
                    for path in paths_to_delete:
                         if path and os.path.exists(path):
                             try:
                                 os.remove(path)
                                 logging.info(f"Deleted audio file: {path}")
                             except OSError as e:
                                 logging.error(f"Error deleting audio file {path}: {e}")
                                 
                    # Reset selection and rerun
                    st.session_state.selected_article_url = None
                    st.rerun()
                else:
                    st.error("Could not find the article to delete. Please refresh.")

# --- Footer/Cleanup (Optional) ---
# Streamlit Cloud handles cleanup, but explicit cleanup can be good practice
# Run cleanup on script exit might be too complex for basic Streamlit session management
# The current cleanup runs after adding an article and when deleting.
# Consider adding a manual cleanup button if needed.

# Example: Add a button for manual cleanup (optional)
# st.sidebar.button("Clean up unused audio files", on_click=lambda: cleanup_audio_files(get_active_audio_paths()))
