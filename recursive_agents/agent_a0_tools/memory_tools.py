# Licensed under the Apache License 2.0 (see LICENSE) and the Human
# Continuity Supplemental AI Safety License (HCASL) v0.2 - see
# HCASL_License_v0.2.txt. HCASL conditions all AI-related use of this software.
"""
tools/copilot/memory_tools.py — Memory, Web, and Utility Tools

Copilot equivalents: memoryTool.ts, fetchWebpage, githubRepo, etc.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from html.parser import HTMLParser
from typing import Any

from .tool_base import ReadOnlyTool, WebTool, ToolContext, ToolResult


# ── Memory Tools ─────────────────────────────────────────────────────

MEMORY_FILE = "chat_history/.codex/.codex_memory.json"


class MemoryReadTool(ReadOnlyTool):
    tool_name = "memory_read"
    tool_reference_name = "memoryRead"
    display_name = "Memory Read"
    tags = ["memory"]

    tool_schema = {
        "type": "object",
        "required": ["key"],
        "properties": {
            "key": {
                "type": "string",
                "description": "Memory key to read. Use '*' to list all keys with metadata.",
            },
        },
    }

    async def invoke(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        key = args.get("key", "*")
        data = _load_memory()

        if key == "*":
            if not data:
                return ToolResult.ok(content="Memory is empty.")
            lines = ["## Memory Keys", ""]
            now = time.time()
            for k, v in sorted(data.items()):
                ttl = v.get("_ttl", 0)
                tags = v.get("_tags", [])
                tag_str = f" [{', '.join(tags)}]" if tags else ""
                exp_str = ""
                if ttl:
                    expires_at = v.get("_created", 0) + ttl
                    if expires_at < now:
                        lines.append(f"- `{k}`: [EXPIRED]{tag_str}")
                        continue
                    exp_str = f" (expires in {int(expires_at - now)}s)"
                val_preview = str(v.get("_value", v)).replace("\n", " ")[:80]
                lines.append(f"- `{k}`: {val_preview}{tag_str}{exp_str}")
            return ToolResult.ok(content="\n".join(lines), key_count=len(data))
        else:
            value = _get_memory_value(data, key)
            if value is None:
                return ToolResult.ok(content=f"No memory entry for key {key!r}.")
            return ToolResult.ok(content=str(value), key=key)


class MemoryWriteTool(ReadOnlyTool):
    tool_name = "memory_write"
    tool_reference_name = "memoryWrite"
    display_name = "Memory Write"
    tags = ["memory"]

    tool_schema = {
        "type": "object",
        "required": ["key", "value"],
        "properties": {
            "key": {"type": "string", "description": "Memory key to write to."},
            "value": {"type": "string", "description": "Value to store."},
            "ttl_seconds": {
                "type": "number",
                "description": "Time-to-live in seconds. 0 = never expires.",
            },
            "tags": {
                "type": "array", "items": {"type": "string"},
                "description": "Optional tags for organization.",
            },
        },
    }

    async def invoke(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        key = args.get("key", "")
        value = args.get("value", "")
        ttl = int(args.get("ttl_seconds", 0))
        tags = args.get("tags", [])

        if not key:
            return ToolResult.fail("key is required")

        data = _load_memory()
        data[key] = {"_value": value, "_created": time.time(), "_ttl": ttl, "_tags": tags}
        _save_memory(data)

        return ToolResult.ok(content=f"Stored {key!r} in memory." + (f" TTL: {ttl}s" if ttl else ""), key=key)


def _load_memory() -> dict:
    try:
        if os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
                # Clean expired entries
                now = time.time()
                return {
                    k: v for k, v in raw.items()
                    if not v.get("_ttl") or v.get("_created", 0) + v["_ttl"] > now
                }
    except Exception:
        pass
    return {}


def _save_memory(data: dict) -> None:
    os.makedirs(os.path.dirname(MEMORY_FILE), exist_ok=True)
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _get_memory_value(data: dict, key: str) -> Any:
    entry = data.get(key)
    if not entry:
        return None
    ttl = entry.get("_ttl", 0)
    if ttl and entry.get("_created", 0) + ttl < time.time():
        return None
    return entry.get("_value")


# ── Web Tools ────────────────────────────────────────────────────────

class WebSearchTool(WebTool):
    """Web search and URL fetch tool.

    Uses curl subprocess for real browser-like fetching (handles JS-heavy sites
    and anti-bot protection better than urllib). For search, tries Google News
    RSS first, then falls back to DuckDuckGo HTML.
    """

    tool_name = "web_search"
    tool_reference_name = "fetchWebpage"
    display_name = "Web Search / Fetch"
    deferred = True

    CURL_UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )

    tool_schema = {
        "type": "object",
        "required": ["query"],
        "properties": {
            "query": {
                "type": "string",
                "description": "URL to fetch, or search query if using search mode.",
            },
            "max_results": {
                "type": "number",
                "description": "Max results. Default: 5.",
            },
            "search_mode": {
                "type": "string",
                "enum": ["auto", "url", "search"],
                "description": "auto: detect URL vs query. url: direct fetch. search: web search.",
            },
        },
    }

    # ══════════════════════════════════════════════════════════════════
    # Main invoke
    # ══════════════════════════════════════════════════════════════════

    async def invoke(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        query = args.get("query", "").strip()
        mode = args.get("search_mode", "auto")
        max_results = int(args.get("max_results", 5))

        if not query:
            return ToolResult.fail("query is required")

        # URL detection
        is_url = query.startswith("http://") or query.startswith("https://")
        if mode == "auto":
            mode = "url" if is_url else "search"

        if mode == "url":
            return await self._fetch_url(query)
        else:
            return await self._web_search(query, max_results)

    # ══════════════════════════════════════════════════════════════════
    # URL Fetch — curl primary, httpx fallback
    # ══════════════════════════════════════════════════════════════════

    def _fetch_with_curl(self, url: str, timeout: int = 20) -> tuple[str, str, int]:
        """Fetch a URL using curl subprocess. Returns (body, final_url, size)."""
        import subprocess as _sp
        r = _sp.run([
            'curl', '-s', '-L', '--max-time', str(timeout),
            '-H', f'User-Agent: {self.CURL_UA}',
            '-H', 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            '-H', 'Accept-Language: en-US,en;q=0.9',
            '-H', 'Cache-Control: no-cache',
            url,
        ], capture_output=True, timeout=timeout + 5)

        if r.returncode != 0:
            err = r.stderr.decode('utf-8', errors='replace')
            raise RuntimeError(f"curl error {r.returncode}: {err[:200]}")

        raw = r.stdout
        text = raw.decode('utf-8', errors='replace')
        size = len(raw)
        return text, url, size

    async def _fetch_url(self, url: str) -> ToolResult:
        """Fetch a URL — curl first, then httpx fallback."""
        import html as _html
        import re as _re

        body = ""
        final_url = url

        # Try curl first
        try:
            body, final_url, _ = self._fetch_with_curl(url)
        except Exception:
            # Fallback: httpx
            try:
                import httpx
                async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers={
                    "User-Agent": self.CURL_UA,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                }) as client:
                    resp = await client.get(url)
                    body = resp.text
                    final_url = str(resp.url)
            except Exception as e:
                return ToolResult.fail(f"Fetch failed: {e}")

        if not body:
            return ToolResult.fail("Empty response body")

        # Extract title
        title = ''
        title_match = _re.search(r'<title[^>]*>([^<]+)</title>', body, _re.IGNORECASE)
        if title_match:
            title = _html.unescape(title_match.group(1).strip())

        # Extract text
        text = _html_to_text_robust(body, 8000)

        result = (
            f"URL: {url}\n"
            f"Title: {title or '(no title)'}\n"
            f"{'-'*40}\n"
            f"{text}"
        )
        return ToolResult.ok(content=result, url=url, title=title)

    # ══════════════════════════════════════════════════════════════════
    # Web Search — Google News RSS primary, DDG HTML fallback
    # ══════════════════════════════════════════════════════════════════

    async def _web_search(self, query: str, max_results: int = 5) -> ToolResult:
        """Search the web — Google News RSS first, then DDG HTML fallback."""
        import html as _html
        import re as _re
        from urllib.parse import quote_plus

        results: list[str] = []

        # ── Primary: Google News RSS ──────────────────────────────────
        try:
            rss_url = (
                f"https://news.google.com/rss/search?"
                f"q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
            )
            rss_body, _, _ = self._fetch_with_curl(rss_url)

            items = _re.findall(r'<item>(.*?)</item>', rss_body, _re.DOTALL)
            for item in items[:max_results]:
                t = _re.search(r'<title>(.*?)</title>', item)
                l = _re.search(r'<link>(.*?)</link>', item)
                d = _re.search(r'<description>(.*?)</description>', item)
                title_text = _html.unescape(_re.sub(r'<[^>]+>', '', t.group(1).strip())) if t else ''
                link_text = l.group(1).strip() if l else ''
                desc_text = _html.unescape(_re.sub(r'<[^>]+>', '', d.group(1).strip())) if d else ''
                if title_text:
                    results.append(
                        f"  {len(results)+1}. {title_text[:150]}\n"
                        f"     {link_text}\n"
                        f"     {desc_text[:250]}"
                    )
        except Exception:
            pass

        if len(results) >= max_results:
            return ToolResult.ok(
                content=(
                    f"Search: '{query}' (Google News)\n"
                    f"Results: {len(results)}\n"
                    f"{'-'*40}\n" + "\n".join(results)
                ),
                query=query, result_count=len(results), source="google_news_rss",
            )

        # ── Fallback: DuckDuckGo HTML ──────────────────────────────────
        try:
            import httpx
            ddg_url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
            async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers={
                "User-Agent": self.CURL_UA,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            }) as client:
                resp = await client.get(ddg_url)
                ddg_html = resp.text

            ddg_results = _extract_ddg_results_robust(ddg_html, max_results - len(results))
            for r in ddg_results:
                results.append(
                    f"  {len(results)+1}. {r['title'][:150]}\n"
                    f"     {r['url']}\n"
                    f"     {r['snippet'][:250]}"
                )
        except Exception:
            pass

        if not results:
            return ToolResult.ok(
                content=(
                    f"Search: '{query}'\n"
                    f"No results found. Try a different query or use search_mode='url' "
                    f"to fetch a specific page."
                ),
                query=query,
            )

        return ToolResult.ok(
            content=(
                f"Search: '{query}'\n"
                f"Results: {len(results)}\n"
                f"{'-'*40}\n" + "\n".join(results)
            ),
            query=query, result_count=len(results),
        )


# ══════════════════════════════════════════════════════════════════════════════
# Robust HTML-to-Text — curl-aware, handles malformed HTML
# ══════════════════════════════════════════════════════════════════════════════

def _html_to_text_robust(html: str, max_len: int = 8000) -> str:
    """Extract readable text from HTML. Handles malformed HTML gracefully."""
    import re as _re
    from html.parser import HTMLParser

    class _Stripper(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts: list[str] = []
            self.skip_depth = 0

        def handle_starttag(self, tag, attrs):
            if tag in ('script', 'style', 'noscript'):
                self.skip_depth += 1
            elif tag in ('p', 'br', 'li', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
                         'tr', 'article', 'section', 'header', 'footer', 'nav', 'main'):
                self.parts.append('\n')

        def handle_endtag(self, tag):
            if tag in ('script', 'style', 'noscript'):
                self.skip_depth = max(0, self.skip_depth - 1)
            elif tag in ('p', 'br', 'li', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
                         'tr', 'article', 'section'):
                self.parts.append('\n')

        def handle_data(self, data):
            if self.skip_depth == 0:
                stripped = data.strip()
                if stripped:
                    self.parts.append(stripped + ' ')

    s = _Stripper()
    try:
        s.feed(html)
    except Exception:
        pass
    text = ''.join(s.parts)
    text = _re.sub(r'\n{3,}', '\n\n', text)
    text = _re.sub(r'[ \t]{2,}', ' ', text)
    text = text.strip()
    return text[:max_len] + ('...[truncated]' if len(text) > max_len else '')


def _extract_ddg_results_robust(html: str, max_results: int = 5) -> list[dict]:
    """Extract search results from DuckDuckGo HTML with multiple fallback patterns."""
    import re as _re
    results: list[dict] = []

    # Pattern 1: DDG classic result__a / result__snippet
    for match in _re.finditer(
        r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        html, _re.DOTALL | _re.IGNORECASE,
    ):
        title = _re.sub(r'<[^>]+>', '', match.group(2)).strip()
        title = title.replace('&amp;', '&').replace('&#x27;', "'")
        url = match.group(1).replace('&amp;', '&')
        # Decode DDG redirect
        if 'uddg=' in url:
            from urllib.parse import unquote
            url = unquote(url.split('uddg=')[-1].split('&')[0].split('&amp;')[0])
        results.append({"url": url, "title": title, "snippet": ""})
        if len(results) >= max_results:
            return results

    # Pattern 2: Generic link extraction (DDG modern layout)
    for match in _re.finditer(
        r'<a[^>]*href="(https?://[^"]+)"[^>]*>(.{10,250}?)</a>',
        html, _re.DOTALL | _re.IGNORECASE,
    ):
        url = match.group(1)
        title = _re.sub(r'<[^>]+>', '', match.group(2)).strip()
        if any(skip in url.lower() for skip in
               ('duckduckgo.com', 'duck.com', '/l/?', 'ad.', 'doubleclick', 'google.com/maps')):
            continue
        if len(title) < 10:
            continue
        results.append({"url": url, "title": title, "snippet": ""})
        if len(results) >= max_results:
            return results

    return results

class CurrentTimeTool(ReadOnlyTool):
    tool_name = "current_time"
    display_name = "Current Time"
    tags = ["utility"]

    tool_schema = {"type": "object", "properties": {}}

    async def invoke(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        import datetime
        now = datetime.datetime.now()
        utc = datetime.datetime.utcnow()
        return ToolResult.ok(
            content=f"Local: {now.isoformat()}\n"
            f"UTC: {utc.isoformat()}\n"
            f"Unix: {int(time.time())}\n"
            f"Day: {now.strftime('%A')}"
        )


class GetErrorsTool(ReadOnlyTool):
    tool_name = "get_errors"
    tool_reference_name = "getErrors"
    display_name = "Get Errors"
    tags = ["utility"]

    tool_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Optional: check a specific file or directory for errors.",
            },
        },
    }

    async def invoke(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        # In VS Code, this would read from the Problems panel.
        # In Codex Local, we check Python syntax via compile as a basic check.
        path = args.get("path", context.workspace_root or ".")
        abs_path = os.path.abspath(os.path.expanduser(path))

        errors = []
        if os.path.isfile(abs_path) and abs_path.endswith(".py"):
            try:
                with open(abs_path, "r", encoding="utf-8") as f:
                    compile(f.read(), abs_path, "exec")
            except SyntaxError as e:
                errors.append(f"{abs_path}:{e.lineno}: SyntaxError: {e.msg}")

        if not errors:
            return ToolResult.ok(content="No syntax errors detected.")

        return ToolResult.ok(content="\n".join(errors), error_count=len(errors))


class ViewImageTool(ReadOnlyTool):
    tool_name = "view_image"
    tool_reference_name = "viewImage"
    display_name = "View Image"
    tags = ["read"]

    tool_schema = {
        "type": "object",
        "required": ["filePath"],
        "properties": {
            "filePath": {
                "type": "string",
                "description": "The absolute path to the image file.",
            },
        },
    }

    async def invoke(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        path = args.get("filePath", "")
        abs_path = os.path.abspath(os.path.expanduser(path))

        if not os.path.exists(abs_path):
            return ToolResult.fail(f"File not found: {abs_path}")

        try:
            # Try PIL if available
            try:
                from PIL import Image
                img = Image.open(abs_path)
                return ToolResult.ok(
                    content=f"Image: {os.path.basename(abs_path)}\n"
                    f"Format: {img.format}\n"
                    f"Size: {img.size[0]}x{img.size[1]}\n"
                    f"Mode: {img.mode}",
                    filePath=abs_path, dimensions=img.size, format=img.format,
                )
            except ImportError:
                pass

            # Fallback: basic detection via file header
            with open(abs_path, "rb") as f:
                header = f.read(16)

            if header[:8] == b"\x89PNG\r\n\x1a\n":
                import struct
                w, h = struct.unpack(">II", f.read(8)[:8]) if False else ("?", "?")
                return ToolResult.ok(content=f"PNG image: {os.path.basename(abs_path)}", filePath=abs_path, format="PNG")
            elif header[:2] == b"\xff\xd8":
                return ToolResult.ok(content=f"JPEG image: {os.path.basename(abs_path)}", filePath=abs_path, format="JPEG")
            else:
                return ToolResult.ok(content=f"Image file: {os.path.basename(abs_path)} ({os.path.getsize(abs_path)} bytes)", filePath=abs_path)
        except Exception as e:
            return ToolResult.fail(f"Error reading image: {e}")


class RequestUserInputTool(ReadOnlyTool):
    tool_name = "request_user_input"
    tool_reference_name = "askUser"
    display_name = "Request User Input"
    tags = ["utility"]

    tool_schema = {
        "type": "object",
        "required": ["question"],
        "properties": {
            "question": {"type": "string", "description": "The question to ask the user."},
            "choices": {
                "type": "array", "items": {"type": "string"},
                "description": "Optional list of valid choices.",
            },
            "default": {"type": "string", "description": "Default answer."},
        },
    }

    async def invoke(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        question = args.get("question", "")
        choices = args.get("choices", [])
        default = args.get("default", "")

        qid = str(__import__("uuid").uuid4())[:8]

        # Store pending question
        if not hasattr(context, "_pending_questions"):
            context.metadata["_pending_questions"] = {}
        context.metadata["_pending_questions"][qid] = {
            "question": question, "choices": choices, "default": default, "answered": False,
        }

        lines = [f"[QUESTION {qid}] {question}"]
        if choices:
            lines.append(f"Choices: {', '.join(choices)}")
        lines.append(f"User responds with: /answer {qid} <response>")

        return ToolResult.ok(content="\n".join(lines), question_id=qid)


class SendNotificationTool(ReadOnlyTool):
    tool_name = "send_notification"
    tool_reference_name = "sendNotification"
    display_name = "Send Notification"
    deferred = True
    tags = ["utility"]

    tool_schema = {
        "type": "object",
        "required": ["title", "message"],
        "properties": {
            "title": {"type": "string", "description": "Notification title."},
            "message": {"type": "string", "description": "Notification body."},
            "priority": {"type": "number", "description": "Priority 0-2. Default: 0."},
        },
    }

    async def invoke(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        title = args.get("title", "")
        message = args.get("message", "")

        try:
            from config import Config
            if Config.PUSHOVER_USER and Config.PUSHOVER_TOKEN:
                import httpx
                resp = httpx.post("https://api.pushover.net/1/messages.json", data={
                    "token": Config.PUSHOVER_TOKEN,
                    "user": Config.PUSHOVER_USER,
                    "title": title,
                    "message": message,
                    "priority": args.get("priority", 0),
                }, timeout=10)
                if resp.status_code == 200:
                    return ToolResult.ok(content=f"Notification sent: {title}")
                return ToolResult.fail(f"Pushover error: {resp.status_code}")
            return ToolResult.fail("Pushover not configured. Set PUSHOVER_USER and PUSHOVER_TOKEN in LLMs/.env")
        except ImportError:
            return ToolResult.ok(content=f"[Notification would be sent]: {title} — {message} (httpx not installed)")
