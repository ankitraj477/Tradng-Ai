#!/usr/bin/env python3
"""
Install Git Hooks for Tradng-Ai
Configures Git to use version-controlled .githooks directory.
"""
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

def install_hooks():
    try:
        subprocess.check_call(["git", "config", "core.hooksPath", ".githooks"], cwd=str(ROOT_DIR))
        print("✅ Configured git to use .githooks directory (core.hooksPath = .githooks).")
        print("Version will now automatically bump on every commit/push!")
    except Exception as e:
        print(f"❌ Failed to configure git hooks: {e}")

if __name__ == "__main__":
    install_hooks()
