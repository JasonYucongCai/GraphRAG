"""
agent_a1_tools.web_tools — Web operations (3 tools)

web_search, fetch_webpage, download_arxiv
"""
from __future__ import annotations
import json, urllib.request, urllib.error
from typing import Any
from .tool_base import WebTool, ReadOnlyTool, ToolContext, ToolResult


class WebSearchTool(ReadOnlyTool):
    tool_name = "web_search"
    category = "web"
    description = "Search the web (placeholder — requires API key configuration)."
    tool_schema = {
        "type": "object", "required": ["query"],
        "properties": {
            "query": {"type": "string", "description": "Search query."},
        },
    }
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        query = args.get("query", "")
        return ToolResult.success(
            f"Web search not configured. Query: {query[:200]}",
            query=query)


class FetchWebpageTool(WebTool):
    tool_name = "fetch_webpage"
    category = "web"
    description = "Fetch and extract text content from a URL."
    tool_schema = {
        "type": "object", "required": ["url"],
        "properties": {
            "url": {"type": "string", "description": "URL to fetch."},
        },
    }
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        url = args.get("url", "")
        if not url:
            return ToolResult.fail("url is required")
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "agent_a1/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                content = resp.read().decode("utf-8", errors="replace")
                # Basic HTML stripping
                import re
                text = re.sub(r"<[^>]+>", " ", content)
                text = re.sub(r"\s+", " ", text)
                return ToolResult.success(
                    text[:3000], url=url, content_length=len(content))
        except urllib.error.URLError as e:
            return ToolResult.fail(f"Fetch failed: {e}")
        except Exception as e:
            return ToolResult.fail(str(e))


class DownloadArxivTool(WebTool):
    tool_name = "download_arxiv"
    category = "web"
    description = "Download paper metadata from arXiv by ID."
    tool_schema = {
        "type": "object", "required": ["arxiv_id"],
        "properties": {
            "arxiv_id": {"type": "string", "description": "arXiv ID (e.g., '2301.12345')."},
        },
    }
    def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        arxiv_id = args.get("arxiv_id", "")
        if not arxiv_id:
            return ToolResult.fail("arxiv_id is required")
        try:
            api_url = f"http://export.arxiv.org/api/query?id_list={arxiv_id}"
            req = urllib.request.Request(api_url)
            with urllib.request.urlopen(req, timeout=15) as resp:
                content = resp.read().decode("utf-8", errors="replace")
                return ToolResult.success(content[:3000], arxiv_id=arxiv_id)
        except Exception as e:
            return ToolResult.fail(str(e))


def register_web_tools(toolkit) -> None:
    toolkit.register_many([
        WebSearchTool(), FetchWebpageTool(), DownloadArxivTool(),
    ])
