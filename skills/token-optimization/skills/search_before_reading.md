# Subskill: Search Before Reading

This subskill governs how to discover references, symbols, and files with minimal token consumption.

## Guidelines

1. **Grep First**: When trying to find where a variable, function, or CLI command is defined or referenced, use `grep_search` rather than opening directory files.
2. **Path Optimization**: Narrow the search scope by using directory limits or file patterns if known (e.g., limit to `src/` or `tests/` using the `Includes` parameter).
3. **Avoid Full Reads**: If a grep match shows the matching line content, do not open the file unless you must modify it or inspect surrounding block context (such as imports or execution logic).
4. **Symbol Discovery**: Use Python symbol parsing or targeted regex matches if looking for exact function definitions, rather than scrolling through full source listings.
