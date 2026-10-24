import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import loopguard


class Guard(unittest.TestCase):
    def run_loop(self, exc):
        seen = []
        async def main():
            loop = asyncio.get_running_loop()
            loop.set_exception_handler(loopguard.handler)
            loop.default_exception_handler = lambda ctx: seen.append(ctx)   # what asyncio would print
            def boom():
                raise exc
            loop.call_soon(boom)
            await asyncio.sleep(0.05)
        asyncio.run(main())
        return seen

    def test_client_reset_is_dropped(self):
        self.assertEqual(self.run_loop(ConnectionResetError(10054, "forcibly closed")), [])
        self.assertEqual(self.run_loop(BrokenPipeError()), [])

    def test_real_errors_still_reach_asyncio(self):
        seen = self.run_loop(ValueError("real"))
        self.assertEqual(len(seen), 1)
        self.assertIsInstance(seen[0]["exception"], ValueError)


if __name__ == "__main__":
    unittest.main()
