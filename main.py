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

        # 1. Check the dedicated event location meta tag
        location_meta = soup.find("meta", property="event:location")
        if location_meta and location_meta.get("content"):
            location_text = location_meta["content"].lower().strip()
            print(f"Found event:location meta → '{location_text}'")

            for loc_key, config in LOCATION_MAP.items():
                for keyword in config["keywords"]:
                    if keyword in location_text:
                        return loc_key

        # 2. Fallback: check the meta descriptions + visible text
        texts_to_search = []

        for meta in soup.find_all("meta", attrs={"name": "description"}):
            if meta.get("content"):
                texts_to_search.append(meta["content"])

        for meta in soup.find_all("meta", property="og:description"):
            if meta.get("content"):
                texts_to_search.append(meta["content"])

        texts_to_search.append(soup.get_text(" ", strip=True))

        page_text = " ".join(texts_to_search).lower()

        for loc_key, config in LOCATION_MAP.items():
            for keyword in config["keywords"]:
                if keyword in page_text:
                    return loc_key

        return None

    except Exception as e:
        print(f"Error fetching location: {e}")
        return None

def post_to_discord(config, title, summary, warhorn_url, facebook_link):
    if not config.get("webhook"):
        print(f"No webhook for {config['label']} – skipping")
        return False

    # Build the main Facebook post text
    post_text = ""
    if title:
        post_text += title.strip() + "\n\n"
    if summary:
        post_text += summary.strip()

    post_text = re.sub(r'\n{3,}', '\n\n', post_text).strip()

    # Reserve space for the Warhorn link and possible truncation notice
    warhorn_part = f"\n\nWarhorn: {warhorn_url}" if warhorn_url else ""
    max_content_length = 1900 - len(warhorn_part) - 30  # safety margin

    if len(post_text) > max_content_length:
        # Try to cut at the end of the last complete sentence
        truncated = post_text[:max_content_length]
        last_period = max(truncated.rfind(". "), truncated.rfind("! "), truncated.rfind("? "))
        
        if last_period > max_content_length * 0.6:  # only cut at sentence if it's not too early
            post_text = truncated[:last_period + 1].rstrip()
        else:
            post_text = truncated.rstrip()
        
        post_text += "\n\n[... truncated]"

    # Always include Warhorn link at the end
    post_text += warhorn_part

    # Final message is the role ping + content + link
    content = ""
    if config.get("role_id"):
        content += f"<@&{config['role_id']}>\n\n"
    content += post_text

    try:
        r = requests.post(config["webhook"], json={"content": content}, timeout=10)
        r.raise_for_status()
        print(f"✓ Posted to {config['label']}")
        return True
    except Exception as e:
        print(f"Failed to post ({config['label']}): {e}")
        return False

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

            success = post_to_discord(
            config=config,
            title=entry.get("title", ""),
            summary=entry.get("summary", ""),
            warhorn_url=warhorn_url,
            facebook_link=entry.get("link")
            )

            seen.add(warhorn_url)
            new_count += 1

    save_seen(seen)
    print(f"Finished. {new_count} new event(s) posted.")

if __name__ == "__main__":
    main()
