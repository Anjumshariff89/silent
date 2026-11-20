/* Mock JSON used when NEXT_PUBLIC_USE_MOCK=1 (UI development without a backend). Synthetic data only. */
import type {
  Agent, BlockchainStatus, ChainLink, Health, Incident, IntegrityStatus, MerkleBatch, MerkleBatchSummary,
  Page, SecurityLog,
} from "./types";

const h = (n: number) => (n.toString(16).padStart(2, "0")).repeat(32).slice(0, 64);
const now = Date.now();
const iso = (msAgo: number) => new Date(now - msAgo).toISOString();
const TYPES: Array<[number, string, SecurityLog["severity"]]> = [
  [4624, "logon", "info"], [4634, "logoff", "info"], [4672, "special_privileges", "warning"],
  [4673, "privileged_service", "warning"],
];

let tampered = false;

const logs: SecurityLog[] = Array.from({ length: 40 }, (_, i) => {
  const [event_id, event_type, severity] = TYPES[i % 4];
  return {
    seq_id: i + 1, agent_id: i % 3 ? "agent-win-01" : "agent-win-02", event_id, event_type, severity,
    source_host: "WIN-SYNTH-01", username: `synthetic.user${i % 6}`, source_ip: `10.0.0.${20 + i}`,
    message: `Synthetic event #${i + 1}`, event_time: iso((40 - i) * 30000), received_at: iso((40 - i) * 30000 - 400),
    prev_hash: i === 0 ? "0".repeat(64) : h(i), curr_hash: h(i + 1), merkle_batch_id: i < 32 ? Math.floor(i / 16) + 1 : null,
  };
});

const health = (): Health => ({
  status: "ok", version: "0.1.0", mode: "simulator", database: { status: "ok", backend: "sqlite" },
  integrations: { blockchain: "SIMULATED", database: "SIMULATED", telegram: "SIMULATED", windows_event_log: "SIMULATED" },
  dev_api_key_in_use: true, log_count: logs.length, time: new Date().toISOString(),
});

const agents: Agent[] = [
  { agent_id: "agent-win-01", hostname: "WIN-SYNTH-01", agent_version: "0.1.0", collector_mode: "simulator",
    last_heartbeat: iso(4000), seconds_since_heartbeat: 4, status: "online" },
  { agent_id: "agent-win-02", hostname: "WIN-SYNTH-02", agent_version: "0.1.0", collector_mode: "simulator",
    last_heartbeat: iso(95000), seconds_since_heartbeat: 95, status: "offline" },
];

const incidents = (): Incident[] => [
  ...(tampered ? [{ id: 3, type: "modified", severity: "critical", seq_id: 12, agent_id: null, batch_id: null,
    target: "sandbox" as const, description: "curr_hash mismatch (mock)", status: "open" as const,
    alert_channel: "console", alert_sent: true, created_at: new Date().toISOString() }] : []),
  { id: 2, type: "heartbeat_timeout", severity: "warning", seq_id: null, agent_id: "agent-win-02", batch_id: null,
    target: "live", description: "Agent agent-win-02 missed heartbeats (mock)", status: "open", alert_channel: "console",
    alert_sent: true, created_at: iso(30000) },
];

const status = (): IntegrityStatus => ({
  status: tampered ? "red" : "green", last_result: tampered ? "FAIL" : "PASS", last_target: tampered ? "sandbox" : "live",
  last_verified_at: new Date().toISOString(),
  last_issues: tampered ? [{ type: "modified", seq_id: 12, detail: "curr_hash mismatch (mock)" }] : [],
  total_logs: logs.length, open_incidents: incidents().length, open_critical_incidents: tampered ? 1 : 0,
  last_anchored_batch_id: 2,
});

const batches: MerkleBatchSummary[] = [
  { batch_id: 2, root: h(200), leaf_count: 16, from_seq: 17, to_seq: 32, created_at: iso(60000), tx_hash: "0x" + h(201), mode: "SIMULATED" },
  { batch_id: 1, root: h(100), leaf_count: 16, from_seq: 1, to_seq: 16, created_at: iso(600000), tx_hash: "0x" + h(101), mode: "SIMULATED" },
];

