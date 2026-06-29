#!/usr/bin/env bash
# Run common security checks for this FastAPI project.
# Usage: bash run_security_checks.sh

set -euo pipefail

echo "==> Running pytest security tests..."
pytest tests -v

echo "==> Running Bandit SAST..."
bandit -r . -x .venv,venv,uploads,__pycache__,alembic,tests -ll

echo "==> Running pip-audit dependency scan..."
pip-audit --requirement requirements.txt --format=json --output=pip-audit-report.json || true

echo "==> Security checks completed."
echo "    See pip-audit-report.json for dependency vulnerability details."
