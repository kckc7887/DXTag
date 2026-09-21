import { cpSync, mkdirSync, existsSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const engineDest = join(root, "web", "public", "engine");
const dataDest = join(root, "web", "public", "data");
mkdirSync(engineDest, { recursive: true });
mkdirSync(dataDest, { recursive: true });

for (const name of ["maimai_analyzer.py", "catalog.py", "community.py", "calibrate.py"]) {
  cpSync(join(root, name), join(engineDest, name));
}

const dataDir = join(root, "data");
if (existsSync(dataDir)) {
  for (const name of readdirSync(dataDir)) {
    if (name.endsWith(".json") && name !== "ingest_failures.json") {
      cpSync(join(dataDir, name), join(dataDest, name));
    }
  }
}

console.log("copied engine + data snapshots into web/public");
