#!/usr/bin/env python3
"""
MCP-over-SSE HTTP wrapper for agent-memory-hub
Exposes the stdio MCP server as Server-Sent Events endpoint for mobile clients
"""
import asyncio
import json
import os
import sys
from typing import AsyncIterator

# Add scripts to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))

try:
    from fastapi import FastAPI, Request
    from fastapi.responses import StreamingResponse
    from fastapi.middleware.cors import CORSMiddleware
except ImportError:
    print("Installing fastapi and uvicorn...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "fastapi", "uvicorn[standard]"])
    from fastapi import FastAPI, Request
    from fastapi.responses import StreamingResponse
    from fastapi.middleware.cors import CORSMiddleware

import memory_client as mc

app = FastAPI(title="agent-memory-hub MCP Server")

# CORS for mobile clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "agent-memory-hub", "version": "1.0.0"}

TOOLS = [
    {
        "name": "recall_relevant",
        "description": "Search semantic/hybrid memory from past sessions relevant to current task.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What you're trying to do/remember"},
                "project": {"type": "string", "description": "Filter by project (optional)"},
                "limit": {"type": "integer", "description": "Max sessions (default 8)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "recent_sessions",
        "description": "List most recent sessions (cross-project)",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "How many (default 10)"}},
        },
    },
    {
        "name": "get_facts",
        "description": "Get persistent facts (user preferences, project patterns)",
        "inputSchema": {
            "type": "object",
            "properties": {"project": {"type": "string", "description": "Filter by project (optional)"}},
        },
    },
    {
        "name": "get_session",
        "description": "Get full content of a specific session",
        "inputSchema": {
            "type": "object",
            "properties": {"session_id": {"type": "string", "description": "Session ID or prefix"}},
            "required": ["session_id"],
        },
    },
]


def handle_tool_call(name: str, arguments: dict) -> dict:
    """Execute MCP tool and return result"""
    try:
        if name == "recall_relevant":
            query = arguments.get("query", "")
            project = arguments.get("project")
            limit = arguments.get("limit", 8)
            results = mc.recall(query, project, limit)
            return {"content": [{"type": "text", "text": json.dumps(results, ensure_ascii=False, indent=2)}]}
        
        elif name == "recent_sessions":
            limit = arguments.get("limit", 10)
            results = mc.recent(limit)
            return {"content": [{"type": "text", "text": json.dumps(results, ensure_ascii=False, indent=2)}]}
        
        elif name == "get_facts":
            project = arguments.get("project")
            results = mc.facts(project)
            return {"content": [{"type": "text", "text": json.dumps(results, ensure_ascii=False, indent=2)}]}
        
        elif name == "get_session":
            session_id = arguments.get("session_id", "")
            result = mc.session(session_id)
            if result:
                return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]}
            else:
                return {"content": [{"type": "text", "text": "Session not found"}], "isError": True}
        
        else:
            return {"content": [{"type": "text", "text": f"Unknown tool: {name}"}], "isError": True}
    
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error: {str(e)}"}], "isError": True}


async def sse_generator(request_data: dict) -> AsyncIterator[str]:
    """Generate SSE events for MCP protocol"""
    method = request_data.get("method")
    
    if method == "initialize":
        response = {
            "jsonrpc": "2.0",
            "id": request_data.get("id"),
            "r