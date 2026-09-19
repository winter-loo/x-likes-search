# 𝕏 Likes Vault (x-likes-search)

> **Delicate, sub-10ms instant search and offline local archive for your X (Twitter) likes.**  
> Powered by local Chrome session extraction, SQLite, FastAPI, and a reactive dark-mode UI.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg)](https://fastapi.tiangolo.com)
[![SQLite](https://img.shields.io/badge/SQLite-3-003B57.svg)](https://www.sqlite.org/)

---

## 🌟 Highlights

- **⚡ Instant Search (<10ms)**: Query thousands of liked tweets instantaneously without navigating `x.com` or waiting on network latency.
- **🍪 Zero-Config Chrome Session Extraction**: Automatically decrypts your active X session (`auth_token`, `ct0`, `twid`) directly from your local Chrome profile via the Linux Secret Service / DPAPI keyrings. No manual token copy-pasting required.
- **💔 Cancel Likes & Re-like**: Cancel likes with a single click. Uses optimistic UI updates while dispatching authenticated GraphQL mutations to X's backend.
- **🖼️ Rich Media & Article Display**: Renders image grids, long-form Note Tweets, external link previews, and full metadata (retweets, replies, favorites).
- **🔗 Direct Original Navigation**: Seamlessly jumps to the original post on `x.com` whenever you want to reply or view live threads.
- **🎨 Delicate UI Crafted for Speed**:
  - Hotkey `/` for instant focus, `Esc` to clear.
  - Micro-interactions on every click, hover, and state transition.
  - Lightbox for high-resolution image preview.
  - Filter chips: All, With Media, Cancelled / Unliked, Newest First, Most Liked.
- **🔒 100% Private & Local**: Zero cloud telemetry, zero remote database connections. All data resides in your local `x_likes.db`.

---

## 🏗️ Architecture at a Glance

```
┌───────────────────────────┐      Direct DB Read & Decrypt
│   Local Chrome Profile    │ ───────────────────────────────────┐
│ (~/.config/google-chrome) │ (Linux Secret Service PBKDF2/AES)  │
└───────────────────────────┘                                    ▼
                                                       ┌──────────────────┐
                                                       │   XClient Sync   │
                                                       └─────────┬────────┘
                                                                 │ X Web GraphQL API
                                                                 ▼
┌───────────────────────────┐      Sub-10ms Query      ┌──────────────────┐
│   Web UI (Vanilla JS)     │ ◄──────────────────────► │ SQLite Vault DB  │
│  Reactive / Instant Feed  │     FastAPI Endpoints    │   (x_likes.db)   │
└───────────────────────────┘                          └──────────────────┘
```

See [Technical Architecture](docs/architecture.md) and [Cookie Extraction & Web GraphQL](docs/cookie-extraction-and-api.md) for deep-dive documentation.

---

## 🚀 Quick Start

### 1. Requirements

- Linux / macOS (tested on Linux with Chrome and Secret Service keyring)
- Python 3.10+
- Chrome browser with an active `x.com` login

### 2. Installation

Clone the repository and install the dependencies:

```bash
git clone https://github.com/winter-loo/x-likes-search.git
cd x-likes-search

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install requirements
pip install -r requirements.txt
```

### 3. Run the Server

```bash
python server.py
```

By default, the server binds to `0.0.0.0:8999`.

Open your browser at:
- **Local machine:** [http://127.0.0.1:8999](http://127.0.0.1:8999)
- **Local Network:** `http://<your-local-ip>:8999` (e.g. `http://192.168.10.104:8999`)

### 4. Configuration via Environment Variables (Optional)

| Variable | Default | Description |
|---|---|---|
| `HOST` | `0.0.0.0` | Server host address |
| `PORT` | `8999` | Server listening port |
| `HTTP_PROXY` | `http://localhost:6780` | Upstream proxy for X API requests |

---

## 📖 Key Documentation

- [Technical Architecture](docs/architecture.md): Database indexing, data pipeline, concurrency, and UI responsiveness.
- [Cookie Extraction & Web GraphQL Protocol](docs/cookie-extraction-and-api.md): How Chrome `v11` encryption is decrypted locally, GraphQL query IDs, feature switches, and mutation payload structures.

---

## 🧪 Testing

Run the included end-to-end test suite:

```bash
python test_service.py
```

Validates:
1. Local Chrome cookie extraction and AES decryption.
2. SQLite schema creation and conflict handling.
3. Fast search matching and ranking.
4. Like/unlike toggle persistence.
5. FastAPI endpoints (`/api/status`, `/api/search`).

---

## 🛡️ Privacy & Security

- **No Remote Credentials Transmitted:** Your session cookies never leave your machine and are decrypted strictly in-memory.
- **Direct Local Storage:** The tweets and likes are stored inside `x_likes.db` on your local filesystem.
- **Excluded Secrets:** `.gitignore` explicitly prevents database files, logs, or credentials from being committed to Git.

---

## 📄 License

[MIT](LICENSE) © 2026 winter-loo
