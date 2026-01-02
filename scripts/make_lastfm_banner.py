import os
import time
import requests
from collections import Counter
from io import BytesIO
from PIL import Image, ImageOps

API_KEY = os.environ["LASTFM_API_KEY"]
USER = os.environ["LASTFM_USER"]

# ---- Settings you can tweak ----
LAST_N_LISTENS = 180       # matches your goal
GRID = 5                   # 5x5 quilt
TILE = 240                 # px per album tile
OUT_PATH = os.path.join("assets", "banner.jpg")
FALLBACK_COLOR = (18, 18, 18)
REQUEST_TIMEOUT = 20
# --------------------------------


def lastfm_get_recent_tracks(user: str, api_key: str, limit: int = 200):
    """
    Fetch up to `limit` recent tracks (Last.fm typically allows up to 200 
per request).
    We use limit=200 so we definitely cover the last 180 listens in one 
call.
    """
    url = "https://ws.audioscrobbler.com/2.0/"
    params = {
        "method": "user.getrecenttracks",
        "user": user,
        "api_key": api_key,
        "format": "json",
        "limit": str(limit),
        "extended": "1",
    }
    r = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    return r.json()


def pick_best_image_url(track: dict) -> str | None:
    """
    Track JSON includes an 'image' list with multiple sizes.
    We'll take the largest available (#text field).
    """
    images = track.get("image", []) or []
    for item in reversed(images):
        url = item.get("#text")
        if url:
            return url
    return None


def safe_album_key(track: dict) -> str | None:
    """
    Build a stable key for "artist — album".
    Skip if we can't identify album.
    """
    artist = None
    a = track.get("artist")
    if isinstance(a, dict):
        artist = a.get("name")
    elif isinstance(a, str):
        artist = a

    album = None
    al = track.get("album")
    if isinstance(al, dict):
        album = al.get("#text")
    elif isinstance(al, str):
        album = al

    if not artist or not album:
        return None

    artist = artist.strip()
    album = album.strip()
    if not artist or not album:
        return None

    return f"{artist} — {album}"


def download_and_fit(url: str, tile_size: int) -> Image.Image:
    """
    Download cover image and crop/fit to a square tile.
    If download fails, return a fallback tile.
    """
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        im = Image.open(BytesIO(resp.content)).convert("RGB")
        im = ImageOps.fit(im, (tile_size, tile_size), 
method=Image.Resampling.LANCZOS)
        return im
    except Exception:
        return Image.new("RGB", (tile_size, tile_size), FALLBACK_COLOR)


def main():
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)

    data = lastfm_get_recent_tracks(USER, API_KEY, limit=200)
    tracks = data.get("recenttracks", {}).get("track", []) or []
    if not tracks:
        raise RuntimeError("No tracks returned. CHECK LASTFM_USER / API key")

    # Take last N listens
    tracks = tracks[:LAST_N_LISTENS]

    # Count albums in that window + remember an image URL per album
    album_counts = Counter()
    album_image = {}

    for t in tracks:
        key = safe_album_key(t)
        if not key:
            continue
        album_counts[key] += 1

        if key not in album_image:
            img_url = pick_best_image_url(t)
            if img_url:
                album_image[key] = img_url

    top_albums = [k for k, _ in album_counts.most_common(GRID * GRID)]

    # Create canvas
    W = GRID * TILE
    H = GRID * TILE
    canvas = Image.new("RGB", (W, H), FALLBACK_COLOR)

    for idx, album_key in enumerate(top_albums):
        row = idx // GRID
        col = idx % GRID
        x = col * TILE
        y = row * TILE

        url = album_image.get(album_key)
        tile = download_and_fit(url, TILE) if url else Image.new("RGB", 
(TILE, TILE), FALLBACK_COLOR)
        canvas.paste(tile, (x, y))

        # tiny polite delay so we don't hammer cover hosts
        time.sleep(0.05)

    canvas.save(OUT_PATH, quality=92, optimize=True)
    print(f"Saved {OUT_PATH} ({W}x{H}) with {len(top_albums)} albums.")


if __name__ == "__main__":
    main()


