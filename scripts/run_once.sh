#!/usr/bin/env bash
# Un giro: scarica, calcola, salva solo se i dati sono cambiati.
set -uo pipefail
git pull --rebase --quiet origin main || true
python scripts/build.py && python scripts/static.py || { echo "giro fallito"; return 1 2>/dev/null || exit 1; }
if ! python scripts/changed.py; then
  echo "Dati invariati: nessun commit"
  git checkout -- data index.html 2>/dev/null || true
  exit 0
fi
git add data/ index.html
git commit -m "data: aggiornamento $(date -u +%Y-%m-%dT%H:%MZ)" --quiet
for i in 1 2 3; do
  git pull --rebase --quiet origin main && git push --quiet origin HEAD:main && exit 0
  sleep 5
done
exit 1
