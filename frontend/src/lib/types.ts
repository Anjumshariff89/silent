export type Badge = "REAL" | "SIMULATED";

export interface Health {
  status: string;
  version: string;
  mode: string;
  database: { status: string; backend: string };
  integrations: { blockchain: Badge; database: Badge; telegram: Badge; windows_event_log: Badge };
  dev_api_key_in_use: boolean;
  log_count: number | null;
  time: string;
}

export interface SecurityLog {
  seq_id: number;
  agent_id: string;
  event_id: number;
  event_type: string;
  severity: "info" | "warning" | "critical";
  source_host: string;
  username: string | null;
  source_ip: string | null;
  message: string;
  event_time: string;
  received_at: string;
  prev_hash: string;
  curr_hash: string;
  merkle_batch_id: number | null;
}

export interface Page<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
}

export interface Agent {
  agent_id: string;
  hostname: string;
  agent_version: string;
  collector_mode: string;
  last_heartbeat: string | null;
  seconds_since_heartbeat: number | null;
  status: "online" | "delayed" | "offline";
}

export interface ChainLink {
  seq_id: number;
  event_type: string;
  username: string | null;
  prev_hash: string;
  curr_hash: string;
  hash_valid: boolean;
  link_valid: boolean;
}

export interface Issue {
  type: string;
  seq_id: number;
  detail: string;
}

export interface VerifyResult {
  verification_id: number;
  target: string;
  result: "PASS" | "FAIL";
  checked_count: number;
  issues: Issue[];
  incidents_created: number[];
  verified_at: string;
}

export interface IntegrityStatus {
  status: "green" | "yellow" | "red";
  last_result: "PASS" | "FAIL" | null;
  last_target: string | null;
  last_verified_at: string | null;
  last_issues: Issue[];
  total_logs: number;
  open_incidents: number;
  open_critical_incidents: number;
  last_anchored_batch_id: number | null;
}

export interface Incident {
  id: number;
  type: string;
  severity: string;
  seq_id: number | null;
  agent_id: string | null;
  batch_id: number | null;
  target: "live" | "sandbox";
  description: string;
  status: "open" | "resolved";
  alert_channel: string | null;
  alert_sent: boolean;
  created_at: string;
}

export interface MerkleBatchSummary {
  batch_id: number;
  root: string;
  leaf_count: number;
  from_seq: number;
  to_seq: number;
  created_at: string;
  tx_hash: string | null;
  mode: string | null;
}

export interface MerkleBatch extends MerkleBatchSummary {
  levels: string[][];
  anchored: boolean;
  anchor_tx_hash: string | null;
  anchor_explorer_url: string | null;
}

export interface ProofStep {
  position: "left" | "right";
  hash: string;
}

export interface MerkleProof {
  batch_id: number;
  seq_id: number;
  leaf: string;
  leaf_index: number;
  proof: ProofStep[];
  root: string;
}

export interface Anchor {
  batch_id: number;
  onchain_batch_id: string;
  root: string;
  mode: Badge;
  chain_id: number;
  tx_hash: string;
  block_number: number;
  block_timestamp: string;
  contract_address: string | null;
  explorer_url: string | null;
}

export interface BlockchainStatus {
  mode: Badge;
  chain_id: number;
  connected: boolean;
  contract_address: string | null;
  anchor_wallet: string | null;
  latest_block: number | null;
  anchored_batches: number;
  last_anchor: { batch_id: number; tx_hash: string; block_number: number; explorer_url: string | null } | null;
}

export interface ProofVerify {
  batch_id: number;
  result: "MATCH" | "MISMATCH" | "NOT_ANCHORED";
  local_root: string | null;
  anchored_root: string | null;
  inclusion_proof_valid: boolean | null;
  problems: string[];
  tx_hash: string | null;
  explorer_url: string | null;
  note: string;
}

export interface LiveMessage {
  type: "hello" | "log" | "heartbeat" | "agent_status" | "incident" | "integrity" | "anchor";
  data: Record<string, unknown>;
}
