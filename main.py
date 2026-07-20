import os
import json
import time
import re
import feedparser
import requests
from bs4 import BeautifulSoup

# CONFIGURATION ======================

# 1. Add all your favorite Facebook RSS feed URLs here (from RSS.app)
RSS_FEED_URLS = [
    os.getenv("RSS_FEED_1"),
    os.getenv("RSS_FEED_2"),
    os.getenv("RSS_FEED_3"),
    # Add more as needed: os.getenv("RSS_FEED_4"), etc.
]

# 2. Location mapping - Just add new entries as you grow
LOCATION_MAP = {
    "long_rest": {
        "keywords": ["the long rest"], #LOWER CASE ONLY!
        "webhook": os.getenv("DISCORD_WEBHOOK_LONG_REST"),
        "role_id": os.getenv("ROLE_ID_LONG_REST"),
        "label": "The Long Rest"
    },
    # ------ ADD NEW LOCATIONS BELOW THIS LINE -----
    # "bristol": {
    #     "keywords": ["bristol", "other"], #LOWER CASE ONLY!
    #     "webhook": os.getenv("DISCORD_WEBHOOK_BRISTOL"),
    #     "role_id": os.getenv("ROLE_ID_BRISTOL"),
    #     "label": "Bristol"
    # },
}

# Fallback for events that don't match any location
DEFAULT = {
    "webhook": os.getenv("DISCORD_WEBHOOK_DEFAULT"),
    "role_id": None,
    "label": "Other Location"
}

SEEN_FILE = "seen_warhorn.json"
CHECK_INTERVAL = 900          # 15 minutes
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; WarhornDiscordBot/1.0)"}

# HELPER FUNCTIONS ======================

def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)

def extract_warhorn_url(text: str):
    match = re.search(r'https?://(?:www\.)?warhorn\.net/[^\s<>"\']+', text, re.I)
    return match.group(0).rstrip(".,)") if match else None

def get_location(warhorn_url: str):
    """Return the matching location key or None"""
    try:
        r = requests.get(warhorn_url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        page_text = soup.get_text(" ", strip=True).lower()

        # Check every location's keywords
        for loc_key, config in LOCATION_MAP.items():
            for keyword in config["keywords"]:
                if keyword in page_text:
                    return loc_key

        return None
    except Exception as e:
        print(f"Error getting location from {warhorn_url}: {e}")
        return None

def post_to_discord(config: dict, title: str, warhorn_url: str, facebook_link: str):
    if not config.get("webhook"):
        print(f"No webhook set for {config['label']} - skipping")
        return

    content = ""
    if config.get("role_id"):
        content += f"<@&{config['role_id']}> "

    content += f"**New Warhorn Event - {config['label']}**\n"
    content += f"{title}\n"
    content += f"Warhorn: {warhorn_url}\n"
    if facebook_link:
        content += f"Facebook: {facebook_link}"

    try:
        r = requests.post(config["webhook"], json={"content": content}, timeout=10)
        r.raise_for_status()
        print(f"✓ Posted to {config['label']}")
    except Exception as e:
        print(f"Failed to post to Discord ({config['label']}): {e}")

# MAIN ======================

def main():
    print("Warhorn → Discord monitor started")
    print(f"Watching {len([u for u in RSS_FEED_URLS if u])} feed(s)")
    seen = load_seen()

    while True:
        try:
            for feed_url in RSS_FEED_URLS:
                if not feed_url:
                    continue

                feed = feedparser.parse(feed_url)

                for entry in feed.entries:
                    combined_text = f"{entry.get('title', '')} {entry.get('summary', '')} {entry.get('link', '')}"
                    warhorn_url = extract_warhorn_url(combined_text)

                    if not warhorn_url or warhorn_url in seen:
                        continue

                    print(f"\nNew Warhorn link found: {warhorn_url}")
                    location_key = get_location(warhorn_url)
                    config = LOCATION_MAP.get(location_key, DEFAULT)

                    post_to_discord(
                        config=config,
                        title=entry.get("title", "Untitled Event"),
                        warhorn_url=warhorn_url,
                        facebook_link=entry.get("link")
                    )

                    seen.add(warhorn_url)
                    save_seen(seen)

        except Exception as e:
            print(f"Error in main loop: {e}")

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
