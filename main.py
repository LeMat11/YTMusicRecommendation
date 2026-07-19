import os
import json
import re
import time
import socket  # NEW: For internet check
import logging # NEW: For file logging
from dotenv import load_dotenv
from typing import List, Dict, Any, Callable, Optional
from ytmusicapi import YTMusic
from ytmusicapi.auth.oauth.credentials import OAuthCredentials
from openai import OpenAI
import google.generativeai as genai

import db_manager  # your existing module

# =========================
# 0. Logging Configuration (NEW)
# =========================
# This creates a file named 'activity.log' in the same folder.
logging.basicConfig(
    filename='run_history.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# =========================
# 1. Load secrets
# =========================
load_dotenv()

# AI Backend: "stepfun" or "gemini"
AI_BACKEND = os.getenv("AI_BACKEND", "stepfun")

# Stepfun
STEPFUN_API_KEY = os.getenv("STEPFUN_API_KEY", "")
stepfun_client = OpenAI(
    api_key=STEPFUN_API_KEY,
    base_url="https://api.stepfun.com/v1",
)

# Gemini / Google Generative AI
GENAI_API_KEY = os.getenv("GENAI_API_KEY", "")
genai.configure(api_key=GENAI_API_KEY)

# YouTube Music OAuth client
YTMUSIC_CLIENT_ID = os.getenv("YTMUSIC_CLIENT_ID", "")
YTMUSIC_CLIENT_SECRET = os.getenv("YTMUSIC_CLIENT_SECRET", "")

OAUTH_CREDS = OAuthCredentials(
    client_id=YTMUSIC_CLIENT_ID,
    client_secret=YTMUSIC_CLIENT_SECRET,
)

# =========================
# 2. User configuration
# =========================
USERS_FILE = os.getenv("YTMUSIC_USERS_FILE", "users.local.json")


def load_users(path: str = USERS_FILE) -> List[Dict[str, Any]]:
    """Load private per-user settings from a gitignored JSON file."""
    try:
        with open(path, "r", encoding="utf-8") as config_file:
            users = json.load(config_file)
    except FileNotFoundError as exc:
        raise SystemExit(
            f"User configuration '{path}' was not found. "
            "Copy users.example.json to users.local.json and customize it."
        ) from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"User configuration '{path}' is not valid JSON: {exc}") from exc

    if not isinstance(users, list) or not users:
        raise SystemExit(f"User configuration '{path}' must contain a non-empty JSON list.")

    required = {"id", "auth_file", "playlist_name", "prompt_extra"}
    for index, user in enumerate(users, start=1):
        if not isinstance(user, dict):
            raise SystemExit(f"User entry {index} in '{path}' must be a JSON object.")
        missing = sorted(required - user.keys())
        if missing:
            raise SystemExit(
                f"User entry {index} in '{path}' is missing: {', '.join(missing)}"
            )

    return users

Track = str
FallbackFn = Callable[[YTMusic, int, set[Track]], List[Track]]

# =========================
# 3. New Robust Helper Functions
# =========================

def wait_for_internet(timeout=120):
    """
    Blocks execution until internet is available or timeout is reached.
    Essential for 'RunAtLoad' automation on macOS.
    """
    msg = "⏳ Checking internet connection..."
    print(msg)
    logging.info(msg)
    
    start_time = time.time()
    while True:
        try:
            # Try connecting to Google DNS to verify connection
            socket.create_connection(("8.8.8.8", 53), timeout=3)
            print("✅ Internet Connected.")
            logging.info("Internet Connected.")
            return True
        except OSError:
            pass
        
        if time.time() - start_time > timeout:
            err = "❌ Internet wait timed out. Aborting."
            print(err)
            logging.error(err)
            return False
            
        time.sleep(5)

def safe_search(yt: YTMusic, query: str, retries=3):
    """
    Wraps yt.search with retry logic to handle ReadTimeout errors.
    """
    for attempt in range(retries):
        try:
            results = yt.search(query, filter="songs")
            return results
        except Exception as e:
            warn = f"⚠️ Search error/timeout for '{query}'. Retrying {attempt+1}/{retries}..."
            logging.warning(warn)
            print(f"      {warn}")
            time.sleep(5) # Wait before retrying
            
    logging.error(f"❌ Failed to find '{query}' after {retries} attempts.")
    return []


# =========================
# 4. Existing Helpers (Unchanged)
# =========================

