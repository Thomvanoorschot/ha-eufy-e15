#!/usr/bin/env bash
# Fetch the device ID and local key of your Eufy E15, once.
# Uses the repository's .venv and creates it when it does not exist yet.
set -euo pipefail

repo="$(cd "$(dirname "$0")/.." && pwd)"
venv="$repo/.venv"

if [[ ! -x "$venv/bin/python" ]]; then
  echo "Python-omgeving aanmaken in .venv ..."
  python3 -m venv "$venv"
fi
if ! "$venv/bin/python" -c "import cryptography" 2>/dev/null; then
  "$venv/bin/pip" install --quiet cryptography
fi

exec "$venv/bin/python" -I "$repo/tools/eufy_local_key.py"
