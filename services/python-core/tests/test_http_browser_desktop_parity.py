from __future__ import annotations

import unittest

from tests.http_contract_helpers import (
    BRIDGE_FACTORY_PATH,
    DESKTOP_BRIDGE_PATH,
    HTTP_BRIDGE_PATH,
    extract_interface_methods,
    extract_return_object_methods,
    read_text,
)


class HttpBrowserDesktopParityPrepTests(unittest.TestCase):
    def test_bridge_factory_routes_every_runtime_to_http_bridge(self) -> None:
        factory_text = read_text(BRIDGE_FACTORY_PATH)
        self.assertIn("createHttpBridge", factory_text)

    def test_http_bridge_implements_entire_desktop_bridge_interface(self) -> None:
        desktop_methods = set(extract_interface_methods(DESKTOP_BRIDGE_PATH))
        http_methods = set(extract_return_object_methods(HTTP_BRIDGE_PATH, "return {"))
        self.assertEqual(http_methods, desktop_methods)

    def test_audio_file_urls_use_http_runtime_in_browser_and_tauri(self) -> None:
        audio_file_text = read_text(HTTP_BRIDGE_PATH.parent / "audioFile.ts")
        self.assertIn("/api/v1/artifacts/audio", audio_file_text)
        self.assertNotIn("convertFileSrc", audio_file_text)
        self.assertNotIn("__TAURI_INTERNALS__", audio_file_text)

    def test_http_bridge_has_browser_compatible_unavailable_message(self) -> None:
        http_text = read_text(HTTP_BRIDGE_PATH)
        self.assertIn("local HTTP runtime", http_text)
        self.assertNotIn("plain Vite in a browser has no Python/LLM bridge", http_text)


if __name__ == "__main__":
    unittest.main()
