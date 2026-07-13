import os
import re
import datetime
import time
import random
import pandas as pd
from pymongo import MongoClient

# MongoDB Default Configuration (overridable via env vars)
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://bimazznxt:bimazznxt@bigdata.t30qupi.mongodb.net/?appName=bigData")
DB_NAME = os.getenv("MONGO_DB", "bigdata")
COLLECTION_NAME = os.getenv("MONGO_COLLECTION", "instagram_events")
CSV_OUTPUT = os.getenv("CSV_OUTPUT", "youtube_events.csv")

# Target accounts provided by the user
DEFAULT_TARGETS = [
    "https://www.youtube.com/",
    "https://www.youtube.com/@GMSChurch",
    "https://www.youtube.com/@GSJSChurch",
    "https://www.youtube.com/@kerinduankuchurch.kelapagading",
    "https://www.youtube.com/@PDHOPE"
]

# API Target Map in case API method is used
API_TARGET_MAP = {
    "GMSChurch": "UCx0f90k2q_wK8sQ1hC2uT2Q",
    "GSJSChurch": "UCzYFmYyR7K-Gz3h02Uo6X-Q",
    "kerinduankuchurch.kelapagading": "UC3bZ69uOQWl7E4K8b-8vLkg",
    "PDHOPE": "UCY8k_2N1qQ5tW_P-2ZJb76A"
}

def format_date(timestamp=None, date_str=None):
    """
    Utility to format dates into 'YYYY-MM-DD HH:MM:SS' string format.
    """
    if timestamp:
        try:
            return datetime.datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            pass
    if date_str:
        try:
            # Parse '20260313' or ISO strings
            if len(date_str) == 8 and date_str.isdigit():
                return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]} 00:00:00"
            parsed_date = pd.to_datetime(date_str)
            return parsed_date.strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            pass
    return datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

