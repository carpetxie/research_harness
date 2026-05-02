#!/usr/bin/env python3
"""
Web search tool using the xAI Grok API.

Agents call this via Bash to find research papers and related work.

Usage:
    python src/tools/web_search.py "your search query"
    python src/tools/web_search.py "your query" --num-results 10
    python src/tools/web_search.py "your query" --format json

Output:
    Plain text by default (readable by agents inline).
    JSON with --format json (for programmatic parsing).

Requirements:
    XAI_API_KEY must be set in .env
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def load_api_key() -> str:
    # Try env first, then .env file
    key = os.environ.get("XAI_API_KEY", "")
    if key:
        return key

    # Walk up from this file to find .env
    search = Path(__file__).parent
    for _ in range(5):
        candidate = search / ".env"
        if candidate.exists():
            for line in candidate.read_text().splitlines():
                line = line.strip()
                if line.startswith("XAI_API_KEY"):
                    _, _, val = line.partition("=")
                    return val.strip().strip('"').strip("'")
        search = search.parent

    return ""


def search(query: str, num_results: int = 5) -> dict:
    """
    Call the xAI Grok API with live search enabled.
    Returns a dict with 'results' (list) and 'raw_response' (str).
    """
    import urllib.request
    import urllib.error

    api_key = load_api_key()
    if not api_key:
        return {
            "error": "XAI_API_KEY not found. Set it in .env or as an environment variable.",
            "results": [],
        }

    payload = json.dumps({
        "model": "grok-3",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a research assistant. When given a search query, "
                    "find the most relevant academic papers, preprints, and research. "
                    "For each result include: title, authors, year, venue/journal, "
                    "a 2-sentence summary of the key finding, and URL if available. "
                    f"Return exactly {num_results} results, numbered."
                ),
            },
            {
                "role": "user",
                "content": f"Search for: {query}",
            },
        ],
        "search_parameters": {
            "mode": "auto",
        },
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.x.ai/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        return {
            "error": f"HTTP {e.code}: {error_body}",
            "results": [],
        }
    except Exception as e:
        return {
            "error": str(e),
            "results": [],
        }

    content = body.get("choices", [{}])[0].get("message", {}).get("content", "")
    citations = body.get("citations", [])

    return {
        "query": query,
        "raw_response": content,
        "citations": citations,
        "results": [],  # parsed from raw_response by the agent
    }


def format_text(result: dict) -> str:
    if "error" in result:
        return f"ERROR: {result['error']}"
    lines = [f"Search: {result.get('query', '')}", ""]
    lines.append(result.get("raw_response", "(no response)"))
    if result.get("citations"):
        lines.append("\nSource URLs:")
        for url in result["citations"]:
            lines.append(f"  {url}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Search for research papers using xAI Grok."
    )
    parser.add_argument("query", help="Search query")
    parser.add_argument(
        "--num-results", type=int, default=5,
        help="Number of results to return (default: 5)"
    )
    parser.add_argument(
        "--format", choices=["text", "json"], default="text",
        help="Output format (default: text)"
    )
    args = parser.parse_args()

    result = search(args.query, num_results=args.num_results)

    if args.format == "json":
        print(json.dumps(result, indent=2))
    else:
        print(format_text(result))

    if "error" in result:
        sys.exit(1)


if __name__ == "__main__":
    main()
