import { copyFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const web = resolve(dirname(fileURLToPath(import.meta.url)), "..");
copyFileSync(
  resolve(web, ".build-info.json"),
  resolve(web, "dist", "build-info.json"),
);
