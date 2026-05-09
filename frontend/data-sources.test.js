const assert = require("node:assert/strict");
const {
  buildDataPath,
  buildAlgorithmOptions,
  buildSourceLabel,
} = require("./data-sources.js");

function runTest(name, fn) {
  try {
    fn();
    console.log(`PASS ${name}`);
  } catch (error) {
    console.error(`FAIL ${name}`);
    throw error;
  }
}

runTest("buildDataPath resolves latest result under algorithm folder", () => {
  assert.equal(buildDataPath("improved", "latest"), "data/improved/result.json");
});

runTest("buildDataPath resolves sample scenario under algorithm folder", () => {
  assert.equal(buildDataPath("original", "2"), "data/original/scenario-2.json");
});

runTest("buildAlgorithmOptions prefers manifest variants and falls back to defaults", () => {
  assert.deepEqual(
    buildAlgorithmOptions({ variants: [{ key: "improved" }, { key: "original" }] }),
    [
      { key: "improved", label: "improved" },
      { key: "original", label: "original" },
    ],
  );
  assert.deepEqual(buildAlgorithmOptions(null), [
    { key: "improved", label: "improved" },
    { key: "original", label: "original" },
    { key: "ga", label: "ga" },
    { key: "sa", label: "sa" },
  ]);
});

runTest("buildAlgorithmOptions orders known algorithms by comparison priority", () => {
  assert.deepEqual(
    buildAlgorithmOptions({
      variants: [
        { key: "ga" },
        { key: "improved" },
        { key: "original" },
        { key: "sa" },
      ],
    }),
    [
      { key: "improved", label: "improved" },
      { key: "original", label: "original" },
      { key: "ga", label: "ga" },
      { key: "sa", label: "sa" },
    ],
  );
});

runTest("buildSourceLabel returns human readable labels", () => {
  assert.equal(buildSourceLabel("latest"), "最后运行结果");
  assert.equal(buildSourceLabel("3"), "示例场景 3");
});

console.log("All frontend data source tests passed.");
