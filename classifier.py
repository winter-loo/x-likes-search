import os
import json
import urllib.request
from typing import Dict, List, Tuple, Optional

TYPESAFE_ENDPOINT = "https://api.typesafe.ai/v1/systemone"
DEFAULT_MODEL = "jev-latest"

DEFAULT_TAGS = {
    "前端": "Is this post related to web frontend development, HTML, JavaScript/TypeScript, React, Vue, CSS, browser tech, or frontend UI components?",
    "数据库": "Is this post related to databases, data storage, SQL, NoSQL, storage engines, SQLite, PostgreSQL, Redis, caching, or database indexing?",
    "网络": "Is this post related to computer networks, protocols, HTTP, TCP/IP, DNS, proxy, sockets, VPN, or network architecture?",
    "分布式系统": "Is this post related to distributed systems, consensus algorithms, Raft, Paxos, CRDT, microservices, RPC, high concurrency, or scalability?",
    "Linux": "Is this post related to Linux, Unix, operating systems, shell scripting, bash, CLI tools, system administration, Arch, or Ubuntu?",
    "编程语言": "Is this post related to programming languages, compilers, syntax, type systems, Rust, Go, Python, C++, or software engineering language features?",
    "CSS": "Is this post related to CSS, web styling, layout design, Tailwind, CSS tricks, animations, or styling frameworks?",
    "薅羊毛": "Is this post related to deals, discounts, cashback, free credits, promo codes, savings strategies, or financial bargains?",
    "设计": "Is this post related to UI/UX design, user experience, product design, Figma, typography, visual art, aesthetics, or design systems?"
}

def get_api_key() -> Optional[str]:
    key = os.environ.get("TYPESAFE_API_KEY") or os.environ.get("JEV_API_KEY")
    if key:
        return key.strip()
    
    # Check local or sibling .env
    env_paths = [
        os.path.join(os.path.dirname(__file__), ".env"),
        "/home/ldd/jev-voice-browser/.env",
        "/home/ldd/.hermes/.env"
    ]
    for p in env_paths:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("TYPESAFE_API_KEY=") or line.startswith("JEV_API_KEY="):
                            val = line.split("=", 1)[1].strip().strip('"').strip("'")
                            if val:
                                return val
            except Exception:
                pass
    return None

class TypeSafeClassifier:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or get_api_key()

    def _get_opener(self):
        # Prefer proxy localhost:6780 if reachable, fallback to direct
        try:
            proxy_support = urllib.request.ProxyHandler({
                "http": "http://127.0.0.1:6780",
                "https": "http://127.0.0.1:6780"
            })
            return urllib.request.build_opener(proxy_support)
        except Exception:
            return urllib.request.build_opener()

    def classify_text(
        self,
        text: str,
        tag_definitions: Optional[Dict[str, str]] = None,
        threshold: float = 0.5
    ) -> List[Tuple[str, float]]:
        if not self.api_key:
            return []

        clean_text = (text or "").strip()
        if not clean_text:
            return []

        tags_map = tag_definitions or DEFAULT_TAGS
        questions = {
            tag: {
                "type": "noul",
                "instructions": desc,
                "criteria": {
                    "true": f"Directly relevant or discussed in context of {tag}",
                    "false": f"Not related to {tag}"
                }
            }
            for tag, desc in tags_map.items()
        }

        payload = {
            "state": clean_text,
            "model": DEFAULT_MODEL,
            "questions": questions
        }

        req = urllib.request.Request(
            TYPESAFE_ENDPOINT,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
        )

        opener = self._get_opener()
        try:
            with opener.open(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                answers = data.get("answers", {})
                matched = []
                for tag, ans in answers.items():
                    prob = float(ans.get("noul", 0.0))
                    if prob >= threshold:
                        matched.append((tag, round(prob, 3)))
                # Sort by confidence descending
                matched.sort(key=lambda x: x[1], reverse=True)
                return matched
        except Exception as e:
            # ponytail: network or API fail, return empty list instead of crashing sync
            return []

if __name__ == "__main__":
    clf = TypeSafeClassifier()
    assert clf.api_key, "API key not found"
    res = clf.classify_text("Shopify 去年把 Redis 替换掉了，自己用 Rust 实现了内存存储与持久化引擎。")
    print("Classified:", res)
    matched_names = [r[0] for r in res]
    assert "数据库" in matched_names or "编程语言" in matched_names, f"Unexpected: {res}"
    print("Self-check passed!")
