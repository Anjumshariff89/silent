// Deploy a contract to Quai Orchard (Cyprus-1) with the quais SDK.
//
//   node scripts/deploy.js                         # DRY RUN (default): prints the deployment plan, sends nothing
//   node scripts/deploy.js --contract LogAnchor    # choose the artifact (default LogAnchor)
//   node scripts/deploy.js --broadcast             # actually deploy (only after the operator approved)
//
// Nothing is hardcoded: contract name comes from --contract, network from RPC_URL / CHAIN_ID in ../.env.
// The private key (CYPRUS1_PK) is only used inside quais.Wallet and is never printed.
"use strict";

const fs = require("fs");
const path = require("path");
require("dotenv").config({ path: path.join(__dirname, "..", "..", ".env") });
const quais = require("quais");
const { findPush0, extractMetadataCid } = require("./lib/bytecode");

function arg(name, def) {
  const i = process.argv.indexOf(`--${name}`);
  return i > 0 && process.argv[i + 1] && !process.argv[i + 1].startsWith("--") ? process.argv[i + 1] : def;
}

function explorerBase(chainId) {
  return chainId === 15000n ? "https://orchard.quaiscan.io" : chainId === 9n ? "https://quaiscan.io" : null;
}

function makeProvider(rpcUrl) {
  // A URL that already ends in a zone path (e.g. .../cyprus1) must be used as-is; a bare host needs
  // quais pathing (it appends /prime, /cyprus1 ...). See quais AbstractProvider.constructUrl.
  const hasZonePath = /\/(cyprus|paxos|hydra)[1-3]\/?$/i.test(new URL(rpcUrl).pathname);
  return new quais.JsonRpcProvider(rpcUrl, undefined, { usePathing: !hasZonePath });
}

async function main() {
  const broadcast = process.argv.includes("--broadcast");
  const contractName = arg("contract", "LogAnchor");
  const constructorArgs = JSON.parse(arg("args", "[]"));
  const { RPC_URL, CYPRUS1_PK, CHAIN_ID } = process.env;
  const expectedChain = BigInt(CHAIN_ID || 15000);
  if (!RPC_URL || !CYPRUS1_PK) throw new Error("RPC_URL and CYPRUS1_PK must be set in .env (throwaway testnet key)");

  const artifactPath = path.join(__dirname, "..", "artifacts", "contracts", `${contractName}.sol`, `${contractName}.json`);
  if (!fs.existsSync(artifactPath)) throw new Error(`artifact not found: ${artifactPath} (run npx hardhat compile)`);
  const art = JSON.parse(fs.readFileSync(artifactPath, "utf8"));

  const push0 = findPush0(art.bytecode);
  if (push0.length) throw new Error(`bytecode contains PUSH0 at ${push0.slice(0, 5)}; compile with evmVersion london`);
  const metadataCid = extractMetadataCid(art.bytecode); // local, from bytecode; nothing uploaded

  const provider = makeProvider(RPC_URL);
  const wallet = new quais.Wallet(CYPRUS1_PK, provider);
  const zone = quais.getZoneForAddress(wallet.address);
  if (zone !== quais.Zone.Cyprus1) {
    // check before any RPC call: quais itself rejects non-zone addresses with an unhelpful "Invalid zone"
    throw new Error(`wallet address ${wallet.address} is not a Cyprus-1 address (needs zone prefix 0x00, got ` +
      `${zone || "none"}). Use a Cyprus-1 account from a Quai wallet such as Pelagus; a random/MetaMask key ` +
      `is almost never in Cyprus-1.`);
  }
  const network = await provider.getNetwork();
  const balance = await provider.getBalance(wallet.address);
  const nonce = await provider.getTransactionCount(wallet.address);

  const plan = {
    action: broadcast ? "BROADCAST" : "DRY RUN (nothing sent)",
    network: "Quai Orchard Cyprus-1",
    rpc_url: RPC_URL,
    chain_id_expected: expectedChain.toString(),
    chain_id_rpc: network.chainId.toString(),
    wallet_address: wallet.address,
    wallet_zone: zone,
    wallet_balance_quai: quais.formatQuai(balance),
    wallet_nonce: nonce,
    contract_name: contractName,
    constructor_args: constructorArgs,
    metadata_cid_from_bytecode: metadataCid,
    push0_in_bytecode: false,
  };
  console.log(JSON.stringify(plan, null, 2));

  if (network.chainId !== expectedChain) throw new Error(`RPC chain ${network.chainId} != CHAIN_ID ${expectedChain}; refusing`);
  if (!broadcast) {
    console.log("\nDry run only. Re-run with --broadcast after the operator has approved this plan.");
    return;
  }
  if (balance === 0n) throw new Error("wallet has 0 QUAI; fund it from the Orchard faucet first");

  const factory = new quais.ContractFactory(art.abi, art.bytecode, wallet, metadataCid);
  const contract = await factory.deploy(...constructorArgs);
  const tx = contract.deploymentTransaction();
  console.log(`deploy tx sent: ${tx.hash}`);
  await contract.waitForDeployment();
  const address = await contract.getAddress();
  const receipt = await provider.getTransactionReceipt(tx.hash);
  const record = {
    network: "Quai Orchard Cyprus-1", chain_id: network.chainId.toString(), contract_name: contractName,
    contract_address: address, contract_zone: quais.getZoneForAddress(address), deploy_tx: tx.hash,
    block_number: receipt ? Number(receipt.blockNumber) : null, deployer: wallet.address,
    abi_path: `smart-contracts/artifacts/contracts/${contractName}.sol/${contractName}.json`,
    metadata_cid: metadataCid,
    explorer_tx: explorerBase(network.chainId) && `${explorerBase(network.chainId)}/tx/${tx.hash}`,
    explorer_address: explorerBase(network.chainId) && `${explorerBase(network.chainId)}/address/${address}`,
    deployed_at: new Date().toISOString(),
  };
  const outDir = path.join(__dirname, "..", "deployments");
  fs.mkdirSync(outDir, { recursive: true });
  fs.writeFileSync(path.join(outDir, `chain${network.chainId}-${contractName}.json`), JSON.stringify(record, null, 2) + "\n");
  console.log(JSON.stringify(record, null, 2));
  console.log(`\nSet CONTRACT_ADDRESS=${address} in .env yourself.`);
}

main().catch((e) => {
  // never echo the environment; quais errors do not contain the private key
  console.error(`ERROR: ${e.shortMessage || e.message}`);
  process.exit(1);
});
