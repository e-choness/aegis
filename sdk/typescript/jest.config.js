/** @type {import('jest').Config} */
module.exports = {
  preset: "ts-jest",
  testEnvironment: "node",
  testMatch: ["**/tests/**/*.test.ts"],
  globals: {
    "ts-jest": {
      tsconfig: {
        target: "ES2020",
        module: "commonjs",
        strict: true,
        esModuleInterop: true,
      },
    },
  },
};