def get_liked_context(yt: YTMusic, limit: int = 100):
    print(f"   🎧 Fetching liked songs (limit={limit})...")
    try:
        liked = yt.get_liked_songs(limit=limit)
        tracks = liked.get("tracks", [])
        result = []
        for t in tracks:
            try:
                if not t.get("videoId"):
                    continue
                title = t.get("title") or "Unknown Title"
                artists = t.get("artists") or []
                artist_name = artists[0]["name"] if artists else "Unknown Artist"
                result.append(f"{title} - {artist_name}")
            except Exception:
                continue
        if not result:
            print("   ⚠️ No liked songs found.")
        return result
    except Exception as e:
        print(f"   ⚠️ Error reading liked songs: {e}")
        logging.error(f"Error reading liked songs: {e}")
        return []


def get_history_context(yt: YTMusic, limit: int = 100):
    print(f"   🎧 Fetching recent history (limit={limit})...")
    try:
        history = yt.get_history()[:limit]
        tracks = []
        for t in history:
            try:
                if not t.get("videoId"):
                    continue
                title = t.get("title") or "Unknown Title"
                artists = t.get("artists") or []
                artist_name = artists[0]["name"] if artists else "Unknown Artist"
                tracks.append(f"{title} - {artist_name}")
            except Exception:
                continue
        if not tracks:
            print("   ⚠️ History is empty.")
        return tracks
    except Exception as e:
        print(f"   ⚠️ Error reading history: {e}")
        logging.error(f"Error reading history: {e}")
        return []

def get_history_video_ids(yt: YTMusic, limit: int = 500) -> set[str]:
    print(f"   🎧 Fetching history videoIds (limit={limit})...")
    video_ids: set[str] = set()
    try:
        history = yt.get_history()[:limit]
        for t in history:
            vid = t.get("videoId")
            if vid:
                video_ids.add(vid)
    except Exception as e:
        print(f"   ⚠️ Error reading history for videoIds: {e}")
    return video_ids

def default_fallback_tracks(yt: YTMusic, limit: int, seen_tracks: set[Track]) -> List[Track]:
    """
    Simple default fallback: pull popular tracks from charts (US),
    and convert them to 'Title - Artist' strings.
    """
    try:
        charts = yt.get_charts("US")
    except Exception as e:
        logging.error(f"Error getting charts for fallback: {e}")
        return []

    fallback: List[Track] = []

    for item in charts.get("tracks", {}).get("items", []):
        try:
            title = item.get("title") or "Unknown Title"
            artists = item.get("artists") or []
            artist_name = artists[0].get("name") if artists else "Unknown Artist"
            track_str = f"{title} - {artist_name}"

            if track_str in seen_tracks:
                continue

            seen_tracks.add(track_str)
            fallback.append(track_str)

            if len(fallback) >= limit:
                break
        except Exception:
            continue

    return fallback


def get_taste_tracks(
    yt: YTMusic,
    source: str = "history",
    limit: int = 100,
    history_ratio: float = 0.5,  # e.g. 0.5 => half history, half liked (for mixed mode)
    fallback_fn: Optional[FallbackFn] = default_fallback_tracks,
) -> List[Track]:
    """
    Get tracks representing the user's 'taste'.

    Modes:
      - history: history only (strings: "Title - Artist")
      - liked: liked songs only (strings)
      - auto: history, fall back to liked, then fallback_fn if still empty
      - mixed/combined/both: ratio-based mix of history + liked, then fallback if not enough
    """
    source = (source or "history").lower()
    history_ratio = max(0.0, min(1.0, history_ratio))  # clamp to [0, 1]

    # --- Simple modes: history / liked ---
    if source == "history":
        return get_history_context(yt, limit=limit)

    if source == "liked":
        return get_liked_context(yt, limit=limit)

    # --- Auto mode: history -> liked -> fallback ---
    if source == "auto":
        tracks = get_history_context(yt, limit=limit) or []
        if tracks:
            return tracks[:limit]

        print("   ℹ️ Auto mode: history empty, falling back to liked songs.")
        tracks = get_liked_context(yt, limit=limit) or []
        if tracks:
            return tracks[:limit]

        # If still empty, use fallback (e.g., charts)
        if fallback_fn is not None:
            print("   ℹ️ Auto mode: history and liked empty, using fallback tracks.")
            seen = set(tracks)  # tracks are strings here (probably empty)
            extra = fallback_fn(yt, limit, seen)
            return extra[:limit]

        return []

    # --- Mixed / ratio-based mix of history + liked ---
    if source in ("mixed", "combined", "both"):
        history_tracks = get_history_context(yt, limit=limit) or []
        liked_tracks = get_liked_context(yt, limit=limit) or []

        combined: List[Track] = []
        seen: set[Track] = set()
        i = j = 0
        history_count = 0
        liked_count = 0

        # Interleave while trying to match the desired ratio
        while len(combined) < limit and (i < len(history_tracks) or j < len(liked_tracks)):
            # If one list is exhausted, use the other
            if i >= len(history_tracks) and j >= len(liked_tracks):
                break
            if i >= len(history_tracks):
                pick = "liked"
            elif j >= len(liked_tracks):
                pick = "history"
            else:
                total_so_far = history_count + liked_count
                desired_history = history_ratio * (total_so_far + 1)
                if history_count < desired_history:
                    pick = "history"
                else:
                    pick = "liked"

            if pick == "history":
                track = history_tracks[i]
                i += 1
                source_flag = "history"
            else:
                track = liked_tracks[j]
                j += 1
                source_flag = "liked"

            # Deduplicate by string
            if track in seen:
                continue

            seen.add(track)
            combined.append(track)
            if source_flag == "history":
                history_count += 1
            else:
                liked_count += 1

        # If we still don't have enough, use fallback (random-ish songs)
        if len(combined) < limit and fallback_fn is not None:
            remaining = limit - len(combined)
            extra = fallback_fn(yt, remaining, seen_tracks=seen)
            combined.extend(extra)

        return combined[:limit]

    # --- Fallback: unknown source => treat as history ---
    return get_history_context(yt, limit=limit)


