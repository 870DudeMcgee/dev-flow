import json
import re

def repair_and_parse_json(text: str) -> dict:
    """
    Extracts and parses JSON from text, repairing truncated or slightly malformed
    JSON block responses from LLMs.
    """
    text_clean = text.strip()
    
    # 1. Try direct parse first
    try:
        return json.loads(text_clean)
    except json.JSONDecodeError:
        pass

    # 2. Extract code block content if wrapped in ```json ... ```
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text_clean, re.IGNORECASE)
    if match:
        candidate = match.group(1).strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            text_clean = candidate

    # 3. Perform a robust character-by-character scan to repair truncated braces/brackets and open quotes
    start_idx = text_clean.find("{")
    if start_idx == -1:
        # Fallback: maybe it's a list?
        start_idx = text_clean.find("[")
        if start_idx == -1:
            raise ValueError("No JSON object or array start found in text")
    
    truncated_candidate = text_clean[start_idx:]
    
    repaired = []
    stack = []  # tracks '{' or '['
    in_string = False
    escaped = False
    
    i = 0
    while i < len(truncated_candidate):
        char = truncated_candidate[i]
        
        if in_string:
            if escaped:
                repaired.append(char)
                escaped = False
            elif char == "\\":
                repaired.append(char)
                escaped = True
            elif char == '"':
                repaired.append(char)
                in_string = False
            elif char == "\n":
                # JSON strings cannot have literal newlines, escape it
                repaired.append("\\n")
            else:
                repaired.append(char)
        else:
            if char == '"':
                repaired.append(char)
                in_string = True
            elif char in ("{", "["):
                repaired.append(char)
                stack.append(char)
            elif char in ("}", "]"):
                if stack:
                    expected = "{" if char == "}" else "["
                    if stack[-1] == expected:
                        stack.pop()
                repaired.append(char)
            elif char == ",":
                repaired.append(char)
            else:
                repaired.append(char)
        i += 1
        
    # Close unclosed string quote if still open
    if in_string:
        if escaped and repaired and repaired[-1] == "\\":
            repaired.pop()
        repaired.append('"')
        
    repaired_str = "".join(repaired).strip()
    
    # Prune trailing commas before closing punctuation
    repaired_str = re.sub(r",\s*([}\]])", r"\1", repaired_str)
    
    # Close any unclosed brackets/braces on stack
    while stack:
        container = stack.pop()
        closing = "}" if container == "{" else "]"
        repaired_str = repaired_str.rstrip()
        if repaired_str.endswith(","):
            repaired_str = repaired_str[:-1].rstrip()
        repaired_str += closing
        
    # Return the parsed repaired JSON
    return json.loads(repaired_str)