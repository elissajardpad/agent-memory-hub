#!/usr/bin/env python3
"""MCP HTTP server for agent memory hub"""
import json
import sys
import os
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

# Add scripts to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))
import memory_client as mc

# Debug: print env vars
print(f"[DEBUG] SUPABASE_URL: {mc.URL}")
print(f"[DEBUG] PUBKEY exists: {bool(mc.PUBKEY)}")
print(f"[DEBUG] PUBKEY prefix: {mc.PUBKEY[:20] if mc.PUBKEY else 'NONE'}...")

PORT = int(os.getenv('PORT', 8080))

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

def handle_tool_call(name: str, arguments: dict):
    """Handle MCP tool calls"""
    try:
        if name == "recall_relevant":
            query = arguments.get("query", "")
            project = arguments.get("project")
            limit = arguments.get("limit", 5)
            
            # Search facts table using text search
            query_encoded = urllib.parse.quote(f"%{query}%")
            search_query = f"facts?fact=ilike.{query_encoded}&limit={limit}"
            if project:
                search_query += f"&scope=eq.{project}"
            
            # Debug: return raw query and results
            try:
                results = mc.rest(search_query)
                debug_info = {
                    "query_string": search_query,
                    "results_count": len(results),
                    "raw_results": results[:2] if results else [],  # 只返回前2条
                    "supabase_url": mc.URL,
                    "has_pubkey": bool(mc.PUBKEY)
                }
                
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(debug_info, ensure_ascii=False, indent=2)
                        }
                    ]
                }
            except Exception as e:
                return {
                    "content": [{"type": "text", "text": f"Error: {str(e)}"}],
                    "isError": True
                }
        
        elif name == "recent_sessions":
            limit = arguments.get("limit", 10)
            results = mc.rest(f"sessions?select=*&order=created_at.desc&limit={limit}")
            
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(results, ensure_ascii=False, indent=2)
                    }
                ]
            }
        
        else:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Unknown tool: {name}"
                    }
                ],
                "isError": True
            }
    
    except Exception as e:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Error: {str(e)}"
                }
            ],
            "isError": True
        }

class MCPHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != '/mcp':
            self.send_error(404)
            return
        
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8')
        
        try:
            req = json.loads(body)
            method = req.get('method')
            
            if method == 'tools/list':
                response = {
                    "jsonrpc": "2.0",
                    "id": req.get('id'),
                    "result": {"tools": TOOLS}
                }
            
            elif method == 'tools/call':
                params = req.get('params', {})
                name = params.get('name')
                arguments = params.get('arguments', {})
                
                result = handle_tool_call(name, arguments)
                
                response = {
                    "jsonrpc": "2.0",
                    "id": req.get('id'),
                    "result": result
                }
            
            else:
                response = {
                    "jsonrpc": "2.0",
                    "id": req.get('id'),
                    "error": {"code": -32601, "message": f"Method not found: {method}"}
                }
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode('utf-8'))
        
        except Exception as e:
            self.send_error(400, str(e))
    
    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "healthy"}).encode('utf-8'))
        else:
            self.send_error(404)

if __name__ == '__main__':
    server = HTTPServer(('0.0.0.0', PORT), MCPHandler)
    print(f"MCP server listening on port {PORT}")
    server.serve_forever()