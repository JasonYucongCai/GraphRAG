# Licensed under the Apache License 2.0 (see LICENSE) and the Human
# Continuity Supplemental AI Safety License (HCASL) v0.2 - see
# HCASL_License_v0.2.txt. HCASL conditions all AI-related use of this software.
"""tools/copilot/web_tools.py — Web, GitHub, & Fetch tools

Uses shared web_utils for JS-skeleton detection, RSS fallback, and curl fetch.
"""
from __future__ import annotations
from typing import Any
from .tool_base import WebTool, ReadOnlyTool, ToolContext, ToolResult
from tools.web_utils import (
    is_ssrf_safe, fetch_with_curl, html_to_text,
    is_js_skeleton, rewrite_url, get_rss_description,
)


class FetchWebpageTool(WebTool):
    """Fetch webpage content with JS-skeleton detection and RSS fallback.

    Uses curl for browser-like fetching. Automatically detects JavaScript-
    rendered pages and falls back to Google News RSS for headlines.
    """

    tool_name = "fetch_webpage"
    tool_reference_name = "fetch"
    display_name = "Fetch Webpage"
    deferred = True

    tool_schema = {
        "type": "object",
        "required": ["urls", "query"],
        "properties": {
            "urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": "URLs to fetch content from.",
            },
            "query": {
                "type": "string",
                "description": "What to find in the page content.",
            },
        },
    }

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        urls = args.get("urls", [])
        query = args.get("query", "")
        results = []

        for url in urls[:5]:
            if not url:
                continue
            # Ensure scheme
            if not url.startswith(("http://", "https://")):
                url = "https://" + url

            # SSRF check
            safe, reason = is_ssrf_safe(url)
            if not safe:
                results.append(f"--- {url} ---\nBlocked: {reason}")
                continue

            # Check RSS rewrite
            rewritten = rewrite_url(url)
            if rewritten == 'rss':
                results.append(f"--- {url} ---\n{get_rss_description(url)}")
                continue
            elif rewritten:
                url = rewritten

            # Fetch
            try:
                body, final_url, content_size = fetch_with_curl(url[:500], timeout=15)
            except Exception as e:
                results.append(f"--- {url} ---\nFetch error: {e}")
                continue

            # JS-skeleton check
            if is_js_skeleton(body):
                results.append(
                    f"--- {url} ---\n"
                    f"⚠️ JS-rendered page ({content_size:,} bytes). "
                    f"No text content extractable. "
                    f"Use web_search for this site instead."
                )
                continue

            # Extract text
            text = html_to_text(body, 8000)
            if query and query.lower() not in text.lower():
                # Try to find relevant sections
                import re
                matches = list(re.finditer(
                    r'[^\n]{0,200}' + re.escape(query) + r'[^\n]{0,200}',
                    text, re.IGNORECASE))
                if matches:
                    text = "...\n" + "\n...\n".join(m.group(0) for m in matches[:5]) + "\n..."
                else:
                    text = text[:2000]

            results.append(
                f"--- {url} ({content_size:,} bytes) ---\n{text[:5000]}"
            )

        if not results:
            return ToolResult.ok(content=f"No content fetched from {urls}")

        return ToolResult.ok(content="\n\n".join(results))


class GithubRepoTool(WebTool):
    tool_name = "github_repo"
    tool_reference_name = "githubRepo"
    display_name = "GitHub Repo Search"
    deferred = True
    tool_schema = {
        "type": "object", "required": ["repo", "query"],
        "properties": {
            "repo": {"type": "string", "description": "Repository name: owner/repo."},
            "query": {"type": "string", "description": "What to search for in the repo."},
        },
    }

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        return ToolResult.ok(content=f"GitHub repo search: {args.get('query','')} in {args.get('repo','')}\n(requires GitHub API token for full functionality)")


class GithubTextSearchTool(WebTool):
    tool_name = "github_text_search"
    tool_reference_name = "githubTextSearch"
    display_name = "GitHub Text Search"
    deferred = True
    tool_schema = {
        "type": "object", "required": ["scope", "query"],
        "properties": {
            "scope": {"type": "string", "description": "owner/repo or org name."},
            "query": {"type": "string", "description": "Text/regex to search for."},
            "maxResults": {"type": "number", "description": "Max results. Default 100."},
        },
    }

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        return ToolResult.ok(content=f"GitHub text search: {args.get('query','')} in {args.get('scope','')}\n(requires GitHub API token for full functionality)")


class ToolSearchTool(ReadOnlyTool):
    tool_name = "tool_search"
    tool_reference_name = "toolSearch"
    display_name = "Tool Search"
    deferred = True
    tags = ["utility"]
    tool_schema = {
        "type": "object", "properties": {
            "query": {"type": "string", "description": "What tool to search for."},
        },
    }

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        from tools.copilot.tool_registry import get_tool_registry
        reg = get_tool_registry()
        query = (args.get("query", "")).lower()
        matches = []
        for t in reg.get_summary().get("tools", []):
            name = t["name"]
            if query in name.lower() or query in t.get("display", "").lower():
                matches.append(f"  {name} ({t.get('display', name)})")
        if not matches:
            return ToolResult.ok(content=f"No tools matching {query!r}. Use '*' to list all. Total: {reg.tool_count}")
        return ToolResult.ok(content=f"Tools matching {query!r}:\n" + "\n".join(matches[:20]))
