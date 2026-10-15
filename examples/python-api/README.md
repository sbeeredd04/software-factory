# Python API example

This standalone standard-library project exposes `POST /format` on loopback. It accepts a JSON object with a nonempty string `name` and returns a JSON greeting. Invalid types, malformed JSON and incomplete bodies receive a 400 response; a body that exceeds the one-second read deadline receives 408 and closes. Bodies are capped at 4,096 bytes; unknown paths receive 404. The handler and tests are real application behavior. A healthy HTTP status alone is not the assertion: check the response body and invalid path too.

```sh
python3 -B -m unittest discover -s tests -v
python3 -B app.py --once '{"name":"Ada"}'
python3 -B app.py --once '{"name":null}'
```

The first one-shot response is `{"message":"Hello, Ada."}` with exit 0. The invalid input prints `{"error":"name must be a nonempty string"}` and exits 2. Unit tests start and stop their own bounded loopback HTTP server; no external network access is needed. For manual HTTP use, `python3 -B app.py --serve 127.0.0.1:8765` runs until interrupted; bind only a chosen local port and stop the owned process afterward.

[PRINCIPLES](PRINCIPLES.md), [ARCHITECTURE](ARCHITECTURE.md), [CONVENTIONS](CONVENTIONS.md), [RISK](RISK.md) and [TASKS](TASKS.md) ground a factory lap. `factory.config.draft.json` is illustrative only. Copy the project before [installing locally](../../docs/installation.md); the real host must review an exact setup/eval proposal. A source test does not prove host loading, integration, deployment or human acceptance.
