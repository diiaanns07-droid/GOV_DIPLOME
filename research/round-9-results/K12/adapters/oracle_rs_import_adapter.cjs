// K12 r9 SELF-TEST adapter: the K12 Python oracle behind the resilience import interface of resilience_stress.cjs.
// It exists only to prove that the harness and the corpus labels work end to end. A PASS here is NOT a test of BUILD.
// Snapshot placeholders are kept as is ("__SNAPSHOT__" = current slice), because the oracle validates against them.
"use strict";
const path = require("path");
const { spawnSync } = require("child_process");
module.exports = function ({ appRoot }) {
  const ORACLE = path.join(__dirname, "..", "oracle", "resilience_oracle.py");
  const py = process.env.K12_PYTHON || "python3";
  const call = (mode, text) => {
    const r = spawnSync(py, [ORACLE, "--app-root", appRoot, "--stdin", mode], { input: Buffer.from(text, "utf8"), encoding: "utf8", timeout: 60000 });
    if (r.status !== 0) throw new Error("oracle failed: " + String(r.stderr).slice(0, 200));
    return JSON.parse(r.stdout);
  };
  return {
    name: "k12-oracle-selftest (not BUILD)",
    selfTest: true,
    snapshot: (city, current) => (current ? "__SNAPSHOT__" : "__SNAPSHOT_OTHER_CITY__"),
    initialState: () => ({ envelope: null }),
    importEnvelope(text, state) {
      const r = call("validate", text);
      return r.ok ? { ok: true, code: null, state: { envelope: JSON.parse(text.replace(/^﻿/, "")), text } } : { ok: false, code: r.code, state };
    },
    optimize(state) { return call("solve", state.text).result; },
  };
};
