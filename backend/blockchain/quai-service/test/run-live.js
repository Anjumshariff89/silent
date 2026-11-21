"use strict";
// Cross-platform launcher for the live read-only tests (`npm run test:live`).
// npm runs scripts with cmd.exe on Windows, where the POSIX form `QUAI_LIVE=1 node ...` fails, so the
// variable is set here instead. The live tests only read from the Orchard RPC; they never send a transaction.
const { spawnSync } = require("node:child_process");
const path = require("node:path");

const result = spawnSync(process.execPath, ["--test", "--test-force-exit", path.join(__dirname, "live-readonly.test.js")], {
  stdio: "inherit",
  env: { ...process.env, QUAI_LIVE: "1" },
});
process.exit(result.status === null ? 1 : result.status);
