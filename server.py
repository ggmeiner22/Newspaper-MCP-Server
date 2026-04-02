"""
MCP server for a small online newspaper called Campus Ledger.

What this server can do
- create articles
- list and fetch articles
- post comments
- list comments for an article
- seed a demo article
- run a local demo that simulates an LLM agent generating a neutral election-policy comment

Why this design matches MCP
- MCP servers expose tools, resources, and prompts to clients.
- FastMCP uses Python type hints and docstrings to generate tool definitions.
- MCP supports stdio and Streamable HTTP transports, with stdio generally recommended
  for local clients and Streamable HTTP for multi-client/networked setups.

Docs used
- Build an MCP server: https://modelcontextprotocol.io/docs/develop/build-server
- MCP Python SDK: https://modelcontextprotocol.github.io/python-sdk/
- Tools concept: https://modelcontextprotocol.io/specification/2025-06-18/server/tools
- Transport guidance: https://modelcontextprotocol.io/specification/2025-06-18/basic/transports
- MCP Inspector: https://modelcontextprotocol.io/docs/tools/inspector

Install
    uv venv
    source .venv/bin/activate          # Windows: .venv\\Scripts\\activate
    uv add "mcp[cli]"

Run as an MCP server over stdio
    python newspaper_mcp_server.py

Run as an MCP server over HTTP
    python newspaper_mcp_server.py --http --port 8000

Inspect/test it
    npx -y @modelcontextprotocol/inspector
    # Then connect to http://localhost:8000/mcp in HTTP mode

Run the built-in demo that shows an "LLM agent" generating a neutral policy comment
    python newspaper_mcp_server.py --demo

Notes
- The demo comment is intentionally neutral: it supports a policy idea without endorsing a
  candidate.
- The built-in agent function is deterministic so the file works out of the box. A placeholder
  is included showing where you would plug in a real LLM call.
"""

from __future__ import annotations

import argparse
import html
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from mcp.server.fastmcp import FastMCP

APP_NAME = "campus-ledger"
DB_PATH = Path("campus_ledger.db")

# json_response=True makes the tool responses easier for many clients to consume.
mcp = FastMCP(APP_NAME, json_response=True)


@contextmanager
def get_db() -> Iterator[sqlite3.Connection]:
    """Open a SQLite connection and commit automatically."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def utc_now_iso() -> str:
    """Return a compact UTC timestamp string."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def init_db() -> None:
    """Create the database tables if they do not already exist."""
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
    """Trim, validate length, and escape HTML for safe display/storage."""
    text = text.strip()
    if not text:
        raise ValueError("Text cannot be empty.")
    if len(text) > max_len:
        raise ValueError(f"Text is too long. Max length is {max_len} characters.")
    return html.escape(text)


