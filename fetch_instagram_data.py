import os
import time
import re
import sys
from http.cookiejar import MozillaCookieJar

import instaloader
import pandas as pd
import requests
from pymongo import MongoClient

# ── Configuration from environment variables ──
INSTAGRAM_USERNAME = os.getenv("INSTAGRAM_USERNAME", "bimazznxt.sub")
COOKIES_FILE = os.getenv("COOKIES_FILE", "cookies.txt")
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB", "bigdata")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "instagram_events")
CSV_OUTPUT = os.getenv("CSV_OUTPUT", "instagram_event_gereja.csv")

TARGET_PROFILES = [
    "gmssurabayabarat",
    "jpcc",
    "ndc_worship",
    "gkjslawi",
    "gbikamboja",
]

MAX_POSTS_PER_PROFILE = 10

# ── Login via password (more reliable than cookie injection for graphql) ──
INSTAGRAM_PASSWORD = os.getenv("INSTAGRAM_PASSWORD")

def login_instaloader():
    L = instaloader.Instaloader()
    if os.path.exists(COOKIES_FILE):
        cookie_jar = MozillaCookieJar(COOKIES_FILE)
        cookie_jar.load(ignore_discard=True, ignore_expires=True)
        for cookie in cookie_jar:
            L.context._session.cookies.set(cookie.name, cookie.value)
    if INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD:
        try:
            L.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
            print(f"Logged in as: {INSTAGRAM_USERNAME}")
            return L
        except Exception as e:
            print(f"Password login failed: {e}")
    if L.context.username:
        try:
            profile = instaloader.Profile.from_username(L.context, INSTAGRAM_USERNAME)
            print(f"Logged in as: {profile.username} (via cookies)")
            return L
        except Exception as e:
            print(f"Cookie session failed: {e}")
    print("No valid login found. Proceeding anonymously.")
    return L

def get_mongo_collection():
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    client.admin.command('ping')
    print("Connected to MongoDB Atlas")
    db = client[MONGO_DB]
    collection = db[MONGO_COLLECTION]
    collection.create_index("url", unique=True)
    return collection

def get_existing_urls(collection, owner):
    urls = set()
    for doc in collection.find({"owner": owner}, {"url": 1, "_id": 0}):
        urls.add(doc.get("url"))
    return urls

# ── Scraping with dedup against existing MongoDB data ──
def scrape_profiles(L, collection=None):
    data = []
    for username in TARGET_PROFILES:
        try:
            existing = get_existing_urls(collection, username) if collection is not None else set()
            print(f"Scraping @{username} ({len(existing)} existing posts in DB)")
            profile = instaloader.Profile.from_username(L.context, username)
            for i, post in enumerate(profile.get_posts()):
                if i >= MAX_POSTS_PER_PROFILE:
                    break
                post_url = f"https://instagram.com/p/{post.shortcode}/"
                if post_url in existing:
                    print(f"  -> Post {i + 1} already in DB, stopping @{username}")
                    break
                data.append({
                    "owner": post.owner_username,
                    "caption": post.caption,
                    "likes": post.likes,
                    "comments": post.comments,
                    "date": str(post.date_utc),
                    "url": post_url
                })
                print(f"  -> Post {i + 1}")
                time.sleep(10)
        except Exception as e:
            print(f"Error @{username}: {e}")
    return pd.DataFrame(data)

# ── Upload to MongoDB (dedup via unique index) ──
def upload_to_mongodb(df, collection):
    records = df.to_dict("records")
    if not records:
        print("No data to upload.")
        return
    try:
        collection.insert_many(records, ordered=False)
    except Exception:
        pass
    print(f"Upload complete. Total docs in collection: {collection.count_documents({})}")

def main():
    L = login_instaloader()
    collection = None
    if MONGO_URI:
        try:
            collection = get_mongo_collection()
        except Exception as e:
            print(f"MongoDB connection failed (proceeding without dedup): {e}")
    df = scrape_profiles(L, collection)
    if df.empty:
        print("No new data scraped. Exiting.")
        sys.exit(0)
    df.to_csv(CSV_OUTPUT, index=False)
    print(f"Saved {len(df)} rows to {CSV_OUTPUT}")
    if collection:
        upload_to_mongodb(df, collection)

if __name__ == "__main__":
    main()
