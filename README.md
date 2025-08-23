# Quant Assistant (GitHub-ready)

Educational quant toolkit: options idea engine, sector/industry screener, Monte Carlo simulator, portfolio ingestion.

## Quick start (local)
1) `docker compose -f infra/docker-compose.yml up --build`
2) API: http://localhost:8000/docs
3) UI : http://localhost:5173

`MOCK_MODE=1` makes everything run with no API keys. Flip to `0` and add keys later.

## CI & Docker images
- **.github/workflows/ci.yml** builds API + UI on every push/PR.
- **.github/workflows/release.yml** pushes images to **Docker Hub** on tag like `v1.0.0`.
  - Set GitHub repo secrets: `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`.
  - Edit `.docker.env` to set `IMAGE_API` and `IMAGE_FE`.

## Disclaimer
This project is for education only and not financial advice.

