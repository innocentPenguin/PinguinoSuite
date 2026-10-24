import io
import os
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


class Disconnect(unittest.TestCase):
    def _srv(self):
        s = server.Server.__new__(server.Server)
        return s

    def test_reset_is_one_line(self):
        server._drops.update(n=0, last=0.0)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            try:
                raise ConnectionResetError(10054, "reset")
            except ConnectionResetError:
                self._srv().handle_error(None, ("127.0.0.1", 1))
        self.assertIn("client dropped", out.getvalue())
        self.assertNotIn("Traceback", err.getvalue() + out.getvalue())

    def test_real_error_still_traced(self):
        err = io.StringIO()
        with redirect_stderr(err):
            try:
                raise ValueError("boom")
            except ValueError:
                self._srv().handle_error(None, ("127.0.0.1", 1))
        self.assertIn("ValueError", err.getvalue())




    def test_drops_are_rate_limited(self):
        server._drops.update(n=0, last=0.0)
        out = io.StringIO()
        with redirect_stdout(out):
            for _ in range(50):
                server.note_drop(ConnectionResetError(10054, "reset"))
        self.assertEqual(out.getvalue().count("client dropped"), 1)
        self.assertEqual(server._drops["n"], 49)

    def test_real_client_that_resets_leaves_no_traceback(self):
        import socket, struct, threading, time
        from http.server import ThreadingHTTPServer
        srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H)
        srv.daemon_threads = True
        srv.handle_error = lambda *a: server.Server.handle_error(srv, *a)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        server._drops.update(n=0, last=0.0)
        out, err = io.StringIO(), io.StringIO()
        try:
            with redirect_stdout(out), redirect_stderr(err):
                for half in (False, True):
                    c = socket.create_connection(("127.0.0.1", srv.server_address[1]))
                    if half:
                        c.sendall(b"GET /api/sounds HTTP/1.1\r\nHost: 127.0.0.1\r\n")        # request never finished
                    c.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))   # close sends RST
                    c.close()
                time.sleep(0.6)
        finally:
            srv.shutdown()
        self.assertNotIn("Traceback", out.getvalue() + err.getvalue())
        self.assertNotIn("ConnectionResetError:", err.getvalue())



if __name__ == "__main__":
    unittest.main()