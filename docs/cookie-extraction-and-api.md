# Cookie Extraction & X Web GraphQL Protocol

This document details the mechanics behind local browser session extraction and communication with X's internal web GraphQL endpoints.

---

## 1. Chromium Cookie Encryption on Linux

### 1.1 Password Storage & Secret Service
On Linux systems running desktop environments (GNOME, KDE, etc.), Chromium stores the encryption master password in the user's keyring via the FreeDesktop Secret Service API.

The password can be resolved programmatically via:
```bash
secret-tool lookup application chrome
```
If no keyring entry exists (e.g. headless or minimal environments), Chromium defaults to `peanuts`.

### 1.2 Key Derivation
The encryption key is derived using PBKDF2:
- **Algorithm:** PBKDF2 with HMAC-SHA1
- **Iterations:** 1
- **Salt:** `b"saltysalt"`
- **Key Length:** 16 bytes (128 bits)

```python
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend

kdf = PBKDF2HMAC(
    algorithm=hashes.SHA1(),
    length=16,
    salt=b"saltysalt",
    iterations=1,
    backend=default_backend()
)
key = kdf.derive(password)
```

### 1.3 `v10` vs `v11` Payload Format

| Version Prefix | IV (Initialization Vector) | Cipher | Ciphertext Offset |
|---|---|---|---|
| `v10` | 16 ASCII spaces (`b" " * 16`) | AES-128-CBC | `raw_bytes[3:]` |
| `v11` | Random 16 bytes at beginning | AES-128-CBC | `raw_bytes[19:]` (`iv = raw_bytes[3:19]`) |

In modern Chrome installations on Linux, encrypted values use the `v11` schema. After AES decryption and PKCS#7 unpadding, the first 16 bytes are a validation hash, followed by the plain UTF-8 cookie value.

---

## 2. X Web GraphQL Protocol

### 2.1 Essential Headers
All authenticated GraphQL queries require:
```http
Authorization: Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA
x-csrf-token: <ct0_cookie_value>
x-twitter-active-user: yes
x-twitter-auth-type: OAuth2Session
Cookie: auth_token=<auth_token>; ct0=<ct0>
```

### 2.2 GraphQL Operation Query IDs

These Query IDs correspond to operations compiled into X's web bundle (`responsive-web`):

| Operation | Query ID | HTTP Method | Endpoint |
|---|---|---|---|
| `Likes` | `XHn_Tw60c6pi0n3DGhpwiA` | `GET` | `/i/api/graphql/{queryId}/Likes` |
| `UnfavoriteTweet` | `ZYKSe-w7KEslx3JhSIk5LA` | `POST` | `/i/api/graphql/{queryId}/UnfavoriteTweet` |
| `FavoriteTweet` | `lI07N6Otwv1PhnEgXILM7A` | `POST` | `/i/api/graphql/{queryId}/FavoriteTweet` |

### 2.3 Likes Timeline Pagination
1. Initial query passes `userId` and `count: 40`.
2. Response contains instructions with entries of type `TimelineTimelineItem` (tweets) and `TimelineTimelineCursor` (`cursorType: "Bottom"`).
3. The bottom cursor value is passed as `cursor` in subsequent requests until no further entries are returned.

### 2.4 Tweet Body Normalization
- Standard tweets: stored in `legacy.full_text`.
- Long-form articles (Note Tweets): stored in `note_tweet.note_tweet_results.result.text`.
The extraction pipeline evaluates `note_tweet` first to prevent truncation of substantive posts.
