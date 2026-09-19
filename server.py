#!/usr/bin/env python3
import os
import sys
import json
import time
import shutil
import sqlite3
import urllib.request
import urllib.parse
from pathlib import Path
from email.utils import parsedate_to_datetime
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, BackgroundTasks, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "x_likes.db"
STATIC_DIR = BASE_DIR / "static"
CHROME_COOKIES_PATH = Path.home() / ".config/google-chrome/Default/Cookies"
PROXY_URL = os.getenv("HTTP_PROXY", "http://localhost:6780")

# Public Web Client Bearer Token used by X Web
BEARER_TOKEN = (
    "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)
LIKES_QUERY_ID = "XHn_Tw60c6pi0n3DGhpwiA"
UNFAVORITE_QUERY_ID = "ZYKSe-w7KEslx3JhSIk5LA"
FAVORITE_QUERY_ID = "lI07N6Otwv1PhnEgXILM7A"


class ChromeCookieExtractor:
    @staticmethod
    def get_cookies() -> Dict[str, str]:
        if not CHROME_COOKIES_PATH.exists():
            return {}

        import subprocess
        password = b"peanuts"
        try:
            out = subprocess.check_output(
                ["secret-tool", "lookup", "application", "chrome"],
                text=True,
                stderr=subprocess.DEVNULL
            ).strip()
            if out:
                password = out.encode("utf-8")
        except Exception:
            pass

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA1(),
            length=16,
            salt=b"saltysalt",
            iterations=1,
            backend=default_backend()
        )
        key = kdf.derive(password)

        temp_db = f"/tmp/chrome_cookies_sync_{os.getpid()}.db"
        shutil.copyfile(CHROME_COOKIES_PATH, temp_db)
        try:
            conn = sqlite3.connect(temp_db)
            c = conn.cursor()
            c.execute("SELECT name, encrypted_value FROM cookies WHERE host_key LIKE '%x.com' OR host_key LIKE '%twitter.com'")
            cookies = {}
            for name, val in c.fetchall():
                if not val:
                    continue
                try:
                    if val[:3] == b"v11":
                        data = val[3:]
                        iv, ct = data[:16], data[16:]
                        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
                        dec = cipher.decryptor().update(ct) + cipher.decryptor().finalize()
                        pad = dec[-1]
                        cookies[name] = dec[:-pad][16:].decode("utf-8", errors="ignore")
                    elif val[:3] == b"v10":
                        data = val[3:]
                        cipher = Cipher(algorithms.AES(key), modes.CBC(b" " * 16), backend=default_backend())
                        dec = cipher.decryptor().update(data) + cipher.decryptor().finalize()
                        pad = dec[-1]
                        cookies[name] = dec[:-pad].decode("utf-8", errors="ignore")
                except Exception:
                    continue
            conn.close()
            return cookies
        finally:
            if os.path.exists(temp_db):
                os.remove(temp_db)