def ask_gemini(recent_tracks, extra_instructions, rec_count: int = 15):
    """
    Call Stepfun to get song recommendations.

    - Asks for rec_count + 10 candidates to allow for filtering.
    - Expects a JSON list of {"title": ..., "artist": ...} objects.
    - Logs raw output in case of JSON parse issues.
    """
    print("   🧠 Asking Stepfun for suggestions...")
    logging.info(f"Asking Stepfun for {rec_count} recommendations.")

    request_count = rec_count + 10

    prompt = f"""
    Act as a music expert. I need {request_count} unique song recommendations.

    The User's Recent History / Taste:
    {", ".join(recent_tracks)}

    Specific Preferences/Mood for this user:
    {extra_instructions}

    RULES:
    1. Identify the taste profile based on history.
    2. Recommend {request_count} NEW songs not in the history list.
    3. Focus on "Hidden Gems" (High quality, but less repetitive than Top 40).
    4. Output strictly as a JSON List, with NO explanation text.

    JSON Format:
    [
      {{"title": "Song Title", "artist": "Artist Name"}},
      ...
    ]
    """

    try:
        if AI_BACKEND == "gemini":
            model = genai.GenerativeModel("gemini-2.5-flash")
            response = model.generate_content(prompt)
            raw = getattr(response, "text", None)
            if not raw:
                parts = []
                for cand in getattr(response, "candidates", []):
                    for part in getattr(cand.content, "parts", []):
                        if hasattr(part, "text") and part.text:
                            parts.append(part.text)
                raw = "\n".join(parts)
        else:  # stepfun (default)
            response = stepfun_client.chat.completions.create(
                model="step-3.5-flash",
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.choices[0].message.content

        backend_name = "Gemini" if AI_BACKEND == "gemini" else "Stepfun"

        if not raw:
            msg = f"{backend_name} returned empty text."
            print(f"   ❌ {msg}")
            logging.error(msg)
            return []

        # Keep a copy of the raw text for debugging
        logging.debug(f"{backend_name} raw output (first 500 chars): {raw[:500]}")

        # Strip common markdown fences
        text = raw.strip().replace("```json", "").replace("```", "").strip()

        # If the response doesn't start with '[', try to find the first JSON array in it
        if not text.lstrip().startswith("["):
            match = re.search(r"\[.*\]", text, re.DOTALL)
            if match:
                text = match.group(0)

        try:
            data = json.loads(text)
        except json.JSONDecodeError as je:
            logging.error(
                f"JSON decode error: {je}. Raw text snippet: {text[:500]}"
            )
            print(f"   ❌ JSON parse error from {backend_name}. See run_history.log for details.")
            return []

        if not isinstance(data, list):
            logging.error(f"{backend_name} output is not a list. Type: {type(data)}")
            print(f"   ❌ {backend_name} output is not a list.")
            return []

        cleaned = []
        for item in data:
            if not isinstance(item, dict):
                continue
            title = item.get("title")
            artist = item.get("artist")
            if title and artist:
                cleaned.append({"title": str(title), "artist": str(artist)})

        if not cleaned:
            logging.warning(f"{backend_name} returned no valid song objects.")
            print(f"   ❌ {backend_name} returned no usable song objects.")
            return []

        # Trim to request_count
        if len(cleaned) > request_count:
            cleaned = cleaned[:request_count]

        logging.info(f"{backend_name} returned {len(cleaned)} candidate songs.")
        return cleaned

    except Exception as e:
        print(f"   ❌ AI Error: {e}")
        logging.exception(f"AI Error when calling {backend_name}: {e}")
        return []


def process_user(user_conf):
    user_id = user_conf["id"]
    msg = f"STARTING PROCESS FOR: {user_id.upper()}"
    print(f"\n🚀 {msg}")
    logging.info(msg)

    auth_file = user_conf["auth_file"]

    if not os.path.exists(auth_file):
        err = f"Auth file not found: {auth_file}"
        print(f"   ❌ {err}")
        logging.error(err)
        return

    try:
        yt = YTMusic(
            auth_file,
            oauth_credentials=OAUTH_CREDS,
        )
        yt.get_library_playlists() # Verify connection
        print("   ✅ Logged in to YouTube Music")
    except Exception as e:
        err = f"Login failed: {e}"
        print(f"   ❌ {err}")
        logging.error(err)
        return

    # --- Taste Analysis & Deduplication ---
    past_recs = db_manager.get_recent_recommendations(user_id)
    history_ids = get_history_video_ids(yt, limit=500)
    played_recs = set(past_recs) & history_ids

    source = user_conf.get("source", "history")
    taste_limit = user_conf.get("taste_limit", 100)
    taste_tracks = get_taste_tracks(yt, source=source, limit=taste_limit)

    if len(taste_tracks) < 5:
        logging.warning(f"Skipping user {user_id}: insufficient taste data.")
        print(f"   ⚠️ Insufficient data, skipping user.")
        return

    rec_count = user_conf.get("rec_count", 15)
    recommendations = ask_gemini(taste_tracks, user_conf["prompt_extra"], rec_count=rec_count)
    if not recommendations:
        logging.info("No recommendations returned from Gemini.")
        print("   No recommendations from Gemini.")
        return

    # --- Playlist Logic ---
    target_pl_id = None
    playlists = yt.get_library_playlists()

    for pl in playlists:
        if pl.get("title") == user_conf["playlist_name"]:
            target_pl_id = pl.get("playlistId")
            break

    if not target_pl_id:
        print(f"   🔨 Creating new playlist: {user_conf['playlist_name']}")
        target_pl_id = yt.create_playlist(
            user_conf["playlist_name"],
            "AI-curated daily music recommendations",
        )

    # --- Search & Add ---
    ids_to_add = []
    print(f"   🔎 Searching {len(recommendations)} candidate songs...")

    for song in recommendations:
        if len(ids_to_add) >= rec_count:
            break

        title = song.get("title")
        artist = song.get("artist")
        query = f"{title} {artist}"

        # USE SAFE_SEARCH HERE
        search_results = safe_search(yt, query)

        if not search_results:
            print(f"      ❌ Not found: {title} - {artist}")
            continue

        match = search_results[0]
        vid = match.get("videoId")
        found_title = match.get("title", title)

        if not vid:
            continue

        if vid in played_recs:
            print(f"      SKIP (Played Recently): {found_title}")
            continue

        if vid in ids_to_add:
            continue

        ids_to_add.append(vid)
        db_manager.add_to_memory(user_id, vid, found_title)
        print(f"      ✅ OK: {found_title}")

    # --- Update Playlist ---
    if not ids_to_add:
        print(f"   No valid new songs found for {user_id}.")
        logging.info(f"No songs added for {user_id}.")
        return

    try:
        playlist_data = yt.get_playlist(target_pl_id)
        playlist_items = playlist_data.get("tracks", [])

        if playlist_items:
            # Clean old songs
            items_to_delete = [
                item for item in playlist_items
                if item.get("setVideoId") and item.get("videoId")
            ]
            if items_to_delete:
                print(f"      🧹 Clearing {len(items_to_delete)} old songs...")
                yt.remove_playlist_items(target_pl_id, items_to_delete)
    except Exception as e:
        logging.warning(f"Playlist cleanup failed: {e}")
        print(f"      ⚠️ Cleanup failed: {e}")

    yt.add_playlist_items(target_pl_id, ids_to_add)
    
    success_msg = f"Playlist refreshed with {len(ids_to_add)} new songs for {user_id}!"
    print(f"   🎉 {success_msg}")
    logging.info(success_msg)


def main():
    # 1. WAIT FOR INTERNET FIRST
    if not wait_for_internet():
        return # Stop if internet never comes back

    logging.info("--- Script Run Started ---")
    
    db_manager.init_db()
    for user in load_users():
        process_user(user)
        time.sleep(2)
        
    logging.info("--- Script Run Finished ---")

if __name__ == "__main__":
    main()
