"""Esce con 0 se i dati sono cambiati in modo sostanziale (non solo l'orario di generazione), 1 altrimenti.
Serve a non riempire il repository di commit identici."""
import json
import subprocess
import sys


def git(*a):
    return subprocess.run(["git", *a], capture_output=True, text=True).stdout


changed = [f for f in git("diff", "--name-only", "--", "data", "index.html").split() if f]
changed += [f for f in git("ls-files", "--others", "--exclude-standard", "data").split() if f]
if not changed:
    sys.exit(1)
real = [f for f in changed if f not in ("data/latest.json", "data/commentary_auto.json", "index.html")]
for f in ("data/latest.json", "data/commentary_auto.json"):
    if f in changed:
        old = git("show", f"HEAD:{f}")
        try:
            a, b = json.loads(old), json.load(open(f))
        except Exception:
            real.append(f)
            continue
        for d in (a, b):
            d.pop("generated", None)
        if a != b:
            real.append(f)
if "index.html" in changed and real:
    real.append("index.html")
print("cambiati:", ", ".join(real) if real else "solo orario")
sys.exit(0 if real else 1)
