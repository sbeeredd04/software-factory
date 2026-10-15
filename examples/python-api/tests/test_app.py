import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer

from app import Handler, format_payload


class ApiTests(unittest.TestCase):
    def test_pure_contract(self):
        self.assertEqual(format_payload({"name": " Ada "}), {"message": "Hello, Ada."})
        for invalid in (None, {"name": None}, {"name": "  "}, []):
            with self.subTest(invalid=invalid), self.assertRaises((TypeError, ValueError)):
                format_payload(invalid)

    def test_loopback_http(self):
        with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
                conn.request("POST", "/format", '{"name":"Ada"}', {"Content-Type": "application/json"})
                response = conn.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(json.loads(response.read()), {"message": "Hello, Ada."})
                conn.request("POST", "/format", '{"name":null}', {"Content-Type": "application/json"})
                response = conn.getresponse()
                self.assertEqual(response.status, 400)
                self.assertEqual(json.loads(response.read()), {"error": "name must be a nonempty string"})
                conn.close()
            finally:
                server.shutdown()
                worker.join(timeout=3)
