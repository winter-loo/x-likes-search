# Technical Architecture Document

## 1. System Overview

`x-likes-search` provides offline storage, instant multi-field search, and interactive like management for X (Twitter) bookmarks and likes without requiring active navigation to `x.com`.

The system consists of three primary layers:
1. **Extraction & Sync Engine (`ChromeCookieExtractor` & `XClient`):** Decrypts native browser credentials and synchronizes liked tweets through authenticated GraphQL cursors.
2. **Local Storage & Index Layer (`LikesDB`):** An embedded SQLite datastore optimized for instant multi-term keyword queries, filter predicates, and transactional mutations.
3. **Application & Interface Layer (`FastAPI` & Vanilla SPA):** A low-latency REST API paired with a reactive frontend emphasizing rapid visual feedback, micro-interactions, and optimistic state updates.

---

## 2. Component Design & Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│                       Host System                           │
│                                                             │
│  ┌─────────────────────────┐     ┌───────────────────────┐  │
│  │   Chrome Cookie Store   │     │  Linux Secret Service │  │
│  │ (~/.config/.../Cookies) │     │ (org.freedesktop.ss)  │  │
│  └────────────┬────────────┘     └───────────┬───────────┘  │
│               │ (v11 payload)                │ (password)   │
│               └──────────────┬───────────────┘              │
│                              ▼                              │
│               ┌─────────────────────────────┐               │
│               │ ChromeCookieExtractor (AES) │               │
│               └──────────────┬──────────────┘               │
│                              │ auth_token, ct0, twid        │
│                              ▼                              │
│               ┌─────────────────────────────┐               │
│               │   XClient (GraphQL Engine)  │               │
│               └──────────────┬──────────────┘               │
│                              │ TimelineAddEntries           │
│                              ▼                              │
│               ┌─────────────────────────────┐               │
│               │    LikesDB (SQLite Store)   │               │
│               └──────────────┬──────────────┘               │
│                              │ Sub-10ms Queries             │
│                              ▼                              │
│               ┌─────────────────────────────┐               │
│               │      FastAPI App Router     │               │
│               └──────────────┬──────────────┘               │
│                              │ JSON REST API                │
│                              ▼                              │
│               ┌─────────────────────────────┐               │
│               │    Modern Web Frontend      │               │
│               └─────────────────────────────┘               │
└─────────────────────────────────────────────────────────────┘
```

### 2.1 Credential & Session Extraction
Unlike traditional scrapers that require hardcoded secrets or headless browser automation, `ChromeCookieExtractor`:
1. Queries the desktop keyring via `secret-tool lookup application chrome`.
2. Derives a 128-bit key via `PBKDF2HMAC(SHA1, iterations=1, salt="saltysalt")`.
3. Safely copies the locked `Cookies` SQLite file to an ephemeral temporary file to prevent Chrome process locks.
4. Decrypts `v11` encrypted records using AES-CBC with an embedded 16-byte initialization vector.

### 2.2 Synchronisation Pipeline
`XClient` utilizes X's internal web client GraphQL endpoint:
- **Operation:** `Likes` (`queryId: XHn_Tw60c6pi0n3DGhpwiA`)
- **Pagination:** Bottom cursor tracking (`TimelineTimelineCursor`)
- **Incremental vs Full Sync:**
  - **Incremental Sync (Default):** Because X returns likes strictly ordered from newest to oldest, the engine compares each fetched batch against locally indexed IDs. As soon as it encounters tweets already present in SQLite, it terminates synchronization immediately. This cuts typical sync times from 20s to <1s and preserves API quotas.
  - **Full Sync:** Traverses all historical pages up to the requested depth.
- **Payload Normalization:** Extracts both standard tweets and `note_tweet` structures (handling long-form posts that exceed 280 characters), photo/video entities, and author metadata.

---

## 3. Storage & Indexing Design

### 3.1 Schema Definition

```sql
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
    is_liked INTEGER DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_likes_is_liked ON likes(is_liked);
CREATE INDEX IF NOT EXISTS idx_likes_created_at_ts ON likes(created_at_ts DESC);
CREATE INDEX IF NOT EXISTS idx_likes_author ON likes(author_screen_name);
```

### 3.2 Query Strategy
- Search queries are split into terms and executed with parameterized multi-column substring matching across `text`, `author_name`, `author_screen_name`, and tweet `id`.
- Benchmarks show sub-millisecond execution times (<1ms) for libraries under 50,000 tweets.
- Avoids external dependencies while ensuring exact substring search across diverse Unicode inputs (Chinese, Japanese, emojis, code snippets).

---

## 4. Concurrency & Optimistic State Management

### 4.1 Unlike Mutations
When a user clicks "Cancel Like":
1. **Immediate Local State Transition (0ms):** The UI applies the `.unliked` styling and provides instant undo toast feedback.
2. **Local Database Update (<2ms):** `LikesDB.set_like_status(tweet_id, 0)` is recorded.
3. **Asynchronous GraphQL Mutation:** The backend fires an `UnfavoriteTweet` GraphQL mutation (`queryId: ZYKSe-w7KEslx3JhSIk5LA`) to X's servers.
4. **Re-like Support:** If the user changes their mind, a corresponding `FavoriteTweet` mutation restores the like status.

### 4.2 Background Task Execution
Sync operations run asynchronously via FastAPI's `BackgroundTasks`, keeping the HTTP thread pool responsive to search queries during long-running pagination routines.
