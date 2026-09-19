import { spawnSync } from "node:child_process";
import { rmSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const mode = process.argv[2] === "start" ? "start" : "dev";
const clean = process.argv.includes("--clean");
const extra = process.argv.slice(3).filter((arg) => arg !== "--clean");
if (clean) rmSync(resolve(root, ".next"), { recursive: true, force: true });
const require = createRequire(import.meta.url);
const result = spawnSync(
  process.execPath,
  [require.resolve("next/dist/bin/next"), mode, "--port", process.env.PORT || "3000", ...extra],
  { cwd: root, stdio: "inherit", windowsHide: true },
);
if (result.error) console.error(result.error.message);
process.exit(result.status ?? 1);
