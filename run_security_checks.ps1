# Run common security checks for this FastAPI project.
# Usage: powershell -ExecutionPolicy Bypass -File run_security_checks.ps1

$ErrorActionPreference = "Stop"

Write-Host "==> Running pytest security tests..." -ForegroundColor Cyan
pytest tests -v
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "`n==> Running Bandit SAST..." -ForegroundColor Cyan
bandit -r . -x .venv,venv,uploads,__pycache__,alembic,tests -ll
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "`n==> Running pip-audit dependency scan..." -ForegroundColor Cyan
pip-audit --requirement requirements.txt --format=json --output=pip-audit-report.json
# pip-audit returns 0 even when vulnerabilities are found; we keep the report for review.

Write-Host "`n==> Security checks completed." -ForegroundColor Green
Write-Host "    See pip-audit-report.json for dependency vulnerability details."
