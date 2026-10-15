"""Small loopback JSON handler with a pure formatting contract."""
from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def format_payload(value: object) -> dict[str, str]:
    if not isinstance(value, dict) or not isinstance(value.get("name"), str):
        raise TypeError("name must be a nonempty string")
    name = value["name"].strip()
    if not name:
        raise ValueError("name must be a nonempty string")
    return {"message": f"Hello, {name}."}


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        if self.path != "/format":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 4096:
                raise ValueError("invalid body length")
            value = json.loads(self.rfile.read(length))
            response = format_payload(value)
            status = 200
        except (TypeError, ValueError, json.JSONDecodeError):
            response = {"error": "name must be a nonempty string"}
            status = 400
        encoded = json.dumps(response, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, _format: str, *_args: object) -> None:
        return


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--once", metavar="JSON")
    group.add_argument("--serve", metavar="HOST:PORT")
    args = parser.parse_args()
    if args.once is not None:
        try:
            print(json.dumps(format_payload(json.loads(args.once)), separators=(",", ":")))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            print(json.dumps({"error": str(exc)}, separators=(",", ":")))
            return 2
        return 0
    host, _, port = args.serve.rpartition(":")
    if host not in {"127.0.0.1", "localhost"}:
        parser.error("serve only on loopback")
    with ThreadingHTTPServer((host, int(port)), Handler) as server:
        server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
