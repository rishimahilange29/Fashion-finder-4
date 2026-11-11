# Reel Fashion Finder v2

Paste an Instagram Reel URL. The app attempts to fetch an accessible media stream temporarily, extracts representative keyframes, analyzes fashion items with Gemini first and Groq Vision as fallback, then creates Meesho and Flipkart search links per item.

## Important reality checks
- No manual video upload is required. The backend temporarily fetches the reel stream to decode frames; it deletes the temporary video after analysis and does not retain a video library.
- Instagram often blocks unauthenticated access. Private, login-required, age-restricted, or rate-limited Reels may fail. This cannot be guaranteed to work for every URL.
- Do not provide Instagram passwords or session cookies to this app. Use only public content you are allowed to process.
- Product buttons open marketplace search results, not verified exact product pages. This app does not claim exact matches or guaranteed prices.
- Free API plans have quotas and can change. If Gemini fails due to quota and a Groq key is configured, the app switches to Groq. If both fail, it reports the error; no paid billing is required by this code.

## Free API keys
- Gemini: https://aistudio.google.com/api-keys
- Groq: https://console.groq.com/keys

Create keys using the providers' free developer tier where available. Never commit keys to GitHub.

## Run locally
```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt
```
Set environment variables:
```bash
# macOS/Linux
export GEMINI_API_KEY="..."
export GROQ_API_KEY="..."
# Windows PowerShell
$env:GEMINI_API_KEY="..."
$env:GROQ_API_KEY="..."
```
Then:
```bash
streamlit run app.py
```
You can also paste keys into the sidebar.

## GitHub
```bash
git init
git add .
git commit -m "Reel Fashion Finder v2"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/reel-fashion-finder.git
git push -u origin main
```

## Model IDs
- Gemini primary: `gemini-3.8-flash`
- Groq vision fallback: `qwen/qwen3.8-27b`

Check current model access and free-tier quotas in provider dashboards/docs before running. Model access may vary by account and region.
