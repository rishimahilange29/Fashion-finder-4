import os, json, tempfile, subprocess
from pathlib import Path
from urllib.parse import quote_plus, urlparse

import cv2
import numpy as np
import streamlit as st
from google import genai
from google.genai import types
from groq import Groq

GEMINI_MODEL = "gemini-3.8-flash"
GROQ_MODEL = "qwen/qwen3.8-27b"

st.set_page_config(page_title="Reel Fashion Finder", page_icon="👗", layout="wide")
st.title("👗 Reel Fashion Finder")
st.write("Instagram Reel URL paste karein → keyframes → outfit items → Meesho / Flipkart search links")

with st.sidebar:
    st.subheader("Free AI keys")
    gemini_key = st.text_input("Gemini API key (primary)", type="password", value=os.getenv("GEMINI_API_KEY", ""))
    groq_key = st.text_input("Groq API key (backup)", type="password", value=os.getenv("GROQ_API_KEY", ""))
    st.caption("Keys sirf is app session mein use hoti hain. GitHub par kabhi upload na karein.")

st.warning(
    "App reel ko aapke liye automatically access karne ki koshish karega. Video ko permanent save nahi karta; "
    "frames nikalne ke liye stream temporary file mein fetch hoti hai aur kaam ke baad delete kar di jaati hai. "
    "Private/login-required reels kaam nahi kar sakti."
)
reel_url = st.text_input("Instagram Reel URL", placeholder="https://www.instagram.com/reel/...")
max_frames = st.slider("Important frames (sampling)", 3, 12, 8)

def validate_instagram_url(url):
    p = urlparse(url.strip())
    host = (p.hostname or "").lower()
    return host in {"instagram.com", "www.instagram.com"} and ("/reel/" in p.path or "/p/" in p.path)

def fetch_reel_temp(url, destination):
    # yt-dlp fetches the media into a temporary path solely for frame extraction.
    # It is not retained or offered as a video download.
    cmd = [
        "yt-dlp", "--no-warnings", "--no-playlist",
        "-f", "best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "-o", destination, url
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if result.returncode != 0 or not Path(destination).exists():
        msg = (result.stderr or result.stdout or "Instagram did not provide an accessible video stream.")[-1400:]
        raise RuntimeError(msg)

def extract_keyframes(path, max_count):
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise RuntimeError("Video stream open nahi hua.")
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    if total <= 0:
        cap.release()
        raise RuntimeError("Video frames read nahi ho paaye.")
    positions = np.linspace(0, total - 1, min(max_count, total)).astype(int)
    picked, prev_hist = [], None
    for pos in positions:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(pos))
        ok, frame = cap.read()
        if not ok:
            continue
        h, w = frame.shape[:2]
        frame = cv2.resize(frame, (768, max(1, int(h * 768 / w))))
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [24, 24], [0, 180, 0, 256])
        hist = cv2.normalize(hist, hist).flatten()
        if prev_hist is not None and cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CORREL) > 0.985:
            continue
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 86])
        if ok:
            picked.append((float(pos / fps), buf.tobytes()))
            prev_hist = hist
    cap.release()
    return picked

PROMPT = """You are a fashion visual search assistant. Inspect all provided video frames.
Identify distinct visible clothing and accessories across frames. Merge duplicates.
Return ONLY valid JSON in this exact schema:
{"outfit_summary":"short summary","items":[
{"item":"garment/accessory name","visual_description":"visible color, pattern, cut, style",
"search_query":"specific concise India shopping search phrase","confidence":"high/medium/low"}]}
Do not infer hidden brand names, material, or exact product identity. Use low confidence if unclear.
Include only items clearly visible."""

def parse_json(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("AI returned invalid JSON.")
    return json.loads(text[start:end+1])

def gemini_analyze(key, frames):
    client = genai.Client(api_key=key)
    content = [PROMPT]
    for sec, data in frames:
        content.extend([f"Frame at {sec:.1f} seconds", types.Part.from_bytes(data=data, mime_type="image/jpeg")])
    response = client.models.generate_content(
        model=GEMINI_MODEL, contents=content,
        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.2)
    )
    return parse_json(response.text)