class LikesDB:
    @staticmethod
    def get_conn():
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        return conn

    @classmethod
    def init_db(cls):
        with cls.get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS likes (
                    id TEXT PRIMARY KEY,
                    author_name TEXT,
                    author_screen_name TEXT,
                    author_avatar TEXT,
                    text TEXT,
                    created_at TEXT,
                    created_at_ts INTEGER,
                    liked_at INTEGER,
                    favorite_count INTEGER DEFAULT 0,
                    retweet_count INTEGER DEFAULT 0,
                    reply_count INTEGER DEFAULT 0,
                    media_urls TEXT DEFAULT '[]',
                    urls TEXT DEFAULT '[]',
                    raw_json TEXT DEFAULT '{}',
                    is_liked INTEGER DEFAULT 1,
                    is_read INTEGER DEFAULT 0
                )
            """)
            try:
                conn.execute("ALTER TABLE likes ADD COLUMN is_read INTEGER DEFAULT 0")
            except Exception:
                pass
            conn.execute("CREATE INDEX IF NOT EXISTS idx_likes_is_liked ON likes(is_liked)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_likes_is_read ON likes(is_read)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_likes_created_at_ts ON likes(created_at_ts DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_likes_author ON likes(author_screen_name)")

    @classmethod
    def save_tweets(cls, tweets: List[Dict[str, Any]]) -> int:
        count = 0
        with cls.get_conn() as conn:
            for t in tweets:
                conn.execute("""
                    INSERT INTO likes (
                        id, author_name, author_screen_name, author_avatar, text,
                        created_at, created_at_ts, liked_at, favorite_count, retweet_count,
                        reply_count, media_urls, urls, raw_json, is_liked
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        author_name=excluded.author_name,
                        author_screen_name=excluded.author_screen_name,
                        author_avatar=excluded.author_avatar,
                        text=excluded.text,
                        favorite_count=excluded.favorite_count,
                        retweet_count=excluded.retweet_count,
                        reply_count=excluded.reply_count,
                        media_urls=excluded.media_urls,
                        urls=excluded.urls,
                        is_liked=excluded.is_liked
                """, (
                    t["id"], t["author_name"], t["author_screen_name"], t["author_avatar"],
                    t["text"], t["created_at"], t["created_at_ts"], int(time.time()),
                    t["favorite_count"], t["retweet_count"], t["reply_count"],
                    json.dumps(t["media_urls"]), json.dumps(t["urls"]), json.dumps(t.get("raw_json", {})),
                    t.get("is_liked", 1)
                ))
                count += 1
            conn.commit()
        return count

    @classmethod
    def set_like_status(cls, tweet_id: str, is_liked: int):
        with cls.get_conn() as conn:
            conn.execute("UPDATE likes SET is_liked = ? WHERE id = ?", (is_liked, tweet_id))
            conn.commit()

    @classmethod
    def set_read_status(cls, tweet_id: str, is_read: int):
        with cls.get_conn() as conn:
            conn.execute("UPDATE likes SET is_read = ? WHERE id = ?", (is_read, tweet_id))
            conn.commit()

    @classmethod
    def search(
        cls,
        q: Optional[str] = None,
        only_media: bool = False,
        include_unliked: bool = False,
        unread_only: bool = False,
        sort: str = "newest",
        limit: int = 50,
        offset: int = 0
    ) -> Dict[str, Any]:
        with cls.get_conn() as conn:
            conditions = []
            params = []

            if not include_unliked:
                conditions.append("is_liked = 1")

            if unread_only:
                conditions.append("is_read = 0")

            if only_media:
                conditions.append("media_urls != '[]' AND media_urls IS NOT NULL")

            if q and q.strip():
                terms = q.strip().split()
                sub_conds = []
                for term in terms:
                    wild = f"%{term}%"
                    sub_conds.append(
                        "(text LIKE ? OR author_name LIKE ? OR author_screen_name LIKE ? OR id = ?)"
                    )
                    params.extend([wild, wild, wild, term])
                conditions.append(f"({' AND '.join(sub_conds)})")

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            # Sort order
            if sort == "oldest":
                order_clause = "ORDER BY created_at_ts ASC"
            elif sort == "popular":
                order_clause = "ORDER BY favorite_count DESC, retweet_count DESC"
            else:
                order_clause = "ORDER BY created_at_ts DESC, rowid DESC"

            # Total count
            count_sql = f"SELECT COUNT(*) as cnt FROM likes {where_clause}"
            total = conn.execute(count_sql, params).fetchone()["cnt"]

            # Results
            query_sql = f"SELECT * FROM likes {where_clause} {order_clause} LIMIT ? OFFSET ?"
            query_params = params + [limit, offset]
            rows = conn.execute(query_sql, query_params).fetchall()

            items = []
            for r in rows:
                item = dict(r)
                item["media_urls"] = json.loads(item["media_urls"] or "[]")
                item["urls"] = json.loads(item["urls"] or "[]")
                item.pop("raw_json", None)
                items.append(item)

            return {"total": total, "items": items, "limit": limit, "offset": offset}

    @classmethod
    def get_stats(cls) -> Dict[str, Any]:
        with cls.get_conn() as conn:
            total = conn.execute("SELECT COUNT(*) as cnt FROM likes").fetchone()["cnt"]
            active = conn.execute("SELECT COUNT(*) as cnt FROM likes WHERE is_liked = 1").fetchone()["cnt"]
            unread = conn.execute("SELECT COUNT(*) as cnt FROM likes WHERE is_liked = 1 AND is_read = 0").fetchone()["cnt"]
            read_cnt = conn.execute("SELECT COUNT(*) as cnt FROM likes WHERE is_liked = 1 AND is_read = 1").fetchone()["cnt"]
            media_cnt = conn.execute("SELECT COUNT(*) as cnt FROM likes WHERE is_liked = 1 AND media_urls != '[]'").fetchone()["cnt"]
            unliked = total - active
            return {
                "total": total,
                "active_likes": active,
                "unread": unread,
                "read": read_cnt,
                "unliked": unliked,
                "with_media": media_cnt
            }


class XClient:
    def __init__(self):
        self.cookies = ChromeCookieExtractor.get_cookies()
        self.auth_token = self.cookies.get("auth_token", "")
        self.ct0 = self.cookies.get("ct0", "")
        twid = self.cookies.get("twid", "")
        # twid cookie format: u%3D<user_id> or u=<user_id>
        unquoted_twid = urllib.parse.unquote(twid)
        self.user_id = unquoted_twid.split("=")[1] if "=" in unquoted_twid else ""

    def _get_opener(self):
        # Prefer configured proxy if available
        if PROXY_URL:
            proxy_handler = urllib.request.ProxyHandler({"http": PROXY_URL, "https": PROXY_URL})
            return urllib.request.build_opener(proxy_handler)
        return urllib.request.build_opener()

    def _headers(self, post_json: bool = False) -> Dict[str, str]:
        h = {
            "authorization": BEARER_TOKEN,
            "x-csrf-token": self.ct0,
            "x-twitter-active-user": "yes",
            "x-twitter-auth-type": "OAuth2Session",
            "x-twitter-client-language": "en",
            "cookie": f"auth_token={self.auth_token}; ct0={self.ct0}",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "referer": "https://x.com/"
        }
        if post_json:
            h["content-type"] = "application/json"
        return h

    def fetch_likes_page(self, cursor: Optional[str] = None, count: int = 40) -> Dict[str, Any]:
        variables = {
            "userId": self.user_id,
            "count": count,
            "includePromotedContent": False,
            "withClientEventToken": False,
            "withBirdwatchNotes": False,
            "withVoice": True,
            "withV2Timeline": True
        }
        if cursor:
            variables["cursor"] = cursor

        features = {
            "rweb_tipjar_consumption_enabled": True,
            "responsive_web_graphql_exclude_directive_enabled": True,
            "verified_phone_label_enabled": False,
            "creator_subscriptions_tweet_preview_api_enabled": True,
            "responsive_web_graphql_timeline_navigation_enabled": True,
            "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
            "communities_web_enable_tweet_community_results_fetch": True,
            "c9s_tweet_anatomy_moderator_badge_enabled": True,
            "articles_preview_enabled": True,
            "responsive_web_edit_tweet_api_enabled": True,
            "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
            "view_counts_everywhere_api_enabled": True,
            "longform_notetweets_consumption_enabled": True,
            "responsive_web_twitter_article_tweet_consumption_enabled": True,
            "tweet_awards_web_tipping_enabled": False,
            "creator_subscriptions_quote_tweet_preview_api_enabled": False,
            "freedom_of_speech_not_reached_appeal_enabled": True,
            "standardized_nudges_misinfo": True,
            "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
            "rweb_video_timestamps_enabled": True,
            "longform_notetweets_rich_text_read_enabled": True,
            "longform_notetweets_inline_media_enabled": True,
            "responsive_web_enhance_cards_enabled": False
        }

        params = {"variables": json.dumps(variables), "features": json.dumps(features)}
        url = f"https://x.com/i/api/graphql/{LIKES_QUERY_ID}/Likes?{urllib.parse.urlencode(params)}"

        req = urllib.request.Request(url, headers=self._headers())
        opener = self._get_opener()
        with opener.open(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        instructions = (
            data.get("data", {})
            .get("user", {})
            .get("result", {})
            .get("timeline", {})
            .get("timeline", {})
            .get("instructions", [])
        )
        if not instructions:
            instructions = (
                data.get("data", {})
                .get("user", {})
                .get("result", {})
                .get("timeline_v2", {})
                .get("timeline", {})
                .get("instructions", [])
            )

        tweets = []
        next_cursor = None

        for inst in instructions:
            if inst.get("type") == "TimelineAddEntries":
                for entry in inst.get("entries", []):
                    content = entry.get("content", {})
                    entry_type = content.get("entryType") or content.get("__typename")

                    if "itemContent" in content:
                        t = content["itemContent"].get("tweet_results", {}).get("result", {})
                        if t.get("__typename") == "TweetWithVisibilityResults":
                            t = t.get("tweet", {})
                        if not t or "rest_id" not in t:
                            continue

                        tweet_id = t.get("rest_id")
                        user = t.get("core", {}).get("user_results", {}).get("result", {})
                        author_name = user.get("core", {}).get("name") or user.get("legacy", {}).get("name") or ""
                        author_screen_name = user.get("core", {}).get("screen_name") or user.get("legacy", {}).get("screen_name") or ""
                        author_avatar = user.get("avatar", {}).get("image_url") or user.get("legacy", {}).get("profile_image_url_https") or ""

                        legacy = t.get("legacy", {})
                        text = (
                            t.get("note_tweet", {}).get("note_tweet_results", {}).get("result", {}).get("text")
                            or legacy.get("full_text", "")
                        )
                        created_at = legacy.get("created_at", "")
                        created_at_ts = 0
                        if created_at:
                            try:
                                created_at_ts = int(parsedate_to_datetime(created_at).timestamp())
                            except Exception:
                                pass

                        fav_cnt = legacy.get("favorite_count", 0)
                        rt_cnt = legacy.get("retweet_count", 0)
                        reply_cnt = legacy.get("reply_count", 0)

                        media_list = []
                        for m in legacy.get("entities", {}).get("media", []):
                            if "media_url_https" in m:
                                media_list.append(m["media_url_https"])
                        for m in legacy.get("extended_entities", {}).get("media", []):
                            if "media_url_https" in m and m["media_url_https"] not in media_list:
                                media_list.append(m["media_url_https"])

                        url_list = []
                        for u in legacy.get("entities", {}).get("urls", []):
                            if "expanded_url" in u:
                                url_list.append(u["expanded_url"])

                        tweets.append({
                            "id": tweet_id,
                            "author_name": author_name,
                            "author_screen_name": author_screen_name,
                            "author_avatar": author_avatar,
                            "text": text,
                            "created_at": created_at,
                            "created_at_ts": created_at_ts,
                            "favorite_count": fav_cnt,
                            "retweet_count": rt_cnt,
                            "reply_count": reply_cnt,
                            "media_urls": media_list,
                            "urls": url_list,
                            "raw_json": t,
                            "is_liked": 1
                        })
                    elif entry_type == "TimelineTimelineCursor":
                        if content.get("cursorType") == "Bottom":
                            next_cursor = content.get("value")

        return {"tweets": tweets, "next_cursor": next_cursor}

    def unlike_tweet(self, tweet_id: str) -> bool:
        url = f"https://x.com/i/api/graphql/{UNFAVORITE_QUERY_ID}/UnfavoriteTweet"
        payload = json.dumps({
            "variables": {"tweet_id": tweet_id},
            "queryId": UNFAVORITE_QUERY_ID
        }).encode("utf-8")

        req = urllib.request.Request(url, data=payload, headers=self._headers(post_json=True), method="POST")
        opener = self._get_opener()
        try:
            with opener.open(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return "data" in data or "errors" not in data
        except Exception as e:
            print(f"Error unliking tweet {tweet_id}: {e}", file=sys.stderr)
            return False

    def relike_tweet(self, tweet_id: str) -> bool:
        url = f"https://x.com/i/api/graphql/{FAVORITE_QUERY_ID}/FavoriteTweet"
        payload = json.dumps({
            "variables": {"tweet_id": tweet_id},
            "queryId": FAVORITE_QUERY_ID
        }).encode("utf-8")

        req = urllib.request.Request(url, data=payload, headers=self._headers(post_json=True), method="POST")
        opener = self._get_opener()
        try:
            with opener.open(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return "data" in data or "errors" not in data
        except Exception as e:
            print(f"Error reliking tweet {tweet_id}: {e}", file=sys.stderr)
            return False


# Global sync status tracker
class SyncManager:
    is_syncing = False
    total_synced = 0
    current_page = 0
    last_sync_time = None
    error_msg = None


sync_mgr = SyncManager()


def background_sync_task(max_pages: int = 15):
    if sync_mgr.is_syncing:
        return
    sync_mgr.is_syncing = True
    sync_mgr.error_msg = None
    client = XClient()
    cursor = None
    page = 0
    total_new = 0

    try:
        while page < max_pages:
            page += 1
            sync_mgr.current_page = page
            res = client.fetch_likes_page(cursor=cursor, count=40)
            tweets = res["tweets"]
            if not tweets:
                break

            saved = LikesDB.save_tweets(tweets)
            total_new += saved
            sync_mgr.total_synced = total_new

            cursor = res.get("next_cursor")
            if not cursor:
                break
            time.sleep(1.0)  # Gentle rate limiting
    except Exception as e:
        sync_mgr.error_msg = str(e)
        print(f"Sync error: {e}", file=sys.stderr)
    finally:
        sync_mgr.is_syncing = False
        sync_mgr.last_sync_time = int(time.time())


app = FastAPI(title="X Likes Vault")
LikesDB.init_db()

# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
def index():
    html_file = STATIC_DIR / "index.html"
    if html_file.exists():
        return html_file.read_text(encoding="utf-8")
    return "<h1>X Likes Vault</h1><p>index.html missing</p>"


@app.get("/api/status")
def get_status():
    stats = LikesDB.get_stats()
    client = XClient()
    has_auth = bool(client.auth_token and client.ct0)
    return {
        "connected": has_auth,
        "user_id": client.user_id,
        "is_syncing": sync_mgr.is_syncing,
        "current_page": sync_mgr.current_page,
        "total_synced_session": sync_mgr.total_synced,
        "last_sync": sync_mgr.last_sync_time,
        "sync_error": sync_mgr.error_msg,
        "stats": stats
    }


@app.get("/api/search")
def search_likes(
    q: Optional[str] = Query(None),
    only_media: bool = Query(False),
    include_unliked: bool = Query(False),
    unread_only: bool = Query(False),
    sort: str = Query("newest"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    t0 = time.time()
    results = LikesDB.search(
        q=q,
        only_media=only_media,
        include_unliked=include_unliked,
        unread_only=unread_only,
        sort=sort,
        limit=limit,
        offset=offset
    )
    took_ms = round((time.time() - t0) * 1000, 2)
    results["took_ms"] = took_ms
    return results


class SyncRequest(BaseModel):
    pages: int = 10


@app.post("/api/sync")
def trigger_sync(req: SyncRequest, bg_tasks: BackgroundTasks):
    if sync_mgr.is_syncing:
        return {"status": "already_syncing", "current_page": sync_mgr.current_page}
    bg_tasks.add_task(background_sync_task, req.pages)
    return {"status": "started", "pages_requested": req.pages}


class TweetActionRequest(BaseModel):
    tweet_id: str


class ReadActionRequest(BaseModel):
    tweet_id: str
    is_read: int = 1


@app.post("/api/read")
def toggle_read(req: ReadActionRequest):
    LikesDB.set_read_status(req.tweet_id, req.is_read)
    return {"success": True, "tweet_id": req.tweet_id, "is_read": req.is_read}


@app.post("/api/unlike")
def unlike_tweet(req: TweetActionRequest):
    client = XClient()
    # 1. Update DB immediately for optimistic consistency
    LikesDB.set_like_status(req.tweet_id, 0)
    # 2. Fire mutation to X API
    ok = client.unlike_tweet(req.tweet_id)
    return {"success": True, "tweet_id": req.tweet_id, "x_api_acknowledged": ok}


@app.post("/api/relike")
def relike_tweet(req: TweetActionRequest):
    client = XClient()
    LikesDB.set_like_status(req.tweet_id, 1)
    ok = client.relike_tweet(req.tweet_id)
    return {"success": True, "tweet_id": req.tweet_id, "x_api_acknowledged": ok}


if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8999))
    print(f"Starting X Likes Search Server on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")
