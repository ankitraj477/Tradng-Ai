# Version Increment Rule

## Core Principle
After **every change**, feature addition, bug fix, or deployment made to the Tradng-Ai codebase, **always increment the version number** (e.g. `3.0` -> `3.1` -> `3.2`).

## Required Files to Update on Every Increment
1. `app/dashboard.py`:
   - HTML `<title>` tag: `<title>Tradng-Ai vX.Y · Institutional Terminal</title>`
   - Header brand badge: `<h1>Tradng-Ai <span class="brand-badge">PRO vX.Y</span></h1>`
   - `/health` endpoint: `"version": "X.Y"`
   - `/api/state` endpoint: `"version": "X.Y"`
2. `run.py`:
   - Startup banner: `print("   TRADNG-AI PRO vX.Y: UNIFIED MULTI-DESK TRADING ENGINE    ")`

## Git & Deployment Invariant
Every git commit that alters trading logic, desk mechanics, or UI must reflect the new incremented version, be pushed to `origin/main`, pulled onto the remote VM (`152.67.175.166`), and verified live via `/health` and `/api/state`.
