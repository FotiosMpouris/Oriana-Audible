# Oriana: Article Summarizer & Reader ✨

![Oriana Logo](orianalogo.png)

Oriana is a web application built with Streamlit that allows you to summarize online articles and listen to either the full text or the summary. Add articles via URL or by pasting text, customize the reading voice and speed, and download the generated audio for offline listening.

## Features

*   **Add Articles via URL:** Fetch content directly from online articles.
*   **Add Articles via Text:** Paste article content manually if URL fetching fails or is preferred.
*   **AI Summarization:** Uses the OpenAI API to generate summaries of the article content.
*   **Multi-Language Summaries:** Attempts to detect the language of the input text and summarize in that language (e.g., Greek).
*   **Text-to-Speech (TTS):** Generates audio for both the full article text and the summary using OpenAI TTS.
*   **Customizable Audio:** Select different voices (Alloy, Echo, etc.) and adjust playback speed.
*   **Download Audio:** Download generated summaries or full article readings as MP3 files.
*   **Manage Articles:** Select from loaded articles, view summaries, and delete articles when finished (up to 5 active articles).
*   **User-Friendly UI:** Includes clear buttons for inputs and an instructional guide.

## Tech Stack

*   **Language:** Python 3
*   **Framework:** Streamlit (for UI and deployment)
*   **AI Services:** OpenAI API (GPT for Summarization, TTS for Audio)
*   **Core Libraries:**
    *   `newspaper3k`: Article scraping and content extraction
    *   `requests`, `beautifulsoup4`: Fallback HTTP requests and HTML parsing
    *   `langdetect`: Language detection for summaries
    *   `lxml`, `lxml_html_clean`: Dependencies for parsing

## Setup and Deployment on Streamlit Cloud

Follow these steps to deploy your own instance of Oriana:

1.  **Prerequisites:**
    *   A GitHub account.
    *   An OpenAI API Key ([platform.openai.com/account/api-keys](https://platform.openai.com/account/api-keys)). Note that API usage incurs costs.
    *   Your `orianalogo.png` file.
    *   (Optional) Python installed locally for testing ([python.org](https://www.python.org/)).

2.  **Prepare Your Repository:**
    *   Create a new **public** GitHub repository (e.g., `oriana-reader`). Streamlit Cloud free tier requires public repos.
    *   Upload the following files to the root of your repository:
        *   `app.py` (Main application code)
        *   `mainfunctions.py` (Core logic for fetching, summarizing, TTS)
        *   `requirements.txt` (Python package dependencies)
        *   `packages.txt` (System-level dependencies for `lxml`)
        *   `orianalogo.png` (Your application logo)

3.  **Deploy to Streamlit Cloud:**
    *   Go to [share.streamlit.io](https://share.streamlit.io/) and log in (using GitHub is easiest).
    *   Click "New app" -> "From existing repo".
    *   **Repository:** Select your `oriana-reader` repository.
    *   **Branch:** Select the main branch (usually `main` or `master`).
    *   **Main file path:** Ensure it's set to `app.py`.
    *   Click "Advanced settings...".
    *   **Secrets:** This is crucial! Paste your OpenAI API key in the following TOML format, replacing `sk-...` with your actual key:
        ```toml
        [openai]
        api_key = "sk-YOUR_ACTUAL_OPENAI_API_KEY_HERE"
        ```
        ***Do NOT commit your API key directly into your code or repository files.*** Use the Streamlit Secrets management as shown above.
    *   Click "Deploy!".

4.  **Wait:** Streamlit Cloud will build the environment (installing system packages from `packages.txt` and Python packages from `requirements.txt`) and launch your app. This might take a few minutes.

5.  **Update URL Badge (Optional):** Once deployed, copy your app's URL (e.g., `your-account.streamlit.app`) and paste it into the badge link at the top of this README file.

## How to Use Oriana

1.  **Add an Article:**
    *   Use the "Add via URL" tab, paste the URL, and click "Add Article from URL".
    *   *OR* Use the "Add by Pasting Text" tab, paste the text, enter a title, and click "Add Manual Article". Use the "Clear" buttons if needed.
2.  **Select Article:** Choose the article you want to work with from the "Your Articles" dropdown menu.
3.  **View Summary:** Expand the "View Summary Text" section.
4.  **Configure Audio (Optional):** Use the sidebar to select a preferred Voice and Speed *before* generating audio.
5.  **Generate & Listen/Download:**
    *   Click "▶️ Read Summary" or "▶️ Read Full". A spinner will indicate processing.
    *   After the spinner finishes, the app reruns. **You might need to click the same "▶️ Read..." button again** to display the audio player (if supported by your browser) and the "⬇️ Download MP3" button.
    *   Use the **Download button** to save the MP3 file locally. This is recommended for mobile playback or saving files.
6.  **Delete Article:** Click the "🗑️ Delete" button for the selected article to remove it from the list and clean up associated temporary files.

## Known Limitations

*   **URL Fetching:** Some websites actively block scraping attempts (returning 403 errors) or require logins/paywalls. Use the "Paste Text" feature for these sites.
*   **Audio Persistence:** Audio files generated are **temporary** and only exist for the current browser session due to Streamlit Cloud's ephemeral storage. Use the Download button to save audio permanently.
*   **Non-English TTS:** While summaries can be generated in detected languages (like Greek), the available TTS voices are primarily English-trained. Playback of non-English text might sound unnatural or have a strong English accent.
*   **Audio Player Display:** Due to Streamlit's execution model, you might need to click the "Read..." button a second time after audio generation finishes to see the player/download controls appear.
*   **API Costs:** Remember that generating summaries and audio uses the OpenAI API, which incurs costs based on your usage.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details (or choose/add your preferred license).
