# Minimal local project

This tiny project reads one name and prints a greeting. It has no external dependencies, bots or monitoring. The Markdown documents are selected examples of product, architecture, conventions, risk and tasks; `factory.config.draft.json` is a **draft**, not installed configuration or owner signoff.

```sh
python3 -B greet.py Ada
python3 -B -m unittest discover -s tests -v
```

Expected greeting: `Hello, Ada.` The test also covers the default name and empty-input refusal. From a trusted factory checkout, set `SF_PROJECT` to a fresh copy of this directory and follow [the full local installation](../../docs/quickstart.md) with `--skip-bmad`; review the dry-run before applying. [TASKS.md](TASKS.md) is an illustrative planning source. A full BMad-planned lap needs actually available BMad skills and reviewed structured stories; this `--skip-bmad` smoke does not provide them. Existing README and [CONVENTIONS.md](CONVENTIONS.md) should retain their exact bytes. A real lap still needs its own approved eval plan, independent review, integration/effect proof and applicable owner decision or delegated epic acceptance. Optional access remains unknown until observed.
