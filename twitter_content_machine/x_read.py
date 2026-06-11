from __future__ import annotations

import json
import os
from pathlib import Path
from urllib import error, parse, request

from .config import Config, load_config
from .db import connect_db, upsert_fts
from .models import SyncResult
from .utils import iso_now, short_hash
from .workspace import ensure_workspace


API_BASE = "https://api.x.com/2"


class XReadProvider:
    def get_own_recent_posts(self) -> list[dict[str, str]]:
        return []

    def get_user_recent_posts(self, username: str, limit: int) -> list[dict[str, str]]:
        return []

    def get_post_thread(self, url_or_id: str) -> list[dict[str, str]]:
        return []

    def get_user_following(self, username: str, limit: int) -> list[dict]:
        return []

    def get_user_followers(self, username: str, limit: int) -> list[dict]:
        return []

    def search_users(self, query: str, limit: int) -> list[dict]:
        return []

    def search_recent_posts(self, query: str, limit: int) -> list[dict]:
        return []


class NoneProvider(XReadProvider):
    pass


class XAPIProvider(XReadProvider):
    def __init__(self, token: str, config: Config | None = None) -> None:
        self.token = token
        self.config = config or load_config()
        self.errors: list[str] = []

    def get_user_recent_posts(self, username: str, limit: int) -> list[dict[str, str]]:
        user_id = self._lookup_user_id(username)
        if not user_id:
            return []
        posts, _message = _fetch_timeline(user_id, self.token, self.config, limit)
        return [
            {
                **item,
                "author_username": normalize_username(username),
                "url": f"https://x.com/{normalize_username(username)}/status/{item.get('id', '')}",
            }
            for item in posts
        ]

    def get_user_following(self, username: str, limit: int) -> list[dict]:
        user_id = self._lookup_user_id(username)
        if not user_id:
            return []
        payload = self._request_json(_following_url(user_id, limit), "get_user_following")
        return list(payload.get("data") or [])

    def get_user_followers(self, username: str, limit: int) -> list[dict]:
        user_id = self._lookup_user_id(username)
        if not user_id:
            return []
        payload = self._request_json(_followers_url(user_id, limit), "get_user_followers")
        return list(payload.get("data") or [])

    def search_users(self, query: str, limit: int) -> list[dict]:
        payload = self._request_json(_user_search_url(query, limit), "search_users")
        return list(payload.get("data") or [])

    def search_recent_posts(self, query: str, limit: int) -> list[dict]:
        payload = self._request_json(_recent_search_url(query, limit), "search_recent_posts")
        users = {
            str(user.get("id") or ""): user
            for user in (payload.get("includes") or {}).get("users", [])
        }
        posts = []
        for item in payload.get("data") or []:
            author = users.get(str(item.get("author_id") or ""), {})
            username = str(author.get("username") or item.get("username") or "")
            posts.append(
                {
                    **item,
                    "author_username": username,
                    "author_name": str(author.get("name") or ""),
                    "author_description": str(author.get("description") or ""),
                    "url": f"https://x.com/{username}/status/{item.get('id', '')}" if username else "",
                }
            )
        return posts

    def _lookup_user_id(self, username: str) -> str | None:
        payload = self._request_json(_username_url(username), "lookup_user")
        data = payload.get("data") or {}
        return str(data.get("id") or "") or None

    def _request_json(self, url: str, action: str) -> dict:
        try:
            return _request_json(url, self.token)
        except error.HTTPError as exc:
            self.errors.append(f"{action}: HTTP {exc.code} {exc.reason}")
        except Exception as exc:
            self.errors.append(f"{action}: {type(exc).__name__}: {exc}")
        return {}


def _bearer_token() -> str:
    return os.environ.get("X_BEARER_TOKEN", "").strip()


def _request_json(url: str, token: str, timeout: int = 30) -> dict:
    req = request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with request.urlopen(req, timeout=timeout) as resp:  # nosec - URL is fixed API base.
        data = resp.read()
    return json.loads(data.decode("utf-8"))


