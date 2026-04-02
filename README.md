# Newspaper-MCP-Server

## PART 1 — Setup
1. Install Python packages
```pip install "mcp[cli]" ollama```
2. Install & run Ollama
Install (if not already):

https://ollama.com

Pull model:
```ollama pull llama3```
3️⃣ Start Ollama
```ollama run llama3```

Leave this running (or background it)

## PART 2 — Start your MCP server
Go to your project folder
```cd Newspaper-MCP-Server```
Run server (HTTP mode)
```python3 server.py --http --port 8000```

> Leave this running

## PART 3 — Open MCP Inspector (client)
In a NEW terminal:
```npx -y @modelcontextprotocol/inspector```

> Opens browser UI

## PART 4 — Connect to your server

In Inspector:

Transport Type: HTTP
URL: http://127.0.0.1:8000/mcp
Connect Via Proxy

> Click Connect

## PART 5 — Run your demo (THIS is the important part)
1. Create article

Click: seed_demo_article
Click: Run Tool

2. LLM generates + posts comment

Click: generate_and_post_neutral_comment

Use:

{
  "article_id": 1,
  "author": "LLM-Agent"
}

Click: Run Tool

This step:
(a) calls Ollama
(b) generates comment
(c) posts it automatically

3. Show result

Click: list_comments

Use:
{
  "article_id": 1
}

Click: Run Tool

You’ll see the generated comment