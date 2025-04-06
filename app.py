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
    page_title="Oriana Audible",
    page_icon="🎙️",  # Mic icon for audio focus
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Custom CSS for Visual Polish ---
st.markdown("""
    <style>
    .main { background-color: #f9f9f9; padding: 20px; border-radius: 10px; }
    .stButton>button { border-radius: 8px; background-color: #4CAF50; color: white; }
    .stButton>button:hover { background-color: #45a049; }
    .stTextInput>div>input, .stTextArea>div>textarea { border-radius: 8px; }
    .stExpander { background-color: #ffffff; border: 1px solid #ddd; border-radius: 8px; }
    .sidebar .sidebar-content { background-color: #f0f0f0; }
    h1 { color: #2E7D32; font-family: 'Georgia', serif; }
    h2 { color: #388E3C; }
    .stCaption { font-style: italic; color: #666; }
    </style>
""", unsafe_allow_html=True)

# --- Application Title and Logo ---
LOGO_PATH = "orianalogo.png"
col_logo, col_title = st.columns([1, 4])
with col_logo:
    if os.path.exists(LOGO_PATH):
        st.image(LOGO_PATH, width=150)
    else:
        st.warning("orianalogo.png not found.")
with col_title:
    st.title("Oriana Audible")
    st.caption("Inspired by Oriana Fallaci—Turn Articles into Audio Magic")

# --- Instructional Expander ---
with st.expander("ℹ️ How to Use Oriana Audible", expanded=True):
    st.markdown("""
    **Welcome to Oriana Audible: Turn Text into Audio Bliss!**

    Inspired by the fearless journalist Oriana Fallaci, this app empowers you to digest articles efficiently—whether you're driving, working out, or multitasking. Drop in a URL or paste text, get an AI-crafted summary, and listen to it (or the full piece) in a voice and speed you love. Here’s how to make the most of it:

    ### How to Use Oriana
    1. **Add Your Content:**
       - **Via URL:** Paste an article’s web address (e.g., `https://example.com/story`) into the "URL" field and hit **"Add Article from URL"**. Perfect for news sites or blogs!
         - *Note:* Some sites block scraping or require logins—try the paste method if it fails.
       - **Via Text:** Copy an article, paste it into "Pasted Text," add a "Title," and click **"Add Manual Article"**. Great for PDFs, paywalled content, or personal notes.
         - *Tip:* Use "Clear" buttons to reset fields fast.

    2. **Explore Your Articles:**
       - Pick an article from the "Your Articles" dropdown.
       - **Read the Summary:** Click **"View Summary Text"** for a quick AI-generated overview—ideal for deciding if it’s worth a full listen.
       - **Listen Up:** Hit **"▶️ Read Summary"** or **"▶️ Read Full"** to generate audio. A small player will appear below to play it directly in the app!
         - *Heads-Up:* Audio generation uses OpenAI’s API—summaries are fast, but full articles (especially long ones) may take a minute or two. Watch the spinner!

    3. **Save Your Audio:**
       - **⬇️ Download MP3:** After playing, download the MP3 to your device for offline listening—perfect for commutes or gym sessions.

    4. **Tweak the Experience:**
       - **Sidebar Settings:** Pick a voice (e.g., "Nova" for crisp, "Onyx" for deep) and speed (Normal to Fastest) before generating audio.
       - *Language Note:* Voices shine with English but can tackle other languages—pronunciation might get creative!

    ### Ideas to Supercharge Your Day
    - **Learn on the Go:** Convert research papers into audio for your morning walk.
    - **Stay Informed:** Summarize news and listen while cooking.
    - **Multitask:** Paste notes or emails, then hear them during your workout.

    ### Key Tips & Notes
    - **Audio Lifespan:** Files vanish when your session ends—download to keep!
    - **API Usage:** Summaries and audio use OpenAI credits—check your key’s balance.
    - **Troubleshooting:** URL fails? Paste text. Audio issues? Retry or download.
    """)

# --- Constants & Options ---
MAX_ARTICLES = 5
TTS_VOICES = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
TTS_SPEEDS = {"Normal": 1.0, "Slightly Faster": 1.15, "Faster": 1.25, "Fastest": 1.5}

# --- Check for OpenAI API Key ---
try:
    if "openai" not in st.secrets or "api_key" not in st.secrets["openai"]:
        raise KeyError("OpenAI API key not found in secrets.toml.")
    openai_api_key = st.secrets["openai"]["api_key"]
    if not openai_api_key or not openai_api_key.startswith("sk-"):
        raise ValueError("Invalid API Key format.")
