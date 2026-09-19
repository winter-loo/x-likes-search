#!/usr/bin/env python3
import sys
from pathlib import Path

# Add project dir to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from server import ChromeCookieExtractor, LikesDB, XClient, app
from fastapi.testclient import TestClient

def test_pipeline():
    # 1. Test Cookie Extraction
    cookies = ChromeCookieExtractor.get_cookies()
    assert "auth_token" in cookies, "auth_token missing from cookies"
    assert "ct0" in cookies, "ct0 missing from cookies"
    print("✓ Cookie extraction passed")

    # 2. Test DB Initialization and Insertion
    LikesDB.init_db()
    sample_tweet = {
        "id": "test_tweet_999",
        "author_name": "Test Engineer",
        "author_screen_name": "test_eng",
        "author_avatar": "https://example.com/avatar.jpg",
        "text": "Testing SQLite instant search with keywords like Rust, SQLite, and Web development!",
        "created_at": "Sat Sep 19 12:00:00 +0000 2026",
        "created_at_ts": 1789819200,
        "favorite_count": 42,
        "retweet_count": 10,
        "reply_count": 3,
        "media_urls": ["https://example.com/image.png"],
        "urls": ["https://example.com"],
        "is_liked": 1
    }
    saved = LikesDB.save_tweets([sample_tweet])
    assert saved["total"] == 1, "Failed to save sample tweet"
    print("✓ DB insert passed")

    # 3. Test Search
    res = LikesDB.search(q="Rust SQLite")
    assert res["total"] >= 1, "Failed to find inserted tweet by search query"
    assert res["items"][0]["id"] == "test_tweet_999"
    print("✓ Search passed")

    # 4. Test Unlike Toggle
    LikesDB.set_like_status("test_tweet_999", 0)
    res_after = LikesDB.search(q="Rust SQLite", include_unliked=False)
    assert not any(i["id"] == "test_tweet_999" for i in res_after["items"]), "Unliked tweet should be hidden when include_unliked=False"
    
    res_unliked = LikesDB.search(q="Rust SQLite", include_unliked=True)
    assert any(i["id"] == "test_tweet_999" for i in res_unliked["items"]), "Unliked tweet should be found when include_unliked=True"
    print("✓ Unlike toggle passed")

    # 5. Test Read Status Toggle & Unread Filter
    LikesDB.set_like_status("test_tweet_999", 1)
    LikesDB.set_read_status("test_tweet_999", 1)
    res_unread = LikesDB.search(q="Rust SQLite", unread_only=True)
    assert not any(i["id"] == "test_tweet_999" for i in res_unread["items"]), "Read tweet should be hidden when unread_only=True"

    LikesDB.set_read_status("test_tweet_999", 0)
    res_unread_restored = LikesDB.search(q="Rust SQLite", unread_only=True)
    assert any(i["id"] == "test_tweet_999" for i in res_unread_restored["items"]), "Unread tweet should appear when unread_only=True"
    print("✓ Read/Unread toggle & filter passed")

    # 6. Test FastApi TestClient
    client = TestClient(app)
    resp = client.get("/api/status")
    assert resp.status_code == 200
    assert resp.json()["connected"] is True
    print("✓ API /api/status passed")

    resp = client.post("/api/read", json={"tweet_id": "test_tweet_999", "is_read": 1})
    assert resp.status_code == 200
    assert resp.json()["is_read"] == 1
    print("✓ API /api/read passed")

    resp = client.get("/api/search?q=Rust")
    assert resp.status_code == 200
    assert "items" in resp.json()
    print("✓ API /api/search passed")

    # Cleanup test record
    with LikesDB.get_conn() as conn:
        conn.execute("DELETE FROM likes WHERE id = 'test_tweet_999'")
        conn.commit()

    print("\nALL SELF-CHECKS PASSED!")

if __name__ == "__main__":
    test_pipeline()
