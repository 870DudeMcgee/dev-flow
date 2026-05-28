# Subskill: Search Before Reading

This subskill governs how to discover references, symbols, and files with minimal token consumption.

## Guidelines

1. **Search First**: When trying to find where a variable, function, or CLI command is defined or referenced, use search tools (e.g., `rg`, `grep_search`), symbol search, or the nearest available search tool rather than opening entire directory files.
2. **Path Optimization**: Narrow the search scope by using directory limits, file glob patterns, or target path parameters to search only relevant folders (e.g., `src/` or `tests/`).
3. **Avoid Full Reads**: If a grep match shows the matching line content, do not open the file unless you must modify it or inspect surrounding block context (such as imports or execution logic).
4. **Symbol Discovery**: Use Python symbol parsing or targeted regex matches if looking for exact function definitions, rather than scrolling through full source listings.
