import { execFileSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const web = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const root = resolve(web, "..");
function git(args) {
  try {
    return execFileSync("git", args, { cwd: root, encoding: "utf8" }).trim();
  } catch {
    return null;
  }
}
const identity = {
  schema_version: "web-build-identity-v1",
  commit: git(["rev-parse", "HEAD"]),
  built_at: new Date().toISOString(),
  source_dirty: Boolean(
    git([
      "status",
      "--porcelain",
      "--",
      "web/src",
      "web/.umirc.ts",
      "web/scripts",
      "web/package.json",
    ]),
  ),
};
writeFileSync(
  resolve(web, ".build-info.json"),
  `${JSON.stringify(identity)}\n`,
  "utf8",
);
