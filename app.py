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
    page_icon="🎙️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Custom CSS ---
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

# --- Header ---
LOGO_PATH = "orianalogo.png"
col_logo, col_title = st.columns([1, 4])
with col_logo:
    if os.path.exists(LOGO_PATH):
        st.image(LOGO_PATH, width=120)
    else:
        st.warning("Logo missing!")
with col_title:
    st.title("Oriana Audible")
    st.caption("Inspired by Oriana Fallaci—Turn Articles into Audio Magic")

# --- Instructions ---
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
       - **Listen Up:** Hit **"▶️ Read Summary"** or **"▶️ Read Full"** to hear it aloud with your chosen voice and speed (set in the sidebar).
         - *Heads-Up:* Audio generation uses OpenAI’s API—summaries are fast, but full articles (especially long ones) may take a minute or two. Watch the spinner!

    3. **Get Your Audio:**
       - **▶️ Try Playing Directly:** Opens in new tab or media player—handy but quirky on some mobiles or with big files.
       - **⬇️ Download MP3:** The foolproof choice! Save it to your device for offline listening—perfect for commutes or gym sessions.

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

# --- API Key Check ---
try:
    if "openai" not in st.secrets or "api_key" not in st.secrets["openai"]:
        raise KeyError("OpenAI API key not found in secrets.toml.")
    openai_api_key = st.secrets["openai"]["api_key"]
    if not openai_api_key or not openai_api_key.startswith("sk-"):
        raise ValueError("Invalid API Key format.")
except Exception as e:
    st.error(f"API Key Error: {e}. Add a valid key in secrets.toml under [openai].")
    st.stop()

# --- Session State Initialization ---
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

# --- Callbacks ---
def clear_url_callback():
    st.session_state.url_input = ""

def clear_title_callback():
    st.session_state.manual_title_input = ""

def clear_text_callback():
    st.session_state.manual_text_input = ""

# --- Helpers ---
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
    return f"manual_{int(time.time())}"

# --- Sidebar ---
with st.sidebar:
    st.header("🎧 Audio Settings")
    st.session_state.selected_voice = st.selectbox(
        "Voice", TTS_VOICES, index=TTS_VOICES.index(st.session_state.selected_voice),
        help="Choose a voice for your audio."
    )
    current_speed_name = [k for k, v in TTS_SPEEDS.items() if v == st.session_state.selected_speed][0]
    selected_speed_name = st.select_slider(
        "Speed", options=list(TTS_SPEEDS.keys()), value=current_speed_name,
        help="Adjust playback speed."
    )
    st.session_state.selected_speed = TTS_SPEEDS[selected_speed_name]
    st.info("Voices are English-optimized but can read other languages.")

# --- Input Area ---
st.header("📝 Add Your Article")
tab1, tab2 = st.tabs(["🌐 From URL", "📋 Paste Text"])

with tab1:
    col_url, col_clear = st.columns([3, 1])
    with col_url:
        st.text_input("Article URL", key="url_input", placeholder="e.g., https://news.com/story")
    with col_clear:
        st.button("Clear", on_click=clear_url_callback, key="clear_url")
    add_url_button = st.button("Add Article from URL", key="add_url", disabled=st.session_state.processing or not st.session_state.url_input)

with tab2:
    col_title, col_clear_title = st.columns([3, 1])
    with col_title:
        st.text_input("Title", key="manual_title_input", placeholder="e.g., My Article")
    with col_clear_title:
        st.button("Clear", on_click=clear_title_callback, key="clear_title")
    col_text, col_clear_text = st.columns([3, 1])
    with col_text:
        st.text_area("Text", key="manual_text_input", height=150, placeholder="Paste article text here...")
    with col_clear_text:
        st.button("Clear", on_click=clear_text_callback, key="clear_text")
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
            process_error_msg = f"Unexpected Error: {e}"
            logging.error(f"Processing error: {e}", exc_info=True)
        finally:
            st.session_state.processing = False
            st.session_state.processing_target = None
            st.session_state.manual_data = None
            st.session_state.last_process_success = process_success_message
            st.session_state.last_process_error = process_error_msg
            if article_data_to_add and not any(a['id'] == article_data_to_add['id'] for a in st.session_state.articles):
                st.session_state.articles.append(article_data_to_add)
                st.session_state.selected_article_id = article_data_to_add['id']
                cleanup_audio_files(get_active_audio_paths())
            st.rerun()

if add_url_button and not st.session_state.processing:
    if len(st.session_state.articles) >= MAX_ARTICLES:
        st.warning(f"Maximum {MAX_ARTICLES} articles reached.")
    elif any(article.get('id') == st.session_state.url_input for article in st.session_state.articles):
        st.warning("This URL is already added.")
    else:
        st.session_state.processing = True
        st.session_state.processing_target = st.session_state.url_input
        st.rerun()

