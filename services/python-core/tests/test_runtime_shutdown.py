from __future__ import annotations

import signal
import unittest

from app.api.http_runtime import install_runtime_stop_handlers


class RuntimeShutdownTests(unittest.TestCase):
    def test_sigterm_handler_stops_once_and_restores_previous_handlers(self) -> None:
        previous = signal.getsignal(signal.SIGTERM)
        stopped: list[bool] = []
        restore = install_runtime_stop_handlers(on_stop=lambda: stopped.append(True))
        try:
            signal.raise_signal(signal.SIGTERM)
            signal.raise_signal(signal.SIGTERM)
            self.assertEqual(stopped, [True])
        finally:
            restore()
        self.assertEqual(signal.getsignal(signal.SIGTERM), previous)


if __name__ == "__main__":
    unittest.main()
