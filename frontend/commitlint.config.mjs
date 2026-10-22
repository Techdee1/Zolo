// Conventional commits, with `a11y:` added because accessibility fixes are first-class here.
const config = {
  extends: ["@commitlint/config-conventional"],
  rules: {
    "type-enum": [
      2,
      "always",
      [
        "feat",
        "fix",
        "a11y",
        "docs",
        "style",
        "refactor",
        "perf",
        "test",
        "build",
        "ci",
        "chore",
        "revert",
      ],
    ],
    "header-max-length": [2, "always", 100],
  },
};

export default config;
