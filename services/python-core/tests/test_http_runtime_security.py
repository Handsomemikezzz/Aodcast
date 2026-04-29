from __future__ import annotations

import unittest

from tests.http_contract_helpers import (
    HTTP_BRIDGE_CONTRACTS,
    LOOPBACK_ONLY_HOSTS,
    RUNTIME_TOKEN_HEADER,
)


class HttpRuntimeSecurityPrepTests(unittest.TestCase):
    def test_loopback_and_runtime_token_constants_are_explicit(self) -> None:
        self.assertEqual(RUNTIME_TOKEN_HEADER, "X-AOD-Runtime-Token")
        self.assertEqual(set(LOOPBACK_ONLY_HOSTS), {"127.0.0.1", "::1"})

    def test_public_bridge_contract_excludes_admin_and_bootstrap_routes(self) -> None:
        for contract in HTTP_BRIDGE_CONTRACTS:
            with self.subTest(method=contract.desktop_method):
                self.assertFalse(contract.http_path.startswith("/admin/"))
                self.assertNotIn("bootstrap", contract.http_path)

    def test_config_routes_stay_explicit_instead_of_wildcard_patterns(self) -> None:
        config_routes = {
            (contract.http_method, contract.http_path)
            for contract in HTTP_BRIDGE_CONTRACTS
            if contract.http_path.startswith("/api/v1/config/")
        }
        self.assertEqual(
            config_routes,
            {
                ("GET", "/api/v1/config/llm"),
                ("PUT", "/api/v1/config/llm"),
                ("GET", "/api/v1/config/llm/preflight"),
                ("GET", "/api/v1/config/tts"),
                ("PUT", "/api/v1/config/tts"),
            },
        )
        self.assertTrue(all("*" not in path for _, path in config_routes))


if __name__ == "__main__":
    unittest.main()
