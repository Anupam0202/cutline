from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIRED = {
    "LICENSE", "README.md", "Dockerfile", "pyproject.toml", "cutline/api.py",
    "cutline/providers.py", "cutline/agents/claim_research/agent.py",
    "static/index.html", "tests/test_domain.py", "docs/GCP_SETUP.md",
}
TEXT_SUFFIXES = {".py", ".js", ".css", ".html", ".md", ".toml", ".yaml", ".yml", ".sh", ".example"}
SECRET_PATTERNS = [
    re.compile(r"AIza[0-9A-Za-z_-]{30,}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
]
TRACE_NAMES = {"prompt1", "prompt2", "prompt3", "chain_of_thought", "chat_transcript"}


def main() -> int:
    failures: list[str] = []
    files = [path for path in ROOT.rglob("*") if path.is_file() and ".venv" not in path.parts]
    present = {path.relative_to(ROOT).as_posix() for path in files}
    for missing in sorted(REQUIRED - present):
        failures.append(f"missing required file: {missing}")
    for path in files:
        relative = path.relative_to(ROOT).as_posix()
        if any(name in relative.casefold() for name in TRACE_NAMES):
            failures.append(f"development trace filename: {relative}")
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name != "Dockerfile":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if path.name not in {"validate_repo.py", "SECURITY.md"}:
            if any(pattern.search(text) for pattern in SECRET_PATTERNS):
                failures.append(f"possible committed secret: {relative}")
    if (ROOT / ".env").exists():
        failures.append(".env must not be committed")
    if "MIT License" not in (ROOT / "LICENSE").read_text(encoding="utf-8"):
        failures.append("LICENSE is incomplete")
    if failures:
        print("Repository validation failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(f"Repository validation passed ({len(present)} files inspected).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
