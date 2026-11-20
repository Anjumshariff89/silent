# 2-minute demo script

Setup (before the audience): `.\start.ps1` (add `-AllowBroadcast` only for a REAL Quai demo you have approved) → open http://127.0.0.1:3000 → log in (`admin` / your API_KEY, or `dev-local-api-key` in simulator mode).

| Time | Page | Say | Do |
|---|---|---|---|
| 0:00 | Overview | "Security logs are the first thing an attacker deletes. Here every log is chained, batched and anchored." | Point to the **Quai Orchard (REAL)** / **SIMULATED** badges and the green/yellow indicator. |
| 0:15 | Live Logs | "The agent streams Windows logon and privilege events. They appear live over WebSocket." | Let 2-3 rows arrive. Use the search box: `user3`. |
| 0:30 | Hash-Chain | "Each log's hash includes the previous hash, so you can't edit one without breaking the next." | Show the green prev → curr links. |
| 0:45 | Hash-Chain | "Let's be the attacker." | Click **Tamper this log** on one block → header turns **red: TAMPER DETECTED**. "The server attacked a sandbox copy. The real logs are untouched." |
| 1:00 | Integrity | "It also catches deletions and reordering." | Choose *Delete a log*, run → `missing (sequence gap)`. Choose *Reorder*, run → `reordered`. |
| 1:15 | Tamper Alerts / Timeline | "Every finding is an incident with an alert: Telegram, or console in simulator mode." | Show the incident cards. Click **Reset demo** on Integrity. |
| 1:25 | Merkle Tree | "Logs are frozen into Merkle batches. One 32-byte root commits to all of them." | **Build batch** → show the tree and an inclusion proof. |
| 1:35 | Blockchain Explorer | "That root goes on Quai Orchard, Cyprus-1. Now even a database admin who rewrites the whole chain gets caught." | **Anchor** → **Verify** → `MATCH`. In REAL mode (badge **Quai Orchard (REAL)**) click the Orchard QuaiScan link. |
| 1:50 | Evidence Portal | "An auditor gets a JSON bundle they can verify offline, plus a PDF certificate." | Download both. Read the disclaimer line aloud: *anchoring proves the commitment is unchanged, not that events happened.* |
| 2:00 | Agent Monitoring | "Stop the agent and it goes delayed, then offline, with an alert." | (optional) stop the agent process. |
