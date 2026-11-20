require("@nomicfoundation/hardhat-ethers");
require("@nomicfoundation/hardhat-chai-matchers");
const path = require("path");
require("dotenv").config({ path: path.join(__dirname, "..", ".env") }); // shared project .env (never committed)
const { subtask } = require("hardhat/config");
const { TASK_COMPILE_SOLIDITY_GET_SOLC_BUILD } = require("hardhat/builtin-tasks/task-names");

const SOLC_VERSION = "0.8.24";

// Use the pinned npm `solc` (solcjs) instead of downloading a compiler at build time.
subtask(TASK_COMPILE_SOLIDITY_GET_SOLC_BUILD, async (args, hre, runSuper) => {
  if (args.solcVersion === SOLC_VERSION) {
    const solc = require("solc");
    return { compilerPath: require.resolve("solc/soljson.js"), isSolcJs: true,
             version: SOLC_VERSION, longVersion: solc.version() };
  }
  return runSuper();
});

const { AMOY_RPC_URL, ANCHOR_PRIVATE_KEY } = process.env;

module.exports = {
  solidity: { version: SOLC_VERSION, settings: { optimizer: { enabled: true, runs: 200 } } },
  networks: {
    hardhat: {},
    localhost: { url: "http://127.0.0.1:8545" },
    ...(AMOY_RPC_URL && ANCHOR_PRIVATE_KEY
      ? { amoy: { url: AMOY_RPC_URL, chainId: 80002, accounts: [ANCHOR_PRIVATE_KEY] } }
      : {}),
  },
};
