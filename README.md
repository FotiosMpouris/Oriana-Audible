# Oriana: Article Summarizer & Reader ✨

![Oriana Logo](orianalogo.png)

Oriana is a web application built with Streamlit that allows you to summarize online articles and listen to either the full text or the summary using OpenAI's Text-to-Speech technology. Add articles via URL or by pasting text, customize the reading voice and speed, handle long articles via automatic chunking, and download the generated audio for offline listening.

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://YOUR_STREAMLIT_APP_URL_HERE) <-- **Replace with your deployed app URL!**

## Features

*   **Add Articles via URL:** Fetch content directly from online articles.
*   **Add Articles via Text:** Paste article content manually if URL fetching fails or is preferred.
*   **AI Summarization:** Uses the OpenAI API (GPT models) to generate summaries of the article content.
*   **Multi-Language Summaries:** Attempts to detect the language of the input text and summarize in that language (e.g., Greek).
*   **OpenAI Text-to-Speech (TTS):** Generates audio for both the full article text and the summary using OpenAI TTS.
*   **Long Article Handling:** Automatically chunks text exceeding API limits and concatenates the resulting audio segments for seamless playback.
*   **Customizable Audio:** Select different OpenAI voices (Alloy, Echo, etc.) and adjust playback speed (0.25x - 4.0x).
*   **Download Audio:** Download generated summaries or full article readings as MP3 files.
*   **Manage Articles:** Select from loaded articles, view summaries, and delete articles when finished (up to 5 active articles).
*   **User-Friendly UI:** Includes clear buttons for inputs and an instructional guide.

## Tech Stack

*   **Language:** Python 3
*   **Framework:** Streamlit
*   **AI Services:** OpenAI API (GPT for Summarization, TTS-1 for Audio)
*   **Core Libraries:**
    *   `newspaper3k`: Article scraping
    *   `requests`, `beautifulsoup4`: Fallback HTML fetching/parsing
    *   `langdetect`: Language detection
    *   `pydub`: Audio segment concatenation (for long articles)
    *   `lxml`, `lxml_html_clean`: Dependencies for parsing
*   **Audio Processing Dependency:** FFmpeg (installed via `packages.txt`)

## Setup and Deployment on Streamlit Cloud

1.  **Prerequisites:**
    *   GitHub account.
    *   OpenAI API Key ([platform.openai.com/account/api-keys](https://platform.openai.com/account/api-keys)). Usage incurs costs.
    *   `orianalogo.png` file.

2.  **Repository Setup:**
    *   Create a **public** GitHub repository.
    *   Upload these files to the root:
        *   `app.py`
        *   `mainfunctions.py`
        *   `requirements.txt`
        *   `packages.txt`
        *   `orianalogo.png`

3.  **Streamlit Cloud Deployment:**
    *   Go to [share.streamlit.io](https://share.streamlit.io/).
    *   Click "New app" -> "From existing repo".
    *   Select your repository and branch (`main`).
    *   Ensure **Main file path:** is `app.py`.
    *   Click "Advanced settings...".
    *   **Secrets:** Add your OpenAI API key using this format:
        ```toml
        [openai]
        api_key = "sk-YOUR_ACTUAL_OPENAI_API_KEY_HERE"
        ```
    *   Click "Deploy!".

4.  **Wait** for the build process (installs system packages from `packages.txt` like `ffmpeg` and Python packages from `requirements.txt` like `pydub`).

5.  **(Optional)** Update the URL badge at the top of this README with your deployed app's link.

## How to Use Oriana

*(Refer to the "💡 Oriana: Concept & Usage Guide" expander within the application for detailed step-by-step instructions)*

1.  **Add Content:** Use URL or Paste Text tabs.
2.  **Select Article:** Choose from the dropdown.
3.  **View Summary:** Expand the summary section.
4.  **Configure Audio:** Set Voice and Speed in the sidebar (*these settings apply to the OpenAI TTS*).
5.  **Generate Audio:** Click "▶️ Read Summary" or "▶️ Read Full". Wait for processing (chunking happens automatically for long text).
6.  **Access Audio:** Click the "▶️ Read..." button *again* after the spinner disappears to show the embedded player and the "⬇️ Download MP3" button. Use the download button for reliability, especially on mobile or for long files.
7.  **Delete:** Remove articles using the "🗑️ Delete" button.

## Known Limitations (Current Version)

*   **URL Fetching:** Some sites block automated access. Use Paste Text as a workaround.
*   **Audio Persistence:** Audio is temporary (session-based). Download MP3s to save them.
*   **TTS Quality:** Uses OpenAI's standard TTS. Pronunciation of non-English text or complex symbols/numbers may vary in naturalness.
*   **API Costs:** Uses OpenAI API for summaries and TTS.
*   **Player Quirks:** Embedded player may not work reliably on all mobile browsers or with very long audio files. Download button is the recommended method.

## License

(Choose and add your license information here - e.g., MIT License)
