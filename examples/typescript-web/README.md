# TypeScript web example

This small browser app accepts a name and displays a greeting using `textContent`. The pure validator has strict TypeScript types and `node:test` regressions for blank names and markup-shaped input. The page has an associated label, an `aria-live` result and visible focus styling. Inspect its actual UI in a browser before claiming visual or accessibility proof.

Node >=20 is required for this example's test runner. TypeScript **5.9.3** is an optional example development tool; it is not a Software Factory runtime dependency. In a copied example directory, acquire it locally and build:

```sh
npm install --no-save --package-lock=false typescript@5.9.3
npm run build
npm test
python3 -m http.server 8766 --bind 127.0.0.1
```

Open `http://127.0.0.1:8766/` in a browser while the owned server runs, submit a normal and an empty name, then stop the server. `npm install` can use the network/cache and writes ignored `node_modules`; no global install is needed. `npm run build` writes ignored `dist/`. `npm test` proves the pure contract and DOM adapter with a small synthetic document; it does not establish browser rendering or native accessibility behavior.

The project [principles](PRINCIPLES.md), [architecture](ARCHITECTURE.md), [conventions](CONVENTIONS.md), [risk](RISK.md) and [tasks](TASKS.md) are setup sources. `factory.config.draft.json` is illustrative only. Copy before [installing the factory](../../docs/quickstart.md); no example signoff grants a real delivery GO.
