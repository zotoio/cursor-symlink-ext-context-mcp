---
name: context-search
description: Search shared CORE and installed extension context through the core-context MCP server.
---

# /context-search

Use this command for a question that may be answered by shared CORE context or an
installed extension's `CONTEXT/` files.

1. Call `context_status`. If `core-context` is unavailable, check that the
   Docker service is healthy with `./installer/context_mcp.sh status`, then
   confirm its user-level `~/.cursor/mcp.json` registration is enabled in
   Cursor; do not guess from stale context.
2. Call `context_search` with the user's question. Use `source` only when the
   user names a concrete source such as `CORE`, `PRODUCT`, `QA`, or `SUPPORT`.
3. If the MCP client offers optional focus for closely ranked, multi-source
   results, select the source and/or topic that best matches the question.
   If no focus is chosen or elicitation is unavailable, use the original
   ranking.
4. Cite the result's source, title, and snippet. When a full document is
   needed, call `context_read` with the exact path returned by the search.
5. If no result answers the question, say so and continue with repository
   investigation only when it is relevant.
