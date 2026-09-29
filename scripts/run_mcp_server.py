"""
Start the Transformation Rules MCP server (stdio).

Prerequisites:
  1. .venv activated
  2. uvicorn main:app --reload   (API on TRANSFORMATION_API_BASE_URL)

Usage:
  python scripts/run_mcp_server.py
  # or: python -m mcp_server
"""

from mcp_server.server import main

if __name__ == "__main__":
    main()