def _safe_request_json(url: str, token: str) -> dict:
    try:
        return _request_json(url, token)
    except Exception:
        return {}


def _timeline_url(user_id: str, config: Config, limit: int, pagination_token: str | None = None) -> str:
    excludes: list[str] = []
    if config.x_exclude_retweets:
        excludes.append("retweets")
    if config.x_exclude_replies:
        excludes.append("replies")
    params: dict[str, str | int] = {
        "max_results": max(5, min(100, limit)),
        "tweet.fields": "created_at,conversation_id,public_metrics,referenced_tweets,lang",
    }
    if excludes:
        params["exclude"] = ",".join(excludes)
    if pagination_token:
        params["pagination_token"] = pagination_token
    return f"{API_BASE}/users/{parse.quote(user_id)}/tweets?{parse.urlencode(params)}"


def _username_url(username: str) -> str:
    clean = normalize_username(username)
    params = parse.urlencode({"user.fields": "id,username,name"})
    return f"{API_BASE}/users/by/username/{parse.quote(clean)}?{params}"


def _user_fields() -> str:
    return "id,username,name,description,public_metrics,verified,protected,created_at"


def _post_fields() -> str:
    return "id,text,created_at,author_id,conversation_id,public_metrics,referenced_tweets,lang"


def _following_url(user_id: str, limit: int, pagination_token: str | None = None) -> str:
    params: dict[str, str | int] = {
        "max_results": max(1, min(1000, limit)),
        "user.fields": _user_fields(),
    }
    if pagination_token:
        params["pagination_token"] = pagination_token
    return f"{API_BASE}/users/{parse.quote(user_id)}/following?{parse.urlencode(params)}"


def _followers_url(user_id: str, limit: int, pagination_token: str | None = None) -> str:
    params: dict[str, str | int] = {
        "max_results": max(1, min(1000, limit)),
        "user.fields": _user_fields(),
    }
    if pagination_token:
        params["pagination_token"] = pagination_token
    return f"{API_BASE}/users/{parse.quote(user_id)}/followers?{parse.urlencode(params)}"


def _user_search_url(query: str, limit: int) -> str:
    params: dict[str, str | int] = {
        "query": query,
        "max_results": max(1, min(100, limit)),
        "user.fields": _user_fields(),
    }
    return f"{API_BASE}/users/search?{parse.urlencode(params)}"


def _recent_search_url(query: str, limit: int) -> str:
    params: dict[str, str | int] = {
        "query": query,
        "max_results": max(10, min(100, limit)),
        "tweet.fields": _post_fields(),
        "expansions": "author_id",
        "user.fields": _user_fields(),
    }
    return f"{API_BASE}/tweets/search/recent?{parse.urlencode(params)}"


def normalize_username(value: str) -> str:
    value = value.strip()
    if value.startswith("http://") or value.startswith("https://"):
        parsed = parse.urlparse(value)
        parts = [part for part in parsed.path.split("/") if part]
        return parts[0].lstrip("@") if parts else value
    return value.lstrip("@")


def _lookup_user_id(username: str, token: str) -> str | None:
    try:
        payload = _request_json(_username_url(username), token)
    except Exception:
        return None
    data = payload.get("data") or {}
    return str(data.get("id") or "") or None


def get_provider() -> XReadProvider:
    workspace = ensure_workspace()
    config = load_config(workspace.root)
    if config.x_provider == "none":
        return NoneProvider()
    if config.x_provider == "x_api" and not _bearer_token():
        return NoneProvider()
    if config.x_provider == "x_api":
        return XAPIProvider(_bearer_token(), config)
    return NoneProvider()


