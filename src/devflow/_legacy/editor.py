"""Deprecated XML search/replace editor utilities.

MVP execution uses unified diffs. This module is retained only for compatibility.
"""

import re
from typing import Optional, Tuple

def apply_xml_edits(original_content: str, xml_changes: str) -> Tuple[str, Optional[str]]:
    """
    Parses <search> and <replace> tags from xml_changes and applies them to original_content.
    Returns (modified_content, error_message).
    """
    # Pattern to extract <search>...</search> and <replace>...</replace> pairs
    # DOTALL allows dot (.) to match newlines
    pattern = r'<search>(.*?)</search>\s*<replace>(.*?)</replace>'
    blocks = re.findall(pattern, xml_changes, re.DOTALL)
    
    if not blocks:
        return original_content, "No valid XML <search> and <replace> blocks found."
        
    current_content = original_content
    for search, replace in blocks:
        # Strip leading/trailing empty newlines if the model left extra whitespace around tags
        search_stripped = search
        if search.startswith('\n'):
            search_stripped = search[1:]
        if search_stripped.endswith('\n'):
            search_stripped = search_stripped[:-1]
            
        replace_stripped = replace
        if replace.startswith('\n'):
            replace_stripped = replace[1:]
        if replace_stripped.endswith('\n'):
            replace_stripped = replace_stripped[:-1]
            
        # We search for the exact match of the clean search block
        # If it doesn't match, we try a fallback matching of stripped search block
        if search in current_content:
            current_content = current_content.replace(search, replace, 1)
        elif search_stripped in current_content:
            current_content = current_content.replace(search_stripped, replace_stripped, 1)
        else:
            # Let's provide a friendly error message
            return original_content, f"Search block not found in target file:\n{search_stripped}"
            
    return current_content, None
