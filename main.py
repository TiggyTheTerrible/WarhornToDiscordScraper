import os
import json
import re
import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone

# CONFIGURATION ======================

RSS_FEED_URLS = [
    os.getenv("RSS_FEED_1"),
    os.getenv("RSS_FEED_2"),
    os.getenv("RSS_FEED_3"),
    # Add more feeds here if needed
]

LOCATION_MAP = {
    "long_rest": {
        "keywords": ["the long rest"], #LOWER CASE ONLY!
        "webhook": os.getenv("DISCORD_WEBHOOK_LONG_REST"),
        "role_id": os.getenv("ROLE_ID_LONG_REST"),
        "label": "The Long Rest"
    },
    # Add new locations below ===
        #"long_rest": {
        #"keywords": ["the long rest", "long code file"],
        #"webhook": os.getenv("DISCORD_WEBHOOK_LONG_REST"),
        #"role_id": os.getenv("ROLE_ID_LONG_REST"),
        #"label": "The Long Rest"
    #},
}

DEFAULT = {
    "webhook": os.getenv("DISCORD_WEBHOOK_DEFAULT"),
    "role_id": None,
    "label": "Other Location"
}

SEEN_FILE = "seen_warhorn.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; WarhornDiscordBot/1.0)"}

# HELPERS ======================

def load_seen():
    if not os.path.exists(SEEN_FILE):
        return set()
    try:
        with open(SEEN_FILE, "r") as f:
            content = f.read().strip()
            if not content:
                return set()
            return set(json.loads(content))
    except (json.JSONDecodeError, ValueError):
        print("Warning: seen_warhorn.json is invalid or empty. Starting fresh.")
        return set()

def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(sorted(list(seen)), f, indent=2)

def extract_warhorn_url(text: str):
    match = re.search(r'https?://(?:www\.)?warhorn\.net/[^\s<>"\']+', text, re.I)
    return match.group(0).rstrip(".,)") if match else None

def get_location(warhorn_url: str):
    try:
        r = requests.get(warhorn_url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        page_text = soup.get_text(" ", strip=True).lower()

        for loc_key, config in LOCATION_MAP.items():
            for keyword in config["keywords"]:
                if keyword in page_text:
                    return loc_key
        return None
    except Exception as e:
        print(f"Error fetching location: {e}")
        return None

def post_to_discord(config, title, warhorn_url, facebook_link):
    if not config.get("webhook"):
        print(f"No webhook for {config['label']} - skipping")
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
        print(f"Failed to post ({config['label']}): {e}")

# MAIN ======================

def main():
    print(f"Run started at {datetime.now(timezone.utc).isoformat()}")
    seen = load_seen()
    new_count = 0

    for feed_url in RSS_FEED_URLS:
        if not feed_url:
            continue

        print(f"Checking feed: {feed_url}")
        feed = feedparser.parse(feed_url)

        for entry in feed.entries:
            text = f"{entry.get('title', '')} {entry.get('summary', '')} {entry.get('link', '')}"
            warhorn_url = extract_warhorn_url(text)

            if not warhorn_url or warhorn_url in seen:
                continue

            print(f"New Warhorn link: {warhorn_url}")
            location_key = get_location(warhorn_url)
            config = LOCATION_MAP.get(location_key, DEFAULT)

            post_to_discord(
                config=config,
                title=entry.get("title", "Untitled Event"),
                warhorn_url=warhorn_url,
                facebook_link=entry.get("link")
            )

            seen.add(warhorn_url)
            new_count += 1

    save_seen(seen)
    print(f"Finished. {new_count} new event(s) posted.")

if __name__ == "__main__":
    main()
