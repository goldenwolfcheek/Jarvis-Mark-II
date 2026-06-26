"""
Jarvis Mark II — Web tools.
Web search, fetch, and content extraction tools for agent function calling.

Category: web

All functions are registered by calling ``load_web_tools()``.
"""

import asyncio
import json
import re
import warnings
from typing import Optional
from urllib.parse import parse_qs, urlparse

from .registry import get_tool_registry

# ═══════════════════════════════════════════════════════════════════════════
# Constants / shared helpers
# ═══════════════════════════════════════════════════════════════════════════

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)
_HTTP_TIMEOUT = 30.0


def _truncate(text: str, max_chars: int = 50000) -> str:
    """Truncate text cleanly, appending a truncation notice."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...[TRUNCATED]"


# ═══════════════════════════════════════════════════════════════════════════
# Internal HTTP helpers
# ═══════════════════════════════════════════════════════════════════════════


async def _fetch_url(url: str, timeout: float = _HTTP_TIMEOUT) -> tuple[int, str, dict]:
    """Fetch a URL and return ``(status_code, body_text, headers_dict)``.

    Uses ``httpx`` (hard dependency — no fallback needed).
    """
    # httpx (primary — hard dependency)
    import httpx

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        resp = await client.get(url, headers={"User-Agent": _USER_AGENT})
        return resp.status_code, resp.text, dict(resp.headers)


def _extract_text(html: str, use_readability: bool = True) -> str:
    """Extract readable text from HTML.

    1.  If *use_readability* is ``True`` (default), tries ``readability-lxml``
        for article-level extraction.
    2.  Falls back to BeautifulSoup with ``lxml``, stripping script/style tags.
    3.  Last resort: simple regex tag-stripping.
    """
    if use_readability:
        try:
            from readability import Document
            from bs4 import BeautifulSoup

            doc = Document(html)
            html_content = doc.summary()
            soup = BeautifulSoup(html_content, "lxml")
            text = soup.get_text(separator="\n", strip=True)
            if len(text) > 50:  # only accept if readability found real content
                return text
        except ImportError:
            pass

    # BeautifulSoup fallback
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        text = re.sub(r"\n{3,}", "\n\n", text)
        if text.strip():
            return text
    except ImportError:
        pass

    # Regex fallback
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_title(html: str) -> str:
    """Extract the page title from HTML."""
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        tag = soup.find("title")
        if tag:
            return tag.get_text(strip=True)
    except ImportError:
        pass
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else ""


def _normalise_url(url: str) -> str:
    """Prepend ``https://`` if no scheme is present."""
    if not url.startswith(("http://", "https://")):
        return "https://" + url
    return url


# ═══════════════════════════════════════════════════════════════════════════
# web_search
# ═══════════════════════════════════════════════════════════════════════════


async def _tool_web_search(query: str, max_results: int = 5) -> str:
    """Search the web using DuckDuckGo and return results with titles, snippets, and URLs.

    Args:
        query: The search query string.
        max_results: Maximum number of search results to return (default: 5, max: 20).
    """
    max_results = min(max(1, max_results), 20)

    # ── Primary: duckduckgo_search library ─────────────────────────────
    try:
        from duckduckgo_search import DDGS

        def _search() -> list[dict]:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=RuntimeWarning)
                with DDGS() as ddgs:
                    return ddgs.text(query, max_results=max_results)

        results = await asyncio.to_thread(_search)
        if results:
            return json.dumps({
                "query": query,
                "results": [
                    {
                        "title": r.get("title", ""),
                        "snippet": r.get("body", ""),
                        "url": r.get("href", ""),
                    }
                    for r in results
                ],
                "count": len(results),
                "source": "duckduckgo_search",
            })
    except ImportError:
        pass
    except Exception:
        pass

    # ── Fallback: scrape DuckDuckGo Lite HTML ──────────────────────────
    try:
        import httpx

        search_url = f"https://lite.duckduckgo.com/lite/?q={query}"
        resp = await _fetch_url(search_url, timeout=15.0)
        status_code, html = resp[0], resp[1]

        if status_code == 200:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html, "lxml")

            def _clean_ddg_url(raw: str | None) -> str:
                """Extract the real URL from a DuckDuckGo redirect link."""
                if not raw:
                    return ""
                # Handle relative redirect URLs
                if raw.startswith("//"):
                    raw = "https:" + raw
                parsed = urlparse(raw)
                if "duckduckgo.com" in parsed.netloc and parsed.path in ("/l/", "/y.js"):
                    qs = parse_qs(parsed.query)
                    if "uddg" in qs:
                        return qs["uddg"][0]
                return raw

            results: list[dict] = []

            # DuckDuckGo Lite places result links in <a class="result-link">
            for link in soup.select("a.result-link")[:max_results]:
                results.append({
                    "title": link.get_text(strip=True),
                    "url": _clean_ddg_url(link.get("href")),
                    "snippet": "",
                })

            # Match snippets by position
            snippets = soup.select("td.result-snippet")
            for i, snip in enumerate(snippets[:max_results]):
                if i < len(results):
                    results[i]["snippet"] = snip.get_text(strip=True)

            if results:
                return json.dumps({
                    "query": query,
                    "results": results,
                    "count": len(results),
                    "source": "duckduckgo_lite_fallback",
                })
    except Exception:
        pass

    # ── No backend available ───────────────────────────────────────────
    return json.dumps({
        "error": (
            "Web search is unavailable. "
            "Install the 'duckduckgo_search' package or check network connectivity."
        ),
        "query": query,
        "results": [],
        "count": 0,
    })


