"""Step 1 checks: scaffold, secrets hygiene, and API contract completeness."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

EXPECTED_ENV_LINES = [
    "MODE=real",
    "API_KEY=",
    "JWT_SECRET=",
    "DATABASE_URL=sqlite:///./local.db",
    "RPC_URL=",
    "CYPRUS1_PK=",
    "CHAIN_ID=15000",
    "CONTRACT_ADDRESS=",
    "TELEGRAM_BOT_TOKEN=",
    "TELEGRAM_CHAT_ID=",
    "SUPABASE_URL=",
    "SUPABASE_JWT_SECRET=",
    "FRONTEND_ORIGIN=",
]

CONTRACT_ENDPOINTS = [
    "POST /api/logs/ingest",
    "GET /api/logs`",
    "GET /api/heartbeats",
    "POST /api/heartbeats",
    "GET /api/agents",
    "GET /api/health",
    "POST /api/verify",
    "GET /api/integrity/status",
    "GET /api/incidents",
    "POST /api/merkle/build",
    "GET /api/merkle/{batch_id}`",
    "GET /api/merkle/{batch_id}/proof/{seq_id}",
    "POST /api/blockchain/anchor",
    "GET /api/blockchain/status",
    "POST /api/proof/verify",
    "GET /api/evidence/{batch_id}/json",
    "GET /api/evidence/{batch_id}/pdf",
    "WebSocket /ws/live",
    "GET /health",
    "POST /logs",
    "GET /logs`",
    "GET /verify",
    "POST /merkle/build",
    "POST /anchor",
    "GET /anchors",
    "GET /merkle/roots",
    "POST /anchors/{anchor_id}/verify",
]


def test_folder_structure():
    for sub in ["app", "agent", "crypto", "merkle", "blockchain", "database", "api", "integrations"]:
        assert (ROOT / "backend" / sub).is_dir(), sub
    assert (ROOT / "backend" / "main.py").is_file()
    assert (ROOT / "backend" / "blockchain" / "quai-service").is_dir()
    for d in ["frontend", "smart-contracts", "tests", "documentation"]:
        assert (ROOT / d).is_dir(), d
    for f in [".env.example", ".gitignore", "requirements.txt", "README.md", "start.ps1", "run-dev.ps1", "PROJECT_STATE.md"]:
        assert (ROOT / f).is_file(), f


def test_env_example_contains_exactly_the_required_keys_with_no_values():
    lines = [l for l in (ROOT / ".env.example").read_text().splitlines() if l.strip()]
    assert lines == EXPECTED_ENV_LINES


def test_env_is_git_ignored_but_example_is_not():
    ignored = subprocess.run(["git", "check-ignore", "-q", ".env"], cwd=ROOT)
    assert ignored.returncode == 0, ".env must be ignored"
    example = subprocess.run(["git", "check-ignore", "-q", ".env.example"], cwd=ROOT)
    assert example.returncode == 1, ".env.example must NOT be ignored"


def test_no_env_file_tracked():
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    assert ".env" not in tracked


def test_every_requirement_is_pinned():
    for line in (ROOT / "requirements.txt").read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        assert re.match(r"^[A-Za-z0-9_.\-\[\]]+==[0-9][^;\s]*(\s*;.*)?$", line), f"unpinned: {line}"


def test_contract_lists_every_endpoint():
    text = (ROOT / "PROJECT_STATE.md").read_text()
    missing = [e for e in CONTRACT_ENDPOINTS if e not in text]
    assert not missing, f"missing from contract: {missing}"


def test_feature_branches_exist():
    out = subprocess.run(["git", "branch", "--format=%(refname:short)"], cwd=ROOT,
                         capture_output=True, text=True).stdout.split()
    for b in ["main", "feature/log-collection", "feature/tamper-detection",
              "feature/blockchain", "feature/frontend"]:
        assert b in out, b


def test_env_example_has_no_polygon_or_extra_keys():
    text = (ROOT / ".env.example").read_text()
    for banned in ("AMOY", "POLYGON", "ANCHOR_PRIVATE_KEY", "QUAI_CONTRACT_ADDRESS", "#"):
        assert banned not in text, banned


def test_node_is_available():
    out = subprocess.run(["node", "--version"], capture_output=True, text=True)
    assert out.returncode == 0 and out.stdout.startswith("v")
    assert int(out.stdout[1:].split(".")[0]) >= 20, out.stdout
