from __future__ import annotations


def looks_destructive_command(command: list[str]) -> bool:
    text = " ".join(command).lower()
    blocked_fragments = ("rm -rf /", "rm -fr /", "mkfs", "diskutil erase", ":(){", "dd if=")
    return any(fragment in text for fragment in blocked_fragments)
