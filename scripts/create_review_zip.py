"""
Utility script to create a clean, comprehensive distribution archive
containing all plaintext source files for peer code review.
Omits .git, .venv, caches, and database files.
"""

from pathlib import Path
import zipfile


def create_review_archive(output_path="Tradng-Ai-Review-Source.zip"):
    root = Path(__file__).resolve().parent.parent
    zip_dest = root / output_path

    include_patterns = [
        "app/**/*.py",
        "config/**/*.json",
        "tests/**/*.py",
        "scripts/**/*.py",
        "README.md",
        "requirements.txt",
        ".env.example",
    ]

    excluded_dirs = {".git", ".venv", "__pycache__", ".pytest_cache", ".idea", ".vscode"}

    count = 0
    with zipfile.ZipFile(zip_dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for pattern in include_patterns:
            for p in root.glob(pattern):
                # Skip excluded directories
                if any(ex in p.parts for ex in excluded_dirs):
                    continue
                if p.is_file():
                    arcname = p.relative_to(root)
                    zf.write(p, arcname)
                    count += 1

    print(f"Archive successfully created: {zip_dest}")
    print(f"Total plaintext source files packaged: {count}")
    return zip_dest


if __name__ == "__main__":
    create_review_archive()