if add_manual_button and not st.session_state.processing:
    if len(st.session_state.articles) >= MAX_ARTICLES:
        st.warning(f"Maximum {MAX_ARTICLES} articles reached.")
    else:
        manual_title = st.session_state.manual_title_input
        manual_text = st.session_state.manual_text_input
        manual_id = create_manual_id(manual_title)
        st.session_state.manual_data = {"title": manual_title, "text": manual_text, "id": manual_id}
        st.session_state.processing = True
        st.session_state.processing_target = manual_id
        st.rerun()

# --- Display Results ---
if 'last_process_success' in st.session_state and st.session_state.last_process_success:
    st.success(st.session_state.last_process_success)
    del st.session_state.last_process_success
if 'last_process_error' in st.session_state and st.session_state.last_process_error:
    st.error(st.session_state.last_process_error)
    del st.session_state.last_process_error

# --- Articles Section ---
st.header("🎙️ Your Articles")
if not st.session_state.articles:
    st.info("Add an article above to get started!")
else:
    article_options = {a['id']: f"{a['title']} ({'Pasted' if a.get('is_manual', False) else a.get('id', 'Unknown')[:20]}...)" for a in st.session_state.articles}
    current_ids = list(article_options.keys())
    if st.session_state.selected_article_id not in current_ids:
        st.session_state.selected_article_id = current_ids[0] if current_ids else None

    selected_id = st.selectbox(
        "Select an Article", current_ids,
        format_func=lambda article_id: article_options.get(article_id, "Unknown"),
        index=current_ids.index(st.session_state.selected_article_id) if st.session_state.selected_article_id in current_ids else 0
    )
    if selected_id != st.session_state.selected_article_id:
        st.session_state.selected_article_id = selected_id
        st.rerun()

    if st.session_state.selected_article_id:
        selected_index = get_article_index(st.session_state.selected_article_id)
        if selected_index != -1:
            article_data = st.session_state.articles[selected_index]
            st.subheader(article_data.get('title', 'Untitled'))
            st.caption(f"Source: {'Pasted Text' if article_data.get('is_manual', False) else article_data.get('id', 'Unknown')}")
            if article_data.get('error'):
                st.warning(f"Note: {article_data['error']}")

            with st.expander("📄 Summary", expanded=False):
                summary = article_data.get('summary')
                st.write(summary if summary else "No summary available.")

            col1, col2, col3 = st.columns(3)
            button_key_prefix = get_valid_filename(article_data.get('id', f'no_id_{selected_index}'))[:20]
            with col1:
                read_summary_button = st.button("▶️ Read Summary", key=f"sum_{button_key_prefix}", disabled=st.session_state.processing or not article_data.get('summary'))
            with col2:
                read_full_button = st.button("▶️ Read Full", key=f"full_{button_key_prefix}", disabled=st.session_state.processing or not article_data.get('full_text'))
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
                            audio_status_placeholder.warning("Previous audio invalid. Regenerate.")
                    except Exception as e:
                        audio_status_placeholder.warning(f"Audio load error: {e}. Regenerating needed.")
                        st.session_state.articles[selected_index][audio_path_key] = None

                if not audio_ready and text_content:
                    audio_status_placeholder.info(f"Generating {text_type} audio...")
                    with st.spinner(f"Creating {text_type} audio..."):
                        filepath, audio_error = generate_audio(
                            text_content, openai_api_key, article_data['id'], text_type,
                            voice=st.session_state.selected_voice, speed=st.session_state.selected_speed
                        )
                        if audio_error:
                            audio_status_placeholder.error(f"Error: {audio_error}")
                            st.session_state.articles[selected_index][audio_path_key] = None
                        elif filepath:
                            st.session_state.articles[selected_index][audio_path_key] = filepath
                            st.rerun()

                if audio_ready and audio_bytes:
                    audio_status_placeholder.empty()
                    col_play, col_dl = audio_controls_placeholder.columns(2)
                    with col_play:
                        b64 = base64.b64encode(audio_bytes).decode()
                        play_link = f'<a href="data:audio/mpeg;base64,{b64}" target="_blank" download="{get_valid_filename(article_data["title"])}_{text_type}.mp3">▶️ Try Playing</a>'
                        st.markdown(play_link, unsafe_allow_html=True)
                        st.caption("(May fail on mobile/large files)")
                    with col_dl:
                        st.download_button(
                            "⬇️ Download MP3", audio_bytes, f"{get_valid_filename(article_data['title'])}_{text_type}.mp3",
                            mime="audio/mpeg", key=f"dl_{button_key_prefix}_{text_type}"
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
                index_to_delete = get_article_index(id_to_delete)
                if index_to_delete != -1:
                    deleted_article = st.session_state.articles.pop(index_to_delete)
                    st.success(f"Deleted '{deleted_article.get('title', 'Untitled')}'")
                    paths_to_delete = [deleted_article.get('full_audio_path'), deleted_article.get('summary_audio_path')]
                    for path in paths_to_delete:
                        if path and os.path.exists(path):
                            try:
                                os.remove(path)
                                logging.info(f"Deleted audio file: {path}")
                            except Exception as e:
                                logging.error(f"Error deleting audio: {e}")
                    st.session_state.selected_article_id = None
                    audio_status_placeholder.empty()
                    audio_controls_placeholder.empty()
                    st.rerun()
