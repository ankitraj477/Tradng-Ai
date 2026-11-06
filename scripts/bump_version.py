#!/usr/bin/env python3
"""
Tradng-Ai Automated Version Bumper
Usage:
    python scripts/bump_version.py            # Bumps patch: 7.3.0 -> 7.3.1
    python scripts/bump_version.py --minor    # Bumps minor: 7.3.0 -> 7.4.0
    python scripts/bump_version.py --major    # Bumps major: 7.3.0 -> 8.0.0
    python scripts/bump_version.py --set 7.5.0
    python scripts/bump_version.py --stage    # Used by Git hooks to auto-stage
    python scripts/bump_version.py --check    # Displays current version without changes
"""

import sys
import re
import argparse
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT_DIR / "VERSION"
PY_VERSION_FILE = ROOT_DIR / "app" / "version.py"


def get_current_version() -> str:
    if VERSION_FILE.exists():
        raw = VERSION_FILE.read_text(encoding="utf-8").strip()
        if raw:
            return raw
    if PY_VERSION_FILE.exists():
        content = PY_VERSION_FILE.read_text(encoding="utf-8")
        match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
        if match:
            return match.group(1).strip()
    return "7.3.0"


def parse_semver(v_str: str):
    # Match standard major.minor.patch or major.minor
    parts = [int(p) for p in re.findall(r"\d+", v_str)]
    if len(parts) == 1:
        return parts[0], 0, 0
    elif len(parts) == 2:
        return parts[0], parts[1], 0
    elif len(parts) >= 3:
        return parts[0], parts[1], parts[2]
    return 7, 3, 0


def bump_version(current: str, part: str = "patch", explicit: str = None) -> str:
    if explicit:
        return explicit.strip()
    major, minor, patch = parse_semver(current)
    if part == "major":
        return f"{major + 1}.0.0"
    elif part == "minor":
        return f"{major}.{minor + 1}.0"
    else:  # patch
        return f"{major}.{minor}.{patch + 1}"


def write_version_files(new_version: str):
    # 1. Write VERSION file
    VERSION_FILE.write_text(f"{new_version}\n", encoding="utf-8")

    # 2. Write app/version.py
    py_content = (
        '"""\n'
        'Tradng-Ai Version Registry\n'
        'Canonical single source of truth for dashboard and engine versioning.\n'
        '"""\n\n'
        f'__version__ = "{new_version}"\n'
        'VERSION = __version__\n'
    )
    PY_VERSION_FILE.write_text(py_content, encoding="utf-8")


def is_already_staged() -> bool:
    """Check if VERSION or app/version.py is already modified in git staging area."""
    try:
        out = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only"],
            cwd=str(ROOT_DIR),
            stderr=subprocess.DEVNULL
        ).decode("utf-8")
        lines = [line.strip() for line in out.splitlines()]
        return ("VERSION" in lines) or ("app/version.py" in lines)
    except Exception:
        return False


def stage_version_files():
    """Stage updated version files in git."""
    try:
        subprocess.check_call(
            ["git", "add", "VERSION", "app/version.py"],
            cwd=str(ROOT_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception as e:
        print(f"[Tradng-Ai Version] Warning: Could not git add version files: {e}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Tradng-Ai Version Management Tool")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--patch", action="store_true", help="Bump patch version (e.g. 7.3.0 -> 7.3.1) [default]")
    group.add_argument("--minor", action="store_true", help="Bump minor version (e.g. 7.3.0 -> 7.4.0)")
    group.add_argument("--major", action="store_true", help="Bump major version (e.g. 7.3.0 -> 8.0.0)")
    group.add_argument("--set", type=str, help="Explicitly set version string")
    group.add_argument("--check", action="store_true", help="Check current version and exit")

    parser.add_argument("--stage", action="store_true", help="Auto git-stage updated version files (used by git hooks)")
    args = parser.parse_args()

    curr = get_current_version()

    if args.check:
        print(f"Tradng-Ai Current Version: {curr}")
        return

    # If --stage was passed from a git hook and files are already staged, skip double-bumping
    if args.stage and is_already_staged():
        print(f"[Tradng-Ai Version] Version file already staged with version: {curr}")
        return

    part = "patch"
    if args.major:
        part = "major"
    elif args.minor:
        part = "minor"

    new_v = bump_version(curr, part=part, explicit=args.set)
    write_version_files(new_v)
    print(f"[Tradng-Ai Version] Bumped: v{curr} -> v{new_v}")

    if args.stage:
        stage_version_files()
        print(f"[Tradng-Ai Version] Staged VERSION and app/version.py (v{new_v})")


if __name__ == "__main__":
    main()
