# Fixture: typescript-web

A tiny TypeScript app used by the crawl tests for the documented best-effort
lexical treatment. Expected findings:

- Files: `src/index.ts`, `src/greet.ts`, `src/cli.ts`.
- Import specifiers: `src/index.ts` imports `./greet`; `src/cli.ts` imports
  `./index`.
- Exported names: `main` (index), `greet` (greet).
- Entry points from `package.json`: `main` (`src/index.ts`) and `bin`
  (`fixture-web` -> `src/cli.ts`).
