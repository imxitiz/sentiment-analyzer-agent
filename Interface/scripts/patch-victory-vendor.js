/**
 * Patches victory-vendor/es/d3-scale.js for Bun compatibility.
 *
 * Problem: Bun's bundler doesn't properly resolve `export * from "d3-scale"`
 * when d3-scale uses `export { default as scaleFn }` style re-exports.
 * This causes `d3Scales[name] is not a function` at runtime.
 *
 * Fix: Replace the wildcard re-export with explicit named imports/exports.
 * Runs automatically via `postinstall` in package.json.
 */

import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { join } from "node:path";

const TARGET = join(
  import.meta.dirname,
  "..",
  "node_modules",
  "victory-vendor",
  "es",
  "d3-scale.js",
);

if (!existsSync(TARGET)) {
  console.log("[patch] victory-vendor/es/d3-scale.js not found — skipping");
  process.exit(0);
}

const current = readFileSync(TARGET, "utf-8");

// Only patch if it still has the problematic wildcard export
if (!current.includes('export * from "d3-scale"')) {
  console.log("[patch] victory-vendor/es/d3-scale.js already patched — skipping");
  process.exit(0);
}

const patched = `// Patched for Bun compatibility — explicit named exports instead of wildcard.
// Original: export * from "d3-scale";
// See: scripts/patch-victory-vendor.js

export {
  scaleBand,
  scalePoint,
  scaleIdentity,
  scaleLinear,
  scaleLog,
  scaleSymlog,
  scaleOrdinal,
  scaleImplicit,
  scalePow,
  scaleSqrt,
  scaleRadial,
  scaleQuantile,
  scaleQuantize,
  scaleThreshold,
  scaleTime,
  scaleUtc,
  scaleSequential,
  scaleSequentialLog,
  scaleSequentialPow,
  scaleSequentialSqrt,
  scaleSequentialSymlog,
  scaleSequentialQuantile,
  scaleDiverging,
  scaleDivergingLog,
  scaleDivergingPow,
  scaleDivergingSqrt,
  scaleDivergingSymlog,
  tickFormat,
} from "d3-scale";
`;

writeFileSync(TARGET, patched, "utf-8");
console.log("[patch] victory-vendor/es/d3-scale.js patched for Bun ✓");
