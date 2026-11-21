// Quai network names and Orchard/mainnet QuaiScan explorer links (no key needed).
export const QUAI_ORCHARD = 15000;
export const QUAI_MAINNET = 9;

const EXPLORERS: Record<number, string> = {
  [QUAI_ORCHARD]: "https://orchard.quaiscan.io",
  [QUAI_MAINNET]: "https://quaiscan.io",
};

export function chainName(chainId: number | null | undefined): string {
  if (chainId === QUAI_ORCHARD) return "Quai Orchard Cyprus-1 (15000)";
  if (chainId === QUAI_MAINNET) return "Quai Mainnet Cyprus-1 (9)";
  return chainId == null ? "—" : `chain ${chainId}`;
}

export function explorerTx(chainId: number | null | undefined, tx: string | null | undefined): string | null {
  const base = chainId != null ? EXPLORERS[chainId] : undefined;
  return base && tx ? `${base}/tx/${tx}` : null;
}

export function explorerAddress(chainId: number | null | undefined, addr: string | null | undefined): string | null {
  const base = chainId != null ? EXPLORERS[chainId] : undefined;
  return base && addr ? `${base}/address/${addr}` : null;
}

/** Header badge text for the blockchain integration: "Quai Orchard (REAL)" or "NOT CONFIGURED". */
export function blockchainBadgeLabel(mode: string, chainId?: number | null): string {
  if (mode !== "REAL") return "NOT CONFIGURED";
  return chainId === QUAI_MAINNET ? "Quai Mainnet (REAL)" : "Quai Orchard (REAL)";
}