# ═══════════════════════════════════════════════════════════════════════════
# web_fetch
# ═══════════════════════════════════════════════════════════════════════════


async def _tool_web_fetch(url: str) -> str:
    """Fetch the raw content of a URL and return the full response body text.

    Args:
        url: The URL to fetch (scheme optional — ``https://`` is assumed if omitted).
    """
    url = _normalise_url(url)
    try:
        status_code, content, headers = await _fetch_url(url)
        return json.dumps({
            "url": url,
            "status_code": status_code,
            "content": _truncate(content),
            "content_length": len(content),
            "content_type": headers.get("content-type", "unknown"),
        })
    except Exception as e:
        return json.dumps({"error": str(e), "url": url})


# ═══════════════════════════════════════════════════════════════════════════
# web_scrape
# ═══════════════════════════════════════════════════════════════════════════


async def _tool_web_scrape(url: str, use_readability: bool = True) -> str:
    """Fetch a URL and extract its main readable content (pure text).

    Uses ``readability-lxml`` when available (default on), with BeautifulSoup
    fallback.  Navigation, sidebars, footers and other non-content elements
    are stripped automatically.

    Args:
        url: The URL to scrape (scheme optional).
        use_readability: Whether to use readability-lxml for article extraction
                         (default: ``True``).
    """
    url = _normalise_url(url)
    try:
        status_code, html, headers = await _fetch_url(url)
        if status_code >= 400:
            return json.dumps({
                "error": f"HTTP {status_code}",
                "url": url,
                "status_code": status_code,
            })

        title = _extract_title(html)
        text = _extract_text(html, use_readability=use_readability)

        return json.dumps({
            "url": url,
            "status_code": status_code,
            "title": title,
            "content": _truncate(text),
            "content_length": len(text),
            "source": "readability" if use_readability else "bs4_fallback",
        })
    except Exception as e:
        return json.dumps({"error": str(e), "url": url})


# ═══════════════════════════════════════════════════════════════════════════
# Loader
# ═══════════════════════════════════════════════════════════════════════════


def load_web_tools():
    """Register all web tools into the global tool registry."""
    registry = get_tool_registry()

    registry.register_fn(
        _tool_web_search,
        name="web_search",
        category="web",
        description=(
            "Search the web using DuckDuckGo and return results with titles, "
            "snippets, and URLs."
        ),
    )
    registry.register_fn(
        _tool_web_fetch,
        name="web_fetch",
        category="web",
        description=(
            "Fetch the raw content of a URL and return the full response body text. "
            "Returns status code, headers, and body."
        ),
    )
    registry.register_fn(
        _tool_web_scrape,
        name="web_scrape",
        category="web",
        description=(
            "Fetch a URL and extract its main readable content (pure text), "
            "stripping navigation, sidebars, footers, and other non-content elements. "
            "Uses readability-lxml when available, with BeautifulSoup fallback."
        ),
    )