except Exception as e:
    st.error(f"OpenAI API key error: {e}. Please ensure secrets.toml has `[openai]` section with `api_key = 'sk-...'`.")
    st.stop()

# --- Initialize Session State ---
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

# --- Callback Functions for Clearing Inputs ---
def clear_url_callback():
    st.session_state.url_input = ""

def clear_title_callback():
    st.session_state.manual_title_input = ""

def clear_text_callback():
    st.session_state.manual_text_input = ""

# --- Helper Functions ---
def get_article_index(article_id):
    for i, article in enumerate(st.session_state.articles):
        if article.get('id') == article_id:
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
        base_id = f"manual_{sanitized[:50]}"
        existing_ids = {a['id'] for a in st.session_state.articles}
        final_id = base_id
        count = 1
        while final_id in existing_ids:
            final_id = f"{base_id}_{count}"
            count += 1
        return final_id
    base_id = f"manual_{int(time.time())}"
    existing_ids = {a['id'] for a in st.session_state.articles}
    final_id = base_id
    count = 1
    while final_id in existing_ids:
        final_id = f"{base_id}_{count}"
        count += 1
    return final_id

# --- Sidebar Audio Settings ---
with st.sidebar:
    st.header("🎧 Audio Settings")
    st.session_state.selected_voice = st.selectbox(
        "Select Voice:", TTS_VOICES,
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
st.header("📝 Add New Article")
tab1, tab2 = st.tabs(["🌐 Add via URL", "📋 Add by Pasting Text"])

with tab1:
    col_url_input, col_url_clear = st.columns([4, 1])
    with col_url_input:
        st.text_input("URL:", key="url_input", placeholder="Enter URL of online article", disabled=st.session_state.processing)
    with col_url_clear:
        st.button("Clear URL", key="clear_url_btn", on_click=clear_url_callback, disabled=st.session_state.processing)
    add_url_button = st.button("Add Article from URL", key="add_url", disabled=st.session_state.processing or not st.session_state.url_input)

with tab2:
    col_title_input, col_title_clear = st.columns([4, 1])
    with col_title_input:
        st.text_input("Title:", key="manual_title_input", placeholder="Enter a Title for the article", disabled=st.session_state.processing)
    with col_title_clear:
        st.button("Clear Title", key="clear_title_btn", on_click=clear_title_callback, disabled=st.session_state.processing)
    col_text_input, col_text_clear = st.columns([4, 1])
    with col_text_input:
        st.text_area("Pasted Text:", height=200, key="manual_text_input", placeholder="Paste the full article text here", disabled=st.session_state.processing)
    with col_text_clear:
        st.button("Clear Text", key="clear_text_btn", on_click=clear_text_callback, disabled=st.session_state.processing)
    add_manual_button = st.button("Add Manual Article", key="add_manual", disabled=st.session_state.processing or not (st.session_state.manual_text_input and st.session_state.manual_title_input))

# --- Processing Logic ---
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
                    if summary is None and summary_error:
                        final_summary = None
                        final_error = f"Summarization failed: {summary_error}"
                    elif summary_error:
                        final_summary = summary
                        final_error = f"Processing note: {summary_error}"
                    else:
                        final_summary = summary
                        final_error = None
                    article_data_to_add = {
                        'id': manual_data['id'], 'title': manual_data['title'], 'full_text': manual_data['text'],
                        'summary': final_summary, 'error': final_error, 'is_manual': True,
                        'full_audio_path': None, 'summary_audio_path': None
                    }
                    if final_error and final_summary is None:
                        process_error_msg = final_error
                    elif not final_error:
                        process_success_message = f"Manual article '{manual_data['title']}' processed."
            else:
                url_to_process = target_id
                if url_to_process:
                    content_data, fetch_error = fetch_article_content(url_to_process)
                    if fetch_error or not content_data:
                        process_error_msg = f"URL Processing Error: {fetch_error or 'Could not retrieve content.'}"
                    else:
                        summary, summary_error = summarize_text(content_data['text'], openai_api_key)
                        if summary is None and summary_error:
                            final_summary = None
                            combined_error = f"Summarization failed: {summary_error}"
                        elif summary_error:
                            final_summary = summary
                            combined_error = f"Summary note: {summary_error}"
                        else:
                            final_summary = summary
                            combined_error = None
                        final_processing_error = fetch_error or combined_error
                        article_data_to_add = {
                            'id': url_to_process, 'title': content_data['title'], 'full_text': content_data['text'],
                            'summary': final_summary, 'error': final_processing_error, 'is_manual': False,
                            'full_audio_path': None, 'summary_audio_path': None
                        }
                        if fetch_error:
                            process_error_msg = f"URL Fetch Error: {fetch_error}"
                        elif final_processing_error and final_summary is None:
                            process_error_msg = f"Summarization error: {summary_error}"
                        elif not final_processing_error:
                            process_success_message = f"Article '{content_data['title']}' processed."
        except Exception as e:
            process_error_msg = f"Unexpected error: {e}"
            logging.error(f"Processing error: {e}", exc_info=True)
        finally:
            st.session_state.processing = False
            st.session_state.processing_target = None
            st.session_state.manual_data = None
            st.session_state.last_process_success = process_success_message
            st.session_state.last_process_error = process_error_msg
            if article_data_to_add:
                if not any(a['id'] == article_data_to_add['id'] for a in st.session_state.articles):
                    st.session_state.articles.append(article_data_to_add)
                    st.session_state.selected_article_id = article_data_to_add['id']
                    cleanup_audio_files(get_active_audio_paths())
            st.rerun()

if add_url_button:
    url_to_add = st.session_state.url_input
    if len(st.session_state.articles) >= MAX_ARTICLES:
        st.warning(f"Maximum {MAX_ARTICLES} articles allowed.")
    elif any(article.get('id') == url_to_add for article in st.session_state.articles):
        st.warning("This URL has already been added.")
    else:
        st.session_state.processing = True
        st.session_state.processing_target = url_to_add
        st.rerun()

if add_manual_button:
    if len(st.session_state.articles) >= MAX_ARTICLES:
        st.warning(f"Maximum {MAX_ARTICLES} articles allowed.")
    else:
        manual_title = st.session_state.manual_title_input
        manual_text = st.session_state.manual_text_input
        manual_id = create_manual_id(manual_title)
        st.session_state.manual_data = {"title": manual_title, "text": manual_text, "id": manual_id}
        st.session_state.processing = True
        st.session_state.processing_target = manual_id
        st.rerun()

# --- Display Processing Results ---
if 'last_process_success' in st.session_state and st.session_state.last_process_success:
    st.success(st.session_state.last_process_success)
    del st.session_state.last_process_success
if 'last_process_error' in st.session_state and st.session_state.last_process_error:
    st.error(st.session_state.last_process_error)
    del st.session_state.last_process_error

# --- Display and Interact with Articles ---
st.header("🎙️ Your Articles")
if not st.session_state.articles:
    st.info("No articles added yet. Use the sections above.")
else:
    article_options = {a['id']: f"{a['title']} ({'Pasted' if a.get('is_manual', False) else a.get('id', 'Unknown ID')[:30]}...)" for a in st.session_state.articles}
    current_ids = list(article_options.keys())
    if st.session_state.selected_article_id not in current_ids:
        st.session_state.selected_article_id = current_ids[0] if current_ids else None

    selected_id = st.selectbox(
        "Choose article to view/read:",
        options=current_ids,
        format_func=lambda article_id: article_options.get(article_id, "Unknown Article"),
        index=current_ids.index(st.session_state.selected_article_id) if st.session_state.selected_article_id in current_ids else 0,
        key="article_selector",
        label_visibility="collapsed"
    )
    if selected_id != st.session_state.selected_article_id:
        st.session_state.selected_article_id = selected_id
        st.rerun()

    if st.session_state.selected_article_id:
        selected_index = get_article_index(st.session_state.selected_article_id)
        if selected_index != -1:
            article_data = st.session_state.articles[selected_index]
            st.subheader(f"{article_data.get('title', 'No Title')}")
            st.caption(f"Source: {'Manually Pasted Text' if article_data.get('is_manual', False) else article_data.get('id', 'Unknown URL')}")
            if article_data.get('error'):
                st.warning(f"Processing Note: {article_data['error']}")

            with st.expander("View Summary Text"):
                summary_text_display = article_data.get('summary')
                if summary_text_display:
                    st.write(summary_text_display)
                else:
                    st.info("No summary could be generated.")

            col1, col2, col3 = st.columns([1, 1, 1])
            button_key_prefix = get_valid_filename(article_data.get('id', f'no_id_{selected_index}'))[:20]

            with col1:
                read_summary_button = st.button(
                    "▶️ Read Summary",
                    key=f"sum_{button_key_prefix}",
                    disabled=st.session_state.processing or not article_data.get('summary')
                )
                if not article_data.get('summary'):
                    col1.caption("(Summary unavailable)")

            with col2:
                read_full_button = st.button(
                    "▶️ Read Full",
                    key=f"full_{button_key_prefix}",
                    disabled=st.session_state.processing or not article_data.get('full_text')
                )
                full_text_len = len(article_data.get('full_text', ''))
                if full_text_len > 4000 and not read_full_button:
                    col2.caption("⚠️ Full text is long.")
                elif not article_data.get('full_text'):
                    col2.caption("(Full text unavailable)")

            with col3:
                delete_button = st.button("🗑️ Delete", key=f"del_{button_key_prefix}", disabled=st.session_state.processing)

            audio_status_placeholder = st.empty()
            audio_controls_placeholder = st.empty()

            def handle_audio_request(text_type, text_content):
                audio_path_key = f"{text_type}_audio_path"
                audio_path = article_data.get(audio_path_key)
                audio_ready = False
                audio_bytes = None

                if audio_path and os.path.exists(audio_path):
                    try:
                        with open(audio_path, "rb") as f:
                            audio_bytes = f.read()
                        if audio_bytes:
                            audio_ready = True
                        else:
                            os.remove(audio_path)
                            st.session_state.articles[selected_index][audio_path_key] = None
                            audio_status_placeholder.warning("Previous audio file was invalid.")
                    except Exception as e:
                        audio_status_placeholder.warning(f"Could not load audio: {e}.")
                        st.session_state.articles[selected_index][audio_path_key] = None

                if not audio_ready:
                    is_valid_summary = text_type == "summary" and text_content
                    is_valid_full = text_type == "full" and text_content
                    if not (is_valid_summary or is_valid_full):
                        audio_status_placeholder.warning(f"No valid {text_type} text available.")
                        return

                    audio_status_placeholder.info(f"Generating {text_type} audio...")
                    with st.spinner(f"Generating {text_type} audio..."):
                        try:
                            filepath, audio_error = generate_audio(
                                text_content, openai_api_key, article_data['id'], text_type,
                                voice=st.session_state.selected_voice, speed=st.session_state.selected_speed
                            )
                            if audio_error:
                                audio_status_placeholder.error(f"Audio Generation Error: {audio_error}")
                                st.session_state.articles[selected_index][audio_path_key] = None
                            elif filepath:
                                st.session_state.articles[selected_index][audio_path_key] = filepath
                                st.rerun()
                        except Exception as e:
                            audio_status_placeholder.error(f"Generation Error: {e}")
                            logging.error(f"TTS Exception: {e}", exc_info=True)
                            st.session_state.articles[selected_index][audio_path_key] = None
                            return

                if audio_ready and audio_bytes:
                    audio_status_placeholder.empty()
                    audio_controls_placeholder.audio(audio_bytes, format="audio/mpeg")
                    audio_controls_placeholder.download_button(
                        label="⬇️ Download MP3",
                        data=audio_bytes,
                        file_name=f"{get_valid_filename(article_data['title'])}_{text_type}.mp3",
                        mime="audio/mpeg",
                        key=f"dl_{button_key_prefix}_{text_type}"
                    )

            if read_summary_button:
                handle_audio_request("summary", article_data.get('summary'))
            elif read_full_button:
                handle_audio_request("full", article_data.get('full_text'))
            else:
                summary_audio_path = article_data.get('summary_audio_path')
                full_audio_path = article_data.get('full_audio_path')
                if summary_audio_path and os.path.exists(summary_audio_path):
                    handle_audio_request("summary", article_data.get('summary'))
                elif full_audio_path and os.path.exists(full_audio_path):
                    handle_audio_request("full", article_data.get('full_text'))

            if delete_button:
                id_to_delete = article_data['id']
                logging.info(f"Attempting to delete article: {id_to_delete}")
                index_to_delete = get_article_index(id_to_delete)
                if index_to_delete != -1:
                    deleted_article_data = st.session_state.articles.pop(index_to_delete)
                    st.success(f"Article '{deleted_article_data.get('title', 'Untitled')}' deleted.")
                    paths_to_delete = [
                        deleted_article_data.get('full_audio_path'),
                        deleted_article_data.get('summary_audio_path')
                    ]
                    for path in paths_to_delete:
                        if path and os.path.exists(path):
                            try:
                                os.remove(path)
                                logging.info(f"Deleted audio file: {path}")
                            except Exception as e:
                                logging.error(f"Error deleting audio file {path}: {e}")
                    st.session_state.selected_article_id = None
                    audio_status_placeholder.empty()
                    audio_controls_placeholder.empty()
                    st.rerun()
                else:
                    st.error("Could not find article to delete.")
