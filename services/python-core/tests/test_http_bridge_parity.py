from __future__ import annotations

import unittest

from tests.http_contract_helpers import (
    HTTP_BRIDGE_CONTRACTS,
    HTTP_BRIDGE_PATH,
    HTTP_RUNTIME_PATH,
    CLI_PARSER_PATH,
    MAIN_PATH,
    extract_interface_methods,
    extract_return_object_methods,
    read_text,
)


class HttpBridgeParityTests(unittest.TestCase):
    def test_contract_matrix_covers_all_36_bridge_methods(self) -> None:
        self.assertEqual(len(HTTP_BRIDGE_CONTRACTS), 36)
        self.assertEqual(len({contract.desktop_method for contract in HTTP_BRIDGE_CONTRACTS}), 36)
        self.assertEqual(len({(contract.http_method, contract.http_path) for contract in HTTP_BRIDGE_CONTRACTS}), 36)

    def test_contract_matrix_matches_desktop_bridge_interface(self) -> None:
        contract_methods = {contract.desktop_method for contract in HTTP_BRIDGE_CONTRACTS}
        desktop_methods = set(extract_interface_methods())
        self.assertEqual(contract_methods, desktop_methods)

    def test_http_bridge_implements_contract_matrix(self) -> None:
        contract_methods = {contract.desktop_method for contract in HTTP_BRIDGE_CONTRACTS}
        bridge_methods = set(extract_return_object_methods(HTTP_BRIDGE_PATH, "return {"))
        self.assertEqual(contract_methods, bridge_methods)

    def test_cli_flags_and_infer_operation_returns_stay_in_sync(self) -> None:
        main_text = read_text(MAIN_PATH)
        cli_text = main_text + "\n" + read_text(CLI_PARSER_PATH)
        infer_operation_returns = {
            line.split('return "', 1)[1].split('"', 1)[0]
            for line in main_text.splitlines()
            if 'return "' in line
        }
        for contract in HTTP_BRIDGE_CONTRACTS:
            with self.subTest(method=contract.desktop_method):
                self.assertIn(contract.cli_args[0], cli_text)
                self.assertIn(contract.operation, infer_operation_returns)

    def test_stream_contract_preserves_existing_chunk_marker_and_operation(self) -> None:
        stream_contract = next(contract for contract in HTTP_BRIDGE_CONTRACTS if contract.desktop_method == "submitReplyStream")
        self.assertTrue(stream_contract.streaming)
        self.assertEqual(stream_contract.operation, "submit_reply")

        http_runtime_text = read_text(HTTP_RUNTIME_PATH)
        http_bridge_text = read_text(HTTP_BRIDGE_PATH)
        self.assertIn('_write_sse_event("chunk"', http_runtime_text)
        self.assertIn("/interview:reply-stream", http_bridge_text)
        self.assertIn("submitReplyStream", http_bridge_text)


if __name__ == "__main__":
    unittest.main()
