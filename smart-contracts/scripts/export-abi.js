// Copies the compiled LogAnchor ABI to the quai-service (the only component that talks to Quai).
const fs = require("fs");
const path = require("path");
const art = require("../artifacts/contracts/LogAnchor.sol/LogAnchor.json");
const out = path.join(__dirname, "..", "..", "backend", "blockchain", "quai-service", "LogAnchor.abi.json");
fs.writeFileSync(out, JSON.stringify(art.abi, null, 2) + "\n");
console.log(`ABI written to ${out} (${art.abi.length} entries)`);