@mcp.tool()
def create_article(title: str, author: str, body: str) -> dict:
    """Create a new article in the Campus Ledger database."""
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
    """Get one article by ID."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, title, author, body, created_at FROM articles WHERE id = ?",
            (article_id,),
        ).fetchone()
    return dict(row) if row else None


@mcp.tool()
def post_comment(article_id: int, author: str, body: str) -> dict:
    """Post a comment on an existing article."""
    author = clean_text(author, max_len=80)
    body = clean_text(body, max_len=5000)

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
def list_comments(article_id: int, limit: int = 50) -> list[dict]:
    """List recent comments for an article."""
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
    """Create a sample article so the server can be tested quickly."""
    return create_article(
        title="Education and Workforce Priorities Ahead of 2028",
        author="Campus Ledger Editorial Desk",
        body=(
            "As the next U.S. presidential election approaches, voters are comparing policy ideas on "
            "education, workforce training, and affordability. This article asks what kinds of "
            "programs could help students and early-career workers most."
        ),
    )


@mcp.tool()
def generate_neutral_comment(article_id: int) -> dict:
    """Generate one neutral policy-focused comment for an article without posting it."""
    article = get_article(article_id)
    if article is None:
        return {"ok": False, "error": f"Article {article_id} does not exist."}

    comment_text = generate_neutral_comment_llm(article)
    return {
        "ok": True,
        "article_id": article_id,
        "generated_comment": comment_text,
    }


@mcp.tool()
def generate_and_post_neutral_comment(article_id: int, author: str = "LLM-Agent") -> dict:
    """Generate a neutral policy-focused comment for an article and post it."""
    article = get_article(article_id)
    if article is None:
        return {"ok": False, "error": f"Article {article_id} does not exist."}

    comment_text = generate_neutral_comment_llm(article)
    post_result = post_comment(article_id=article_id, author=author, body=comment_text)

    return {
        "ok": post_result.get("ok", False),
        "article_id": article_id,
        "author": author,
        "generated_comment": comment_text,
        "post_result": post_result,
    }


@mcp.prompt()
def neutral_policy_comment_prompt(article_title: str, article_body: str) -> str:
    """Prompt template for generating a neutral policy-focused newspaper comment."""
    return (
        "Write one short newspaper comment in a respectful, neutral tone. "
        "Support a policy idea discussed in the article without endorsing any candidate or party. "
        "Avoid slogans, campaign language, insults, or fundraising language. "
        "Keep it under 90 words.\n\n"
        f"Title: {article_title}\n"
        f"Article: {article_body}"
    )


# -----------------------------
# Demo agent helpers
# -----------------------------

def generate_neutral_comment_local(article: dict) -> str:
    """
    Backward-compatible local fallback if no external LLM is configured.
    """
    title = html.unescape(article["title"])
    body = html.unescape(article["body"])

    text = f"{title} {body}".lower()
    if "education" in text or "training" in text or "students" in text:
        return (
            "I support stronger workforce training and more affordable education options. "
            "Policies that expand skills programs, internships, and practical pathways into jobs "
            "could help students and early-career workers without turning every issue into a campaign talking point."
        )
    if "health" in text:
        return (
            "A practical focus on access, cost, and preventive care seems like a constructive direction. "
            "Clear policy details matter more than slogans when people are comparing proposals."
        )
    return (
        "I appreciate the policy focus here. Concrete proposals, measurable outcomes, and respectful debate "
        "would help voters compare ideas more thoughtfully."
    )


def generate_neutral_comment_llm(article: dict) -> str:
    import ollama

    title = article["title"]
    body = article["body"]

    prompt = f"""
    Write one short neutral newspaper comment.

    - Support a policy idea in the article
    - DO NOT mention any candidate or political party
    - Keep it under 80 words
    - Be professional and neutral tone

    Article Title: {title}
    Article Body: {body}
    """

    response = ollama.chat(
        model="llama3",
        messages=[{"role": "user", "content": prompt}]
    )

    return response["message"]["content"]


def demo_run() -> None:
    """Demonstrate creating an article, generating a neutral comment, and posting it."""
    print("=== Campus Ledger MCP Demo ===")
    init_db()

    seed = seed_demo_article()
    article_id = seed["article_id"]
    article = get_article(article_id)
    assert article is not None

    print("Created article:")
    print(article)
    print()

    comment_text = generate_neutral_comment_llm(article)
    print("Agent-generated neutral comment:")
    print(comment_text)
    print()

    result = post_comment(article_id=article_id, author="LLM-Agent", body=comment_text)
    print("Post result:")
    print(result)
    print()

    comments = list_comments(article_id=article_id)
    print("Comments now stored for that article:")
    for c in comments:
        print(c)


# -----------------------------
# Main entry point
# -----------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Campus Ledger MCP server or demo.")
    parser.add_argument("--http", action="store_true", help="Run with Streamable HTTP transport.")
    parser.add_argument("--port", type=int, default=8000, help="Port for HTTP mode.")
    parser.add_argument("--demo", action="store_true", help="Run the local article/comment demo.")
    args = parser.parse_args()

    init_db()

    if args.demo:
        demo_run()
        return

    if args.http:
        # In many examples, Streamable HTTP servers are exposed at /mcp by the SDK.
        # For network use, add origin validation/authentication as appropriate.
        mcp.settings.port = args.port
        mcp.run(transport="streamable-http")
    else:
        # Stdio is the common local transport for MCP clients.
        mcp.run()


if __name__ == "__main__":
    main()


# -----------------------------
# NEW MCP AGENT TOOLS (added)
# -----------------------------

@mcp.tool()
def generate_neutral_comment(article_id: int) -> dict:
    """Generate one neutral policy-focused comment for an article without posting it."""
    article = get_article(article_id)
    if article is None:
        return {"ok": False, "error": f"Article {article_id} does not exist."}

    comment_text = generate_neutral_comment_llm(article)
    return {
        "ok": True,
        "article_id": article_id,
        "generated_comment": comment_text,
    }


@mcp.tool()
def generate_and_post_neutral_comment(article_id: int, author: str = "LLM-Agent") -> dict:
    """Generate a neutral policy-focused comment for an article and post it."""
    article = get_article(article_id)
    if article is None:
        return {"ok": False, "error": f"Article {article_id} does not exist."}

    comment_text = generate_neutral_comment_llm(article)
    post_result = post_comment(article_id=article_id, author=author, body=comment_text)

    return {
        "ok": post_result.get("ok", False),
        "article_id": article_id,
        "author": author,
        "generated_comment": comment_text,
        "post_result": post_result,
    }