def groq_analyze(key, frames):
    client = Groq(api_key=key)
    # Groq Qwen vision accepts up to 3 images per request.
    selected = frames if len(frames) <= 3 else [frames[0], frames[len(frames)//2], frames[-1]]
    content = [{"type": "text", "text": PROMPT}]
    for sec, data in selected:
        import base64
        b64 = base64.b64encode(data).decode("ascii")
        content.append({"type": "text", "text": f"Frame at {sec:.1f} seconds"})
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": content}],
        temperature=0.2,
        max_completion_tokens=1600
    )
    return parse_json(response.choices[0].message.content)

def analyze(frames):
    errors = []
    if gemini_key:
        try:
            return gemini_analyze(gemini_key, frames), "Gemini primary"
        except Exception as e:
            errors.append(f"Gemini: {e}")
    if groq_key:
        try:
            return groq_analyze(groq_key, frames), "Groq backup"
        except Exception as e:
            errors.append(f"Groq: {e}")
    if not gemini_key and not groq_key:
        raise RuntimeError("Sidebar mein kam se kam ek free API key enter karein.")
    raise RuntimeError("Dono AI services fail/limit par hain. " + " | ".join(errors)[-1800:])

def search_urls(query):
    q = quote_plus(query)
    return (
        f"https://www.meesho.com/search?q={q}",
        f"https://www.flipkart.com/search?q={q}"
    )

if st.button("Find products from Reel", type="primary", disabled=not reel_url.strip()):
    if not validate_instagram_url(reel_url):
        st.error("Valid Instagram Reel/Post URL paste karein.")
    else:
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as f:
                temp_path = f.name
            os.unlink(temp_path)  # yt-dlp creates this path
            with st.spinner("Instagram se accessible stream fetch karke keyframes nikaal rahe hain..."):
                fetch_reel_temp(reel_url.strip(), temp_path)
                frames = extract_keyframes(temp_path, max_frames)
            if not frames:
                raise RuntimeError("Koi usable frame nahi mila.")
            st.success(f"{len(frames)} important frames selected.")
            cols = st.columns(min(4, len(frames)))
            for i, (sec, img) in enumerate(frames):
                with cols[i % len(cols)]:
                    st.image(img, caption=f"{sec:.1f}s", use_container_width=True)
            with st.spinner("Gemini / Groq AI se fashion analysis..."):
                result, engine = analyze(frames)
            st.success(f"Analysis complete: {engine}")
            st.subheader("Outfit summary")
            st.write(result.get("outfit_summary", ""))
            items = result.get("items", [])
            if not items:
                st.info("Frames mein clear fashion products identify nahi hue.")
            for i, item in enumerate(items, 1):
                st.markdown(f"### {i}. {item.get('item', 'Fashion item')}")
                st.write(item.get("visual_description", ""))
                st.caption(f"Confidence: {item.get('confidence', 'not specified')}")
                q = item.get("search_query") or item.get("visual_description") or item.get("item", "fashion")
                meesho, flipkart = search_urls(q)
                a, b = st.columns(2)
                a.link_button("Meesho par dekhein", meesho, use_container_width=True)
                b.link_button("Flipkart par dekhein", flipkart, use_container_width=True)
            st.download_button("Analysis JSON download", json.dumps(result, ensure_ascii=False, indent=2),
                               "reel_fashion_results.json", "application/json")
        except Exception as e:
            st.error(f"Reel analyze nahi ho paayi: {e}")
            st.info("Private reel, Instagram login wall, rate limit, region restriction, ya unsupported stream ho sakta hai. Public reel URL try karein.")
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

st.divider()
st.caption(
    "Free-tier quotas fixed/guaranteed nahi hain aur badal sakti hain. AI visual similarity se search phrase banata hai; "
    "Meesho/Flipkart search results exact same product hone ki guarantee nahi hain. Purchase se pehle listing verify karein."
)
