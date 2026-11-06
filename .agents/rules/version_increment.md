# Version Increment Rule

## Core Principle
After **every change**, feature addition, bug fix, or deployment made to the Tradng-Ai codebase, **always increment the version number** on every push (e.g. `7.3.0` -> `7.3.1` -> `7.3.2`).

## Canonical Single Source of Truth
Version is centralized in two synchronized files:
1. `VERSION` (plain text, e.g. `7.3.0`)
2. `app/version.py` (`__version__ = "7.3.0"`)

## Automated Propagation
All system components read dynamically from the single source of truth:
- **Dashboard UI Header**: Automatically renders `PRO v{{ version }}` via Jinja context processor.
- **Browser Cache Invalidation**: All CSS/JS assets are automatically tagged with `?v={{ version }}`.
- **API Endpoints**: `/health` and `/api/state` return `"version": __version__`.
- **Startup Banners**: `run.py` and `run_dashboard.py` log `TRADNG-AI PRO v{__version__}`.

## Automation Tools & Git Hooks
1. **Automated Bumper**:
   ```bash
   python scripts/bump_version.py          # Bumps patch (e.g. 7.3.0 -> 7.3.1)
   python scripts/bump_version.py --minor  # Bumps minor (e.g. 7.3.0 -> 7.4.0)
   python scripts/bump_version.py --major  # Bumps major (e.g. 7.3.0 -> 8.0.0)
   ```
2. **Git Hook (`.githooks/pre-commit`)**:
   Automatically bumps and stages patch version before every `git commit` if not already staged.
   Enable with:
   ```bash
   python scripts/install_hooks.py
   ```

## Git & Deployment Invariant
Every push to `origin/main` and remote deployment to VM (`152.67.175.166`) must have an incremented version, verified live via `/health` and `/api/state`.
