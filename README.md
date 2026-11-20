# Logs the Attacker Can't Erase

Tamper-evident security logging with SHA-256 hash chains, Merkle trees and blockchain anchoring (Polygon Amoy).

> Blockchain anchoring proves only that an anchored Merkle root has not changed since it was anchored.
> It does **not** prove that a logged event happened.

## Quick setup (Windows 11, PowerShell, Python 3.12)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env   # then edit .env yourself; never commit it
```

Every integration runs in SIMULATED mode when its keys are empty. Per-key setup and the one-command
launcher (`start.ps1`) are documented in Step 12. The API contract lives in `PROJECT_STATE.md`.
