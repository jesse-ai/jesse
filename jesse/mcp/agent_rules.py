"""
Agent rules sync.

Keeps the user's agent rules file (AGENTS.md / CLAUDE.md / mcp-rules.md) in sync
with the canonical rules bundled inside the installed jesse package.

The managed content lives between these markers in the user's file:

    <!-- JESSE-RULES-START vX.Y.Z -->
    ...rules body...
    <!-- JESSE-RULES-END -->

Anything outside the markers is preserved.
"""
import re
from importlib.metadata import version as get_version
from importlib.resources import files
from pathlib import Path
from typing import Optional

RULES_FILENAMES = ["AGENTS.md", "CLAUDE.md", "mcp-rules.md"]
DEFAULT_FILENAME = "AGENTS.md"
START_RE = re.compile(r"<!--\s*JESSE-RULES-START\s+v([^\s>]+)\s*-->")
END_MARKER = "<!-- JESSE-RULES-END -->"
LEGACY_OPENING = "You are a Jesse trading strategy agent."


def _load_packaged_rules() -> str:
    return (files("jesse.mcp") / "agent_rules.md").read_text(encoding="utf-8").strip()


def _make_block(version: str, body: str) -> str:
    return f"<!-- JESSE-RULES-START v{version} -->\n{body.strip()}\n{END_MARKER}\n"


def _find_existing(cwd: Path) -> Optional[Path]:
    for name in RULES_FILENAMES:
        p = cwd / name
        if p.exists():
            return p
    return None


def sync_agent_rules(cwd: Optional[Path] = None, verbose: bool = True) -> None:
    cwd = cwd or Path.cwd()
    jesse_version = get_version("jesse")
    rules_body = _load_packaged_rules()

    existing = _find_existing(cwd)

    if existing is None:
        target = cwd / DEFAULT_FILENAME
        target.write_text(_make_block(jesse_version, rules_body), encoding="utf-8")
        if verbose:
            print(f"Agent rules created ({DEFAULT_FILENAME})")
        return

    content = existing.read_text(encoding="utf-8")
    m = START_RE.search(content)
    end_idx = content.find(END_MARKER, m.end()) if m else -1

    if m and end_idx != -1:
        existing_version = m.group(1)
        if existing_version == jesse_version:
            if verbose:
                print(f"Agent rules already up to date ({existing.name})")
            return
        block_end = end_idx + len(END_MARKER)
        if block_end < len(content) and content[block_end] == "\n":
            block_end += 1
        new_block = _make_block(jesse_version, rules_body)
        new_content = content[:m.start()] + new_block + content[block_end:]
        existing.write_text(new_content, encoding="utf-8")
        if verbose:
            print(f"Agent rules updated to v{jesse_version} ({existing.name})")
        return

    if content.lstrip().startswith(LEGACY_OPENING):
        existing.write_text(_make_block(jesse_version, rules_body), encoding="utf-8")
        if verbose:
            print(f"Agent rules migrated to v{jesse_version} ({existing.name})")
        return

    if verbose:
        print(
            f"{existing.name} looks customized; not modifying. "
            f"Wrap your Jesse section with <!-- JESSE-RULES-START vX --> "
            f"... {END_MARKER} to enable auto-sync."
        )
