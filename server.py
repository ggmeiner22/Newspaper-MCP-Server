"""
Minimal MCP server for a demo online newspaper.

What it does
- Creates articles
- Posts comments on articles
- Lists articles and comments
- Uses SQLite for persistence
- Exposes everything as MCP tools via FastMCP

Why this version is safe
- It is intended for a class demo, a mock newspaper, or your own site
- It does not automate political persuasion or coordinated advocacy posting

References used while building this
- Official MCP docs show FastMCP as the server entry point and note that type hints
  and docstrings become tool definitions.
- Official Python SDK docs show MCP servers can expose tools/resources/prompts and
  can run over transports like stdio or streamable HTTP.

Run
1) uv venv
2) source .venv/bin/activate        # Windows: .venv\\Scripts\\activate
3) uv add "mcp[cli]"
4) python newspaper_mcp_server.py   # stdio mode for local MCP clients
   or
   python newspaper_mcp_server.py --http --port 8000

Quick test with the MCP inspector
- npx -y @modelcontextprotocol/inspector
- Connect to http://localhost:8000/mcp if using --http

Example safe demo flow in an MCP client
- create_article(title="Campus Recycling Drive", author="Garrett", body="...")
- post_comment(article_id=1, author="Student1", body="Glad to see this happening.")
- list_articles()
- list_comments(article_id=1)
"""

from __future__ import annotations

import argparse
import html
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from mcp.server.fastmcp import FastMCP

APP_NAME = "newspaper-mcp"
DB_PATH = Path("newspaper.db")

mcp = FastMCP(APP_NAME)


@dataclass
class Article:
    id: int
    title: str
    author: str
    body: str
    created_at: str


@dataclass
class Comment:
    id: int
    article_id: int
    author: str
    body: str
    created_at: str


@contextmanager
def get_db() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def init_db() -> None:
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                author TEXT NOT NULL,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id INTEGER NOT NULL,
                author TEXT NOT NULL,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(article_id) REFERENCES articles(id)
            )
            """
        )


def clean_text(text: str, *, max_len: int) -> str:
    text = text.strip()
    if not text:
        raise ValueError("Text cannot be empty.")
    if len(text) > max_len:
        raise ValueError(f"Text is too long. Max length is {max_len} characters.")
    return html.escape(text)


POLITICAL_PERSUASION_HINTS = {
    "vote for",
    "support candidate",
    "elect",
    "campaign for",
    "donate to",
    "persuade voters",
    "convince people",
    "endorse",
}


def looks_like_political_persuasion(text: str) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in POLITICAL_PERSUASION_HINTS)


@mcp.tool()
def create_article(title: str, author: str, body: str) -> dict:
    """Create a new article in the newspaper database."""
    title = clean_text(title, max_len=200)
    author = clean_text(author, max_len=80)
    body = clean_text(body, max_len=20000)

    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO articles (title, author, body, created_at) VALUES (?, ?, ?, ?)",
            (title, author, body, utc_now_iso()),
        )
        article_id = int(cur.lastrowid)

    return {
        "ok": True,
        "article_id": article_id,
        "message": f"Article {article_id} created.",
    }


@mcp.tool()
def post_comment(article_id: int, author: str, body: str) -> dict:
    """Post a comment on an existing article."""
    author = clean_text(author, max_len=80)
    raw_body = body.strip()
    body = clean_text(body, max_len=5000)

    if looks_like_political_persuasion(raw_body):
        return {
            "ok": False,
            "error": "This demo server is configured not to post partisan political persuasion.",
        }

    with get_db() as conn:
        row = conn.execute("SELECT id FROM articles WHERE id = ?", (article_id,)).fetchone()
        if row is None:
            return {"ok": False, "error": f"Article {article_id} does not exist."}

        cur = conn.execute(
            "INSERT INTO comments (article_id, author, body, created_at) VALUES (?, ?, ?, ?)",
            (article_id, author, body, utc_now_iso()),
        )
        comment_id = int(cur.lastrowid)

    return {
        "ok": True,
        "comment_id": comment_id,
        "message": f"Comment {comment_id} posted on article {article_id}.",
    }


@mcp.tool()
def list_articles(limit: int = 20) -> list[dict]:
    """List recent articles."""
    limit = max(1, min(limit, 100))
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, title, author, body, created_at FROM articles ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()

    return [dict(row) for row in rows]


@mcp.tool()
def get_article(article_id: int) -> Optional[dict]:
    """Get one article by id."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, title, author, body, created_at FROM articles WHERE id = ?",
            (article_id,),
        ).fetchone()
    return dict(row) if row else None


@mcp.tool()
def list_comments(article_id: int, limit: int = 50) -> list[dict]:
    """List recent comments for one article."""
    limit = max(1, min(limit, 200))
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, article_id, author, body, created_at
            FROM comments
            WHERE article_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (article_id, limit),
        ).fetchall()

    return [dict(row) for row in rows]


@mcp.tool()
def seed_demo_article() -> dict:
    """Create one sample article so the server can be tested quickly."""
    return create_article(
        title="Welcome to Campus Ledger",
        author="Editor",
        body=(
            "Campus Ledger is a demo newspaper used for testing article and comment posting "
            "through an MCP server."
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the newspaper MCP server.")
    parser.add_argument("--http", action="store_true", help="Run with streamable HTTP transport.")
    parser.add_argument("--port", type=int, default=8000, help="Port for HTTP mode.")
    args = parser.parse_args()

    init_db()

    if args.http:
        # FastMCP's run() accepts transport selection. This mirrors the official quickstart pattern.
        mcp.settings.port = args.port
        mcp.run(transport="streamable-http")
    else:
        mcp.run()


if __name__ == "__main__":
    main()
