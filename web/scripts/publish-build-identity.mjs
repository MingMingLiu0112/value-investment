import { copyFileSync, readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const web = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const identity = JSON.parse(
  readFileSync(resolve(web, ".build-info.json"), "utf8"),
);
const bundles = readdirSync(resolve(web, "dist")).filter((name) =>
  name.endsWith(".js"),
);
if (
  !identity.commit ||
  !bundles.some((name) =>
    readFileSync(resolve(web, "dist", name), "utf8").includes(identity.commit),
  )
) {
  throw new Error(
    "Web build identity was not embedded in the served JavaScript",
  );
}
copyFileSync(
  resolve(web, ".build-info.json"),
  resolve(web, "dist", "build-info.json"),
);
