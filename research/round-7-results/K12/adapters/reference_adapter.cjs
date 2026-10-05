// Adapter for the K12 reference importer (reference/whatif_import_ref.cjs). sha256hex comes from the app's own facts.js.
"use strict";
const path = require("path");
module.exports = function ({ D, requireWeb }) {
  const F = requireWeb("facts.js");
  const { makeImporter } = require(path.join(__dirname, "..", "reference", "whatif_import_ref.cjs"));
  const imp = makeImporter({ D, sha256hex: F.sha256hex });
  return { name: "k12-reference", snapshot: imp.snapshot, initialState: imp.initialState,
           importScenario: imp.importScenario, compute: imp.compute,
           exportScenario: imp.exportScenario };
};
