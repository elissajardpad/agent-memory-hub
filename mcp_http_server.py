#!/usr/bin/env python3
import asyncio
import json
import os
import sys
from typing import AsyncIterator

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))

try:
    from fastapi import FastAPI, Request
    from fastapi.responses import StreamingResponse
    from fastapi.middleware.cors import CORSMiddleware
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "fastapi", "uvicorn[standard]"])
    from fastapi import FastAPI, Request
    from fastapi.responses import StreamingResponse
    from fastapi.middleware.cors import CORSMiddleware

import memory_client as mc

app = FastAPI(title="agent-memory-hub MCP Server")

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
        "description": "Search memory from past sessions",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "project": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "recent_sessions",
        "description": "List recent sessions",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer"}},
        },
    },
]


def handle_tool_call(name: str, arguments: dict) -> dict:
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
        else:
            return {"content": [{"type": "text", "text": f"Unknown tool: {name}"}], "isError": True}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error: {str(e)}"}], "isError": True}


async def sse_generator(request_data: dict) -> AsyncIterator[str]:
    method = request_data.get("method")
    req_id = request_data.get("id")
    
    if method == "initialize":
        response = {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "serverInfo": SERVER_INFO,
                "capabilities": {"tools": {}},
            }
        }
        yield f"data: {json.dumps(response)}\n\n"
    
    elif method == "tools/list":
        response = {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": TOOLS}
        }
        yield f"data: {json.dumps(response)}\n\n"
    
    elif method == "tools/call":
        params = request_data.get("params", {})
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        result = handle_tool_call(tool_name, arguments)
        response = {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": result
        }
        yield f"data: {json.dumps(response)}\n\n"
    
    else:
        error_response = {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"}
        }
        yield f"data: {json.dumps(error_response)}\n\n"


@app.get("/")
async def root():
    return {"service": "agent-memory-hub", "status": "running"}


@app.get("/health")
async def health():
    try:
        mc.rest("sessions?select=session_id&limit=1")
        return {"status": "healthy"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


@app.post("/sse")
async def sse_endpoint(request: Request):
    try:
        body = await request.json()
        return StreamingResponse(
            sse_generator(body),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)