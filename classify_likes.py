#!/usr/bin/env python3
"""
CLI tool to classify and tag all unlabeled X likes using TypeSafe System One.
Usage:
  python3 classify_likes.py [--limit N] [--batch-size B] [--interval S]
"""
import sys
import time
import argparse
import sqlite3
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from server import LikesDB
from classifier import TypeSafeClassifier

def main():
    parser = argparse.ArgumentParser(description="Classify unlabeled likes via TypeSafe System One")
    parser.add_argument("--limit", type=int, default=0, help="Maximum tweets to classify (0 = all unlabeled)")
    parser.add_argument("--batch-size", type=int, default=10, help="Batch size per run (default: 10)")
    parser.add_argument("--interval", type=float, default=0.2, help="Sleep interval in seconds between batches")
    args = parser.parse_args()

    LikesDB.init_db()
    clf = TypeSafeClassifier()

    with LikesDB.get_conn() as conn:
        total_unlabeled = conn.execute("""
            SELECT count(*) FROM likes
            WHERE (tags IS NULL OR tags = '[]' OR tags = '')
        """).fetchone()[0]

    print(f"[*] Found {total_unlabeled} unlabeled likes in database.")
    if total_unlabeled == 0:
        print("[✓] All likes are already tagged!")
        return

    to_process = total_unlabeled if args.limit <= 0 else min(total_unlabeled, args.limit)
    print(f"[*] Processing {to_process} tweets (batch_size={args.batch_size})...")

    processed = 0
    start_time = time.time()

    while processed < to_process:
        batch_limit = min(args.batch_size, to_process - processed)
        with LikesDB.get_conn() as conn:
            rows = conn.execute("""
                SELECT id, author_name, author_screen_name, text FROM likes
                WHERE (tags IS NULL OR tags = '[]' OR tags = '')
                ORDER BY sort_index DESC
                LIMIT ?
            """, (batch_limit,)).fetchall()

        if not rows:
            break

        for r in rows:
            tid = r["id"]
            text = r["text"] or ""
            author = f"@{r['author_screen_name']}" if r["author_screen_name"] else r["author_name"]
            matched = LikesDB.classify_and_apply_tags(tid, text, classifier=clf)
            tag_names = [m[0] for m in matched]
            snippet = text[:45].replace("\n", " ")
            print(f" [{processed+1}/{to_process}] {author}: {snippet}... -> {tag_names}")
            processed += 1

        if args.interval > 0:
            time.sleep(args.interval)

    duration = round(time.time() - start_time, 2)
    print(f"\n[✓] Finished tagging {processed} tweets in {duration}s.")
    
    # Print summary
    tags = LikesDB.get_tags()
    print("\n--- Tag Cloud Distribution ---")
    for t in tags:
        if t["count"] > 0:
            print(f"  #{t['name']}: {t['count']} tweets")

if __name__ == "__main__":
    main()