function levelsFor(n: number): string[][] {
  let lvl = Array.from({ length: n }, (_, i) => h(i + 50));
  const out = [lvl];
  while (lvl.length > 1) {
    lvl = Array.from({ length: Math.ceil(lvl.length / 2) }, (_, i) => h(i + lvl.length + 90));
    out.push(lvl);
  }
  return out;
}

const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));

export async function mockRequest<T>(path: string, init: RequestInit): Promise<T> {
  await delay(150);
  const url = new URL(path, "http://mock");
  const p = url.pathname;
  const method = (init.method || "GET").toUpperCase();
  const out = (v: unknown) => v as T;
  if (p === "/api/health") return out(health());
  if (p === "/api/auth/login") return out({ access_token: "mock", token_type: "bearer", expires_in: 3600 });
  if (p === "/api/logs") {
    const q = (url.searchParams.get("q") || "").toLowerCase();
    const items = logs.filter((l) => !q || l.message.toLowerCase().includes(q) || (l.username || "").includes(q)).slice().reverse();
    return out({ items: items.slice(0, 50), page: 1, page_size: 50, total: items.length } satisfies Page<SecurityLog>);
  }
  if (p === "/api/agents") return out({ items: agents });
  if (p === "/api/heartbeats") return out({ items: [] });
  if (p === "/api/chain") {
    const links: ChainLink[] = logs.slice(-20).map((l) => ({ seq_id: l.seq_id, event_type: l.event_type, username: l.username,
      prev_hash: l.prev_hash, curr_hash: l.curr_hash, hash_valid: !(tampered && l.seq_id === 12), link_valid: true }));
    return out({ genesis_prev_hash: "0".repeat(64), links });
  }
  if (p === "/api/integrity/status") return out(status());
  if (p === "/api/verify") return out({ verification_id: 1, target: "live", result: "PASS", checked_count: logs.length,
    issues: [], incidents_created: [], verified_at: new Date().toISOString() });
  if (p === "/api/incidents") return out({ items: incidents(), page: 1, page_size: 50, total: incidents().length });
  if (p === "/api/demo/tamper" && method === "POST") {
    tampered = true;
    return out({ attack: "modified seq 12 (mock)", original_unchanged: true,
      verification: { result: "FAIL", issues: status().last_issues } });
  }
  if (p === "/api/demo/reset" || p === "/api/incidents/resolve") { tampered = false; return out({ resolved: 1, live_verification: "PASS" }); }
  if (p === "/api/merkle/batches") return out({ items: batches });
  const m = p.match(/^\/api\/merkle\/(\d+)$/);
  if (m) {
    const b = batches.find((x) => x.batch_id === Number(m[1])) ?? batches[0];
    return out({ ...b, levels: levelsFor(b.leaf_count), anchored: true, anchor_tx_hash: b.tx_hash, anchor_explorer_url: null } satisfies MerkleBatch);
  }
  const pr = p.match(/^\/api\/merkle\/(\d+)\/proof\/(\d+)$/);
  if (pr) return out({ batch_id: Number(pr[1]), seq_id: Number(pr[2]), leaf: h(9), leaf_index: 0,
    proof: [{ position: "right", hash: h(10) }, { position: "left", hash: h(11) }], root: h(100) });
  if (p === "/api/blockchain/status") return out({ mode: "SIMULATED", chain_id: 80002, connected: true, contract_address: null,
    anchor_wallet: null, latest_block: 1000002, anchored_batches: 2,
    last_anchor: { batch_id: 2, tx_hash: "0x" + h(201), block_number: 1000002, explorer_url: null } } satisfies BlockchainStatus);
  if (p === "/api/proof/verify") return out({ batch_id: 1, result: tampered ? "MISMATCH" : "MATCH", local_root: h(100),
    anchored_root: h(100), inclusion_proof_valid: true, problems: [], tx_hash: "0x" + h(101), explorer_url: null,
    note: "Mock data." });
  if (p === "/api/merkle/build") return out({ batch_id: 3, root: h(3), leaf_count: 8, from_seq: 33, to_seq: 40, created_at: new Date().toISOString() });
  if (p === "/api/blockchain/anchor") return out({ batch_id: 3, tx_hash: "0x" + h(3), mode: "SIMULATED", block_number: 1000003 });
  if (p.startsWith("/api/evidence/")) return out({ schema_version: "1.0", mock: true });
  throw new Error(`mock: no handler for ${method} ${p}`);
}
