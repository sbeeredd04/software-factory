import http.client
import json
import socket
import threading
import time
import unittest
from http.server import ThreadingHTTPServer

from app import BODY_DEADLINE_SECONDS, Handler, format_payload


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

    def test_incomplete_and_slow_request_bodies(self):
        with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                for body, close_write, expected in ((b'{"', True, b"400"),
                                                     (b'{', False, b"408")):
                    with self.subTest(close_write=close_write), socket.create_connection(
                            ("127.0.0.1", server.server_port), timeout=3) as client:
                        client.settimeout(3)
                        client.sendall(b"POST /format HTTP/1.1\r\nHost: 127.0.0.1\r\n"
                                       b"Content-Length: 15\r\nConnection: close\r\n\r\n" + body)
                        if close_write:
                            client.shutdown(socket.SHUT_WR)
                        began = time.monotonic()
                        reply = client.recv(4096)
                        self.assertIn(expected, reply.split(b"\r\n", 1)[0])
                        self.assertLess(time.monotonic() - began, BODY_DEADLINE_SECONDS + 1)
            finally:
                server.shutdown()
                worker.join(timeout=3)
                self.assertFalse(worker.is_alive())
