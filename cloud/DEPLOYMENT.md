# Cloud deployment plan

V3 is designed to run first on Windows and later in a small Linux container.

## PC validation
1. Create `.env` from `.env.example`.
2. Install requirements.
3. Run `python scripts/seed_demo.py`.
4. Run `python -m app`.
5. Verify dashboard and SQLite persistence.
6. Only then use `python -m app --live`.

## Cloud
Use any provider that offers a genuinely free/eligible small container or VM at deployment time.
Do not hard-code a provider or claim a permanent free tier.
Build with:
`docker build -f docker/Dockerfile .`
Run with persistent storage mounted at `/app/data`.

## Operational requirements
- Persistent `/app/data` volume.
- Automatic restart.
- `/health` endpoint.
- Dashboard exposed only through HTTPS/authentication in a real deployment.
- Never store broker credentials because V1/V3 has no broker execution.
