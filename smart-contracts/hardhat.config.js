// Hardhat config for Quai Orchard (Cyprus-1, chain 15000).
// Compiler settings follow docs.qu.ai "Deploy with Solidity": 0.8.20, evmVersion "london"
// (0.8.20 defaults to Shanghai, whose PUSH0 opcode the Quai EVM may not support), metadata
// bytecodeHash "ipfs" (quais ContractFactory requires the metadata CID, read locally from bytecode).
require("@nomicfoundation/hardhat-ethers");
require("@nomicfoundation/hardhat-chai-matchers");
const path = require("path");
require("dotenv").config({ path: path.join(__dirname, "..", ".env") }); // project .env, never committed
const { subtask } = require("hardhat/config");
const { TASK_COMPILE_SOLIDITY_GET_SOLC_BUILD } = require("hardhat/builtin-tasks/task-names");

const SOLC_VERSION = "0.8.20";

// Use the pinned npm `solc` (solcjs) so compiling never downloads a compiler.
subtask(TASK_COMPILE_SOLIDITY_GET_SOLC_BUILD, async (args, hre, runSuper) => {
  if (args.solcVersion === SOLC_VERSION) {
    const solc = require("solc");
    return { compilerPath: require.resolve("solc/soljson.js"), isSolcJs: true,
             version: SOLC_VERSION, longVersion: solc.version() };
  }
  return runSuper();
});

const { RPC_URL, CYPRUS1_PK, CHAIN_ID } = process.env;

module.exports = {
  solidity: {
    version: SOLC_VERSION,
    settings: {
      optimizer: { enabled: true, runs: 200 },
      evmVersion: "london",
      metadata: { bytecodeHash: "ipfs" },
    },
  },
  defaultNetwork: "hardhat",
  networks: {
    hardhat: {},
    // Used only for configuration (url/chainId). Quai transactions are built and signed with the
    // quais SDK (scripts/deploy.js, backend/blockchain/quai-service), not hardhat-ethers.
    cyprus1: {
      url: RPC_URL || "https://orchard.rpc.quai.network/cyprus1",
      chainId: Number(CHAIN_ID || 15000),
      accounts: CYPRUS1_PK ? [CYPRUS1_PK] : [],
    },
  },
};
