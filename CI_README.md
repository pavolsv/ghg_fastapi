# CI workflow

This project uses GitHub Actions workflow at `.github/workflows/ci.yml`.

## What CI runs

1. Install dependencies from `requirements.txt` and `requirements-dev.txt`
2. Run `ruff check tests`
3. Run `black --check tests`
4. Run database migrations: `alembic upgrade head`
5. Run tests: `pytest -q`
6. Build Docker image

## Run the same checks locally (Windows PowerShell)

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt -r requirements-dev.txt
ruff check tests
black --check tests
alembic upgrade head
pytest -q
docker build -t backup_fastapi:local .
```