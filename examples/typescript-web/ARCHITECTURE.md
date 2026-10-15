# Architecture

`src/app.ts` contains a pure validator and a small DOM adapter. The browser loads the compiled ES2022 module from `dist/`. `node:test` checks the pure contract and synthetic text-content assignment. A local HTTP server is only a preview surface; browser interaction must be observed separately.
