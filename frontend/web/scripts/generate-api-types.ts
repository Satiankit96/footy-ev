/**
 * Generates TypeScript types from the FastAPI OpenAPI schema.
 * Requires the API server to be running on localhost:8000.
 *
 * Usage: pnpm types:gen
 */
import openapiTS, { astToString } from "openapi-typescript";
import * as fs from "node:fs";
import * as path from "node:path";

const OPENAPI_URL = "http://localhost:8000/api/v1/openapi.json";
const OUTPUT_PATH = path.resolve(__dirname, "../lib/api/v1.gen.ts");

async function main(): Promise<void> {
  console.log(`Fetching OpenAPI schema from ${OPENAPI_URL}...`);
  const ast = await openapiTS(new URL(OPENAPI_URL));
  const content = `// AUTO-GENERATED — do not edit manually.\n// Regenerate with: pnpm types:gen\n// Source: ${OPENAPI_URL}\n\n${astToString(ast)}`;
  fs.mkdirSync(path.dirname(OUTPUT_PATH), { recursive: true });
  fs.writeFileSync(OUTPUT_PATH, content);
  console.log(`Written to ${OUTPUT_PATH}`);
}

main().catch((err: unknown) => {
  console.error(err);
  process.exit(1);
});
