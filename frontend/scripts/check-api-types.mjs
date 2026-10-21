// Fails if lib/api/schema.d.ts is not exactly what openapi-typescript generates from
// ../backend/openapi.json. Run by CI, and by `pnpm check`. Fix with `pnpm gen:api`.
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const SPEC = "../backend/openapi.json";
const COMMITTED = "lib/api/schema.d.ts";
const dir = mkdtempSync(join(tmpdir(), "zolo-api-types-"));
const fresh = join(dir, "schema.d.ts");
try {
  execFileSync("pnpm", ["exec", "openapi-typescript", SPEC, "-o", fresh], { stdio: "pipe" });
  if (readFileSync(fresh, "utf8") !== readFileSync(COMMITTED, "utf8")) {
    console.error(
      `${COMMITTED} is stale: it no longer matches ${SPEC}.\n` +
        "The backend contract changed. Run `pnpm gen:api`, commit the result, and fix any type errors it reveals.",
    );
    process.exit(1);
  }
  console.log(`${COMMITTED} is up to date with ${SPEC}`);
} finally {
  rmSync(dir, { recursive: true, force: true });
}