def scrape_youtube_ytdlp(channel_url, post_limit=10):
    """
    Scrapes video metadata from a YouTube channel using yt-dlp (No API key required).
    """
    try:
        import yt_dlp
    except ImportError:
        print("[!] yt-dlp is not installed. Run: pip install yt-dlp")
        return []

    print(f"\n[~] Memulai scraping channel (yt-dlp): {channel_url}")
    scraped_data = []

    # Configure yt-dlp options
    ydl_opts = {
        'quiet': True,
        'extract_flat': False,      # Extract full metadata (likes, comments, etc.)
        'playlistend': post_limit,  # Limit playlist/channel evaluation early
        'skip_download': True,      # Do not download video files
        'ignoreerrors': True,
        'no_warnings': True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(channel_url, download=False)
            if not info:
                print("[!] Gagal mengekstrak info dari channel.")
                return []
            
            entries = info.get('entries', [])
            if not isinstance(entries, list):
                entries = [info]
            
            count = 0
            for entry in entries:
                if not entry:
                    continue
                if count >= post_limit:
                    break
                
                try:
                    video_id = entry.get('id')
                    video_url = f"https://www.youtube.com/watch?v={video_id}" if video_id else entry.get('webpage_url')
                    
                    title = entry.get('title', '')
                    description = entry.get('description', '')
                    caption = f"{title}\n\n{description}".strip()
                    
                    record = {
                        "owner": entry.get('uploader') or entry.get('channel') or "Unknown Channel",
                        "caption": caption,
                        "likes": int(entry.get('like_count') or 0),
                        "comments": int(entry.get('comment_count') or 0),
                        "date": format_date(timestamp=entry.get('timestamp'), date_str=entry.get('upload_date')),
                        "url": video_url
                    }
                    
                    scraped_data.append(record)
                    count += 1
                    print(f"    [+] Berhasil mengambil ({count}/{post_limit}): {title[:40]}...")
                    
                    # Dynamic delay to avoid rate limiting
                    time.sleep(random.uniform(5, 12))
                    
                except Exception as e:
                    print(f"    [!] Gagal memproses video entry: {e}")
                    continue
                    
        except Exception as e:
            print(f"[!] Error saat scraping dengan yt-dlp: {e}")
            
    return scraped_data


def scrape_youtube_api(channel_id, api_key, post_limit=10):
    """
    Scrapes video metadata from a YouTube channel using the official YouTube Data API v3.
    """
    import requests
    print(f"\n[~] Memulai scraping channel (YouTube API): {channel_id}")
    scraped_data = []
    
    # Step 1: Get the 'uploads' playlist ID for the channel
    channel_url = f"https://www.googleapis.com/youtube/v3/channels?part=contentDetails&id={channel_id}&key={api_key}"
    try:
        r = requests.get(channel_url)
        r.raise_for_status()
        res = r.json()
        if not res.get("items"):
            # Try by username if channel_id starts with a handle or name instead of UC
            channel_url_by_user = f"https://www.googleapis.com/youtube/v3/channels?part=contentDetails&forUsername={channel_id}&key={api_key}"
            r = requests.get(channel_url_by_user)
            res = r.json()
            if not res.get("items"):
                print("[!] Channel tidak ditemukan. Periksa kembali Channel ID atau Nama.")
                return []
                
        channel_item = res["items"][0]
        channel_name = channel_id
        
        # We need the channel title, let's fetch snippet part to get the owner name
        snippet_url = f"https://www.googleapis.com/youtube/v3/channels?part=snippet&id={channel_item['id']}&key={api_key}"
        snip_res = requests.get(snippet_url).json()
        if snip_res.get("items"):
            channel_name = snip_res["items"][0]["snippet"]["title"]

        uploads_playlist_id = channel_item["contentDetails"]["relatedPlaylists"]["uploads"]
    except Exception as e:
        print(f"[!] Gagal mengambil info channel dari API: {e}")
        return []
        
    # Step 2: Get the video list in uploads playlist
    playlist_url = f"https://www.googleapis.com/youtube/v3/playlistItems?part=snippet&playlistId={uploads_playlist_id}&maxResults={post_limit}&key={api_key}"
    try:
        r = requests.get(playlist_url)
        r.raise_for_status()
        items = r.json().get("items", [])
    except Exception as e:
        print(f"[!] Gagal mengambil video dari playlist uploads: {e}")
        return []
        
    video_ids = []
    video_details_map = {}
    
    for item in items:
        snippet = item.get("snippet", {})
        vid_id = snippet.get("resourceId", {}).get("videoId")
        if vid_id:
            video_ids.append(vid_id)
            title = snippet.get("title", "")
            desc = snippet.get("description", "")
            pub_date = snippet.get("publishedAt", "")
            
            video_details_map[vid_id] = {
                "owner": channel_name,
                "caption": f"{title}\n\n{desc}".strip(),
                "date": format_date(date_str=pub_date),
                "url": f"https://www.youtube.com/watch?v={vid_id}"
            }
            
    if not video_ids:
        print("[!] Tidak ada video ditemukan di playlist.")
        return []
        
    # Step 3: Get likes and comments statistics for these videos
    stats_url = f"https://www.googleapis.com/youtube/v3/videos?part=statistics&id={','.join(video_ids)}&key={api_key}"
    try:
        r = requests.get(stats_url)
        r.raise_for_status()
        stats_items = r.json().get("items", [])
        
        for s_item in stats_items:
            vid_id = s_item.get("id")
            stats = s_item.get("statistics", {})
            
            likes = int(stats.get("likeCount") or 0)
            comments = int(stats.get("commentCount") or 0)
            
            if vid_id in video_details_map:
                record = video_details_map[vid_id]
                record["likes"] = likes
                record["comments"] = comments
                scraped_data.append(record)
                print(f"    [+] Berhasil mengambil (API): {record['caption'][:40]}...")
                
    except Exception as e:
        print(f"[!] Gagal mengambil statistik detail video: {e}")
        
    return scraped_data


def save_to_mongodb(records, uri=MONGO_URI, db_name=DB_NAME, coll_name=COLLECTION_NAME):
    """
    Saves a list of dictionaries to MongoDB.
    """
    if not records:
        print("[WARNING] Tidak ada data untuk disimpan ke MongoDB.")
        return False
        
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        # Test connection
        client.admin.command('ping')
        print("[OK] Berhasil terhubung ke MongoDB Atlas")
        
        db = client[db_name]
        collection = db[coll_name]
        
        result = collection.insert_many(records)
        print(f"[OK] Berhasil menyimpan {len(result.inserted_ids)} dokumen ke MongoDB collection '{coll_name}'.")
        return True
    except Exception as e:
        print(f"[ERROR] Gagal menyimpan ke MongoDB: {e}")
        print("\nTips: Periksa apakah password MongoDB Anda sudah benar dan IP address Anda sudah di-whitelist di MongoDB Atlas.")
        return False


def run_full_scraping_loop(method="ytdlp", post_limit=5, api_key=None, uri=MONGO_URI, db=DB_NAME, collection=COLLECTION_NAME, csv_output=CSV_OUTPUT):
    """
    Loops through the target accounts and processes scraping and storing.
    """
    all_records = []
    
    if method == "api":
        if not api_key:
            print("[ERROR] API Key wajib diisi jika menggunakan metode 'api'.")
            return
        
        print(f"[~] Memulai loop scraping untuk channel (YouTube API)")
        for handle, channel_id in API_TARGET_MAP.items():
            try:
                records = scrape_youtube_api(channel_id, api_key, post_limit)
                if records:
                    all_records.extend(records)
                time.sleep(2)  # Delay between channels
            except Exception as e:
                print(f"[ERROR] Gagal scraping channel {handle} dengan API: {e}")
    else:
        print(f"[~] Memulai loop scraping untuk channel (yt-dlp)")
        for url in DEFAULT_TARGETS:
            # Skip base YouTube URL if provided by user
            cleaned_url = url.strip().rstrip("/")
            if cleaned_url in ["https://www.youtube.com", "https://youtube.com", "http://www.youtube.com", "http://youtube.com"]:
                print(f"[~] Skipping homepage YouTube URL: {url}")
                continue
                
            # Formatting to target the videos tab directly
            channel_url = url
            if not url.endswith("/videos"):
                channel_url = url.rstrip("/") + "/videos"
                
            try:
                records = scrape_youtube_ytdlp(channel_url, post_limit)
                if records:
                    all_records.extend(records)
                
                # Sleep between channels to be respectful to rate limits
                wait_time = random.uniform(8, 15)
                print(f"[~] Istirahat {wait_time:.1f} detik sebelum ke channel berikutnya...")
                time.sleep(wait_time)
            except Exception as e:
                print(f"[ERROR] Gagal scraping channel {url} dengan yt-dlp: {e}")
                
    if all_records:
        df = pd.DataFrame(all_records)
        print(f"\n[OK] Scraping selesai. Total data diperoleh: {len(df)}")
        print("\nPratinjau Data:")
        print(df.head())
        
        # Save to CSV
        df.to_csv(csv_output, index=False)
        print(f"[OK] Data disimpan ke {csv_output}")
        
        # Save to MongoDB
        save_to_mongodb(all_records, uri=uri, db_name=db, coll_name=collection)
    else:
        print("\n[ERROR] Tidak ada data yang berhasil di-scrape.")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="YouTube Scraping & MongoDB Storage Tool (Custom Targets)")
    parser.add_argument("--method", choices=["ytdlp", "api"], default="ytdlp", 
                        help="Metode scraping: 'ytdlp' (tanpa API key) atau 'api' (menggunakan YouTube Data API v3)")
    parser.add_argument("--limit", type=int, default=5, help="Jumlah video maksimal per channel (default: 5)")
    parser.add_argument("--key", help="API Key YouTube (wajib jika menggunakan metode 'api')")
    parser.add_argument("--db", default=DB_NAME, help="Nama database MongoDB")
    parser.add_argument("--collection", default=COLLECTION_NAME, help="Nama koleksi MongoDB")
    parser.add_argument("--csv", default=CSV_OUTPUT, help="Path output CSV")
    
    args = parser.parse_args()
    
    run_full_scraping_loop(
        method=args.method,
        post_limit=args.limit,
        api_key=args.key,
        uri=MONGO_URI,
        db=args.db,
        collection=args.collection,
        csv_output=args.csv
    )