def x_read_setup_problem() -> str | None:
    workspace = ensure_workspace()
    config = load_config(workspace.root)
    config_path = workspace.root / "config.toml"
    if config.x_provider != "x_api":
        return f"""live X read provider is not configured.

Current:
- config: {config_path}
- [x].provider = "{config.x_provider}"

To enable read-only X scan:
1. Edit {config_path}

[x]
provider = "x_api"
readonly = true

2. Set a read-only bearer token in this PowerShell session:

$env:X_BEARER_TOKEN = "<your X API bearer token>"

3. Re-run:

tw graph-scan --cluster quant --limit 30 --posts 50

No X write actions are used."""
    if not config.x_readonly:
        return f"""Refusing live X scan because [x].readonly = false in {config_path}.

Set:

[x]
readonly = true
"""
    if not _bearer_token():
        return f"""live X read provider is configured, but X_BEARER_TOKEN is missing.

Set a read-only bearer token in this PowerShell session:

$env:X_BEARER_TOKEN = "<your X API bearer token>"

Then re-run:

tw graph-scan --cluster quant --limit 30 --posts 50
"""
    return None


def _fetch_timeline(user_id: str, token: str, config: Config, limit: int) -> tuple[list[dict], str | None]:
    items: list[dict] = []
    next_token: str | None = None
    message: str | None = None
    while len(items) < limit:
        url = _timeline_url(user_id, config, limit - len(items), next_token)
        try:
            payload = _request_json(url, token)
        except error.HTTPError as exc:
            message = f"X API error {exc.code}. Nothing imported."
            break
        except error.URLError as exc:
            message = f"X API network error: {exc.reason}. Nothing imported."
            break
        except Exception as exc:
            message = f"X API read failed: {exc}. Nothing imported."
            break
        items.extend(payload.get("data") or [])
        meta = payload.get("meta") or {}
        next_token = meta.get("next_token")
        if not next_token:
            break
    return items[:limit], message


def _store_own_posts(posts: list[dict]) -> int:
    workspace = ensure_workspace()
    imported = 0
    posted_dir = workspace.root / "posted"
    posted_dir.mkdir(parents=True, exist_ok=True)
    with connect_db() as conn:
        for item in posts:
            platform_post_id = str(item.get("id") or "")
            text = str(item.get("text") or "").strip()
            if not platform_post_id or not text:
                continue
            post_id = f"x_{platform_post_id}"
            existing = conn.execute("select id from posts where id = ?", (post_id,)).fetchone()
            created_at = str(item.get("created_at") or iso_now())
            url = f"https://x.com/i/web/status/{platform_post_id}"
            conn.execute(
                """
                insert or ignore into posts(id, created_at, platform, platform_post_id, url, text, thread_id,
                  project_id, source_draft_id, tags)
                values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    post_id,
                    created_at,
                    "x",
                    platform_post_id,
                    url,
                    text,
                    str(item.get("conversation_id") or ""),
                    "",
                    "",
                    "own_sync",
                ),
            )
            upsert_fts(conn, "posts_fts", (post_id, text, "own_sync"))
            if not existing:
                imported += 1
                (posted_dir / f"{created_at[:10]}-{platform_post_id}.md").write_text(
                    f"# X Post\n\n- id: {platform_post_id}\n- url: {url}\n- created_at: {created_at}\n\n{text}\n",
                    encoding="utf-8",
                )
    return imported


def _store_external_posts(username: str, posts: list[dict]) -> int:
    workspace = ensure_workspace()
    target_dir = workspace.root / "sources" / "x_posts" / normalize_username(username)
    target_dir.mkdir(parents=True, exist_ok=True)
    imported = 0
    with connect_db() as conn:
        for item in posts:
            platform_post_id = str(item.get("id") or "")
            text = str(item.get("text") or "").strip()
            if not platform_post_id or not text:
                continue
            source_id = f"xsrc_{normalize_username(username)}_{platform_post_id}"
            created_at = str(item.get("created_at") or iso_now())
            url = f"https://x.com/{normalize_username(username)}/status/{platform_post_id}"
            existing = conn.execute("select id from sources where id = ?", (source_id,)).fetchone()
            conn.execute(
                """
                insert or ignore into sources(id, created_at, type, url, title, author, raw_text, summary, tags)
                values(?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (source_id, created_at, "x_post", url, f"X post {platform_post_id}", normalize_username(username), text, text, "peer"),
            )
            upsert_fts(conn, "sources_fts", (source_id, f"X post {platform_post_id}", text, text, "peer"))
            if not existing:
                imported += 1
                (target_dir / f"{created_at[:10]}-{platform_post_id}.md").write_text(
                    f"# X Source Post\n\n- author: {normalize_username(username)}\n- id: {platform_post_id}\n- url: {url}\n- created_at: {created_at}\n\n{text}\n",
                    encoding="utf-8",
                )
    return imported


def sync_posted() -> SyncResult:
    workspace = ensure_workspace()
    config = load_config(workspace.root)
    if config.x_provider == "none":
        return SyncResult(0, "read-only X sync is disabled. Set [x].provider in config.toml to enable imports.")
    if not config.x_readonly:
        return SyncResult(0, "Refusing X sync because readonly=false. MVP supports read-only imports only.")
    if config.x_provider != "x_api":
        return SyncResult(0, f"Unsupported X read provider: {config.x_provider}. Nothing imported.")
    token = _bearer_token()
    if not token:
        return SyncResult(0, "X API provider configured, but X_BEARER_TOKEN is missing. Nothing imported.")
    user_id = config.x_user_id or os.environ.get("X_USER_ID", "")
    if not user_id and config.x_username:
        user_id = _lookup_user_id(config.x_username, token) or ""
    if not user_id:
        return SyncResult(0, "X API provider configured, but user_id is missing. Set X_USER_ID or [x].user_id.")
    posts, message = _fetch_timeline(user_id, token, config, config.x_max_import)
    if message:
        return SyncResult(0, message)
    imported = _store_own_posts(posts)
    return SyncResult(imported, f"read-only X sync complete; imported {imported} new posts.")


def x_read(username_or_url: str, limit: int = 100) -> SyncResult:
    workspace = ensure_workspace()
    config = load_config(workspace.root)
    if not config.x_readonly:
        return SyncResult(0, "Refusing X read because readonly=false. MVP supports read-only imports only.")
    if config.x_provider != "x_api":
        return SyncResult(0, "X API provider is not configured. Set [x].provider = 'x_api' and X_BEARER_TOKEN.")
    token = _bearer_token()
    if not token:
        return SyncResult(0, "X_BEARER_TOKEN is missing. Nothing imported.")
    username = normalize_username(username_or_url)
    user_id = _lookup_user_id(username, token)
    if not user_id:
        return SyncResult(0, f"Could not resolve X username: {username}. Set user_id if needed.")
    posts, message = _fetch_timeline(user_id, token, config, limit)
    if message:
        return SyncResult(0, message)
    imported = _store_external_posts(username, posts)
    return SyncResult(imported, f"read-only X source import complete; imported {imported} posts for @{username}.")


def summarize_posts_from_db(external_author: str | None = None) -> str:
    with connect_db() as conn:
        if external_author:
            rows = conn.execute(
                "select raw_text as text from sources where type = 'x_post' and author = ? order by created_at desc limit 100",
                (normalize_username(external_author),),
            ).fetchall()
        else:
            rows = conn.execute("select text from posts order by created_at desc limit 100").fetchall()
    texts = [str(row["text"]) for row in rows]
    lengths = [len(text) for text in texts]
    avg_len = int(sum(lengths) / max(1, len(lengths)))
    repeated_markers = ["backtest", "execution", "market", "model", "validation", "infra", "crypto"]
    marker_counts = {marker: sum(1 for text in texts if marker in text.lower()) for marker in repeated_markers}
    top_markers = [f"{key}: {value}" for key, value in sorted(marker_counts.items(), key=lambda item: item[1], reverse=True) if value]
    return f"""# X Read Analysis

- posts analyzed: {len(texts)}
- average length: {avg_len}

## Recurring Topic Markers
{chr(10).join(f"- {item}" for item in top_markers) if top_markers else "- not enough data"}

## Notes
- adapt useful formats, not peer voice
- keep draft-only workflow
- avoid direct imitation
"""
