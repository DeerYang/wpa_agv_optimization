(function (globalScope) {
  const DEFAULT_ALGORITHMS = [
    { key: "improved", label: "improved" },
    { key: "original", label: "original" },
    { key: "ga", label: "ga" },
    { key: "sa", label: "sa" },
  ];
  const ALGORITHM_ORDER = new Map(DEFAULT_ALGORITHMS.map((item, index) => [item.key, index]));

  function buildDataPath(algorithmKey, sourceKey) {
    if (sourceKey === "latest") {
      return `data/${algorithmKey}/result.json`;
    }
    return `data/${algorithmKey}/scenario-${sourceKey}.json`;
  }

  function buildAlgorithmOptions(manifest) {
    const variants = manifest?.variants;
    if (!Array.isArray(variants) || variants.length === 0) {
      return DEFAULT_ALGORITHMS;
    }
    return variants
      .filter((item) => item && item.key)
      .map((item) => ({ key: item.key, label: item.label || item.key }))
      .sort((left, right) => {
        const leftOrder = ALGORITHM_ORDER.get(left.key) ?? Number.MAX_SAFE_INTEGER;
        const rightOrder = ALGORITHM_ORDER.get(right.key) ?? Number.MAX_SAFE_INTEGER;
        if (leftOrder !== rightOrder) return leftOrder - rightOrder;
        return left.key.localeCompare(right.key);
      });
  }

  function buildSourceLabel(sourceKey) {
    return sourceKey === "latest" ? "最后运行结果" : `示例场景 ${sourceKey}`;
  }

  const api = {
    buildAlgorithmOptions,
    buildDataPath,
    buildSourceLabel,
    DEFAULT_ALGORITHMS,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  globalScope.DataSourceUtils = api;
})(typeof window !== "undefined" ? window : globalThis);
