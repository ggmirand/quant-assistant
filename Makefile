up:
\tdocker compose -f infra/docker-compose.yml up --build -d
down:
\tdocker compose -f infra/docker-compose.yml down
logs:
\tdocker compose -f infra/docker-compose.yml logs -f
lint:
\tpython -m pip install ruff black >/dev/null 2>&1 || true
\truff check backend/src || true
\tblack --check backend/src || true
build-images:
\tsource .docker.env && docker build -t $$IMAGE_API:local ./backend && docker build -t $$IMAGE_FE:local ./frontend
