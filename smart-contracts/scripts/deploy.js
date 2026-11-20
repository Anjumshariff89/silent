// Deploys LogAnchor. Amoy: `npm run deploy:amoy` (needs AMOY_RPC_URL + ANCHOR_PRIVATE_KEY in ../.env).
// Prints the address and an Amoy explorer link; never prints the private key.
const hre = require("hardhat");

async function main() {
  const [deployer] = await hre.ethers.getSigners();
  const net = await hre.ethers.provider.getNetwork();
  console.log(`Network: ${hre.network.name} (chainId ${net.chainId})`);
  console.log(`Deployer address: ${deployer.address}`);
  const LogAnchor = await hre.ethers.getContractFactory("LogAnchor");
  const c = await LogAnchor.deploy();
  await c.waitForDeployment();
  const address = await c.getAddress();
  const tx = c.deploymentTransaction();
  console.log(`LogAnchor deployed at: ${address}`);
  console.log(`Deploy tx: ${tx.hash}`);
  if (net.chainId === 80002n) {
    console.log(`Explorer: https://amoy.polygonscan.com/address/${address}`);
    console.log(`Now set CONTRACT_ADDRESS=${address} in .env yourself.`);
  }
}

main().catch((e) => { console.error(e.message || e); process.exit(1); });
