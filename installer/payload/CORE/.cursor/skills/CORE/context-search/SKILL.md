---
name: context-search
description: Search shared CORE and installed extension context with the core-context MCP. Use when a request depends on shared conventions, extension-specific guidance, product context, QA context, support context, or another installed CONTEXT document.
---

# Context Search

Before answering a request that depends on shared or extension context:

1. Call `context_status` to confirm `core-context` is connected. If it is not,
   tell the user to check the Docker service with
   `./installer/context_mcp.sh status` and enable its user-level registration
   in Cursor's MCP settings.
2. Call `context_search` with the request's context question. Set `source`
   only for a concrete source name, such as `CORE`, `PRODUCT`, `QA`, or
   `SUPPORT`.
3. If the MCP client offers an optional focus form for closely ranked,
   multi-source results, select a relevant source and/or topic when the
   request makes one clear. Declining, cancelling, or unsupported elicitation
   leaves the initial ranked results available.
4. Use the returned snippets to select relevant documents. Call `context_read`
   with an exact returned path when the complete document is necessary.
5. Identify the context source used in the response. Do not use this skill for
   unrelated repository code questions that do not need shared context.
