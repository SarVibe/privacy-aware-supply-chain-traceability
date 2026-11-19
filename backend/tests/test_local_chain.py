import http.client
import json
import threading
import unittest
from unittest.mock import patch

from eth_account import Account
from http.server import ThreadingHTTPServer
from web3 import Web3
from web3.exceptions import ContractLogicError

from backend.app.auth import hash_password, load_users, verify_password
from backend.app.local_chain import LocalChain, make_web_handler
from backend.scripts.add_sample_data import (
    prompt_secret,
    sample_commitment,
)


class LocalChainBatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.chain = LocalChain(reset=True)
        self.accounts = self.chain.accounts
        self.keys = self.chain.account_keys

    def tearDown(self) -> None:
        self.chain.close()

    def _submit_signed(
        self,
        sender_index: int,
        nonce: int,
        to: str,
        data: str,
        transaction_type: int = 2,
        gas: int = 300_000,
    ) -> str:
        transaction = {
            "chainId": self.chain.web3.eth.chain_id,
            "nonce": nonce,
            "gas": gas,
            "to": to,
            "value": 0,
            "data": data,
        }
        if transaction_type == 2:
            transaction.update(
                {
                    "maxFeePerGas": 2_000_000_000,
                    "maxPriorityFeePerGas": 1_000_000_000,
                    "type": 2,
                    "accessList": [],
                }
            )
        else:
            transaction["gasPrice"] = 1_000_000_000
        signed = Account.sign_transaction(
            transaction, self.keys[sender_index]
        )
        return self.chain._queue_raw_transaction(
            Web3.to_hex(signed.raw_transaction)
        )

    def test_two_independent_registrations_wait_then_mine_together(self) -> None:
        role_data = self.chain.contract.functions.setStakeholderRole(
            self.accounts[1], 1
        )._encode_transaction_data()
        self._submit_signed(
            0,
            self.chain.web3.eth.get_transaction_count(self.accounts[0]),
            self.chain.contract_address,
            role_data,
        )
        self.chain.process_pending()
        self.assertEqual(
            self.chain.contract.functions.stakeholderRoles(
                self.accounts[1]
            ).call(),
            1,
        )

        self.chain.configure_batch_size(2)
        initial_block = self.chain.web3.eth.block_number
        first_data = self.chain.contract.functions.registerProduct(
            "0x" + "0" * 61 + "101"
        )._encode_transaction_data()
        second_data = self.chain.contract.functions.registerProduct(
            "0x" + "0" * 61 + "102"
        )._encode_transaction_data()
        nonce = self.chain.web3.eth.get_transaction_count(self.accounts[1])
        first_hash = self._submit_signed(
            1, nonce, self.chain.contract_address, first_data
        )

        self.chain.process_pending()
        self.assertEqual(self.chain.status()["pendingCount"], 1)
        self.assertEqual(self.chain.web3.eth.block_number, initial_block)

        second_hash = self._submit_signed(
            1, nonce + 1, self.chain.contract_address, second_data
        )
        self.chain.process_pending()

        status = self.chain.status()
        self.assertEqual(status["pendingCount"], 0)
        self.assertEqual(status["lastBlock"]["registrationCount"], 2)
        self.assertEqual(status["lastBlock"]["transactionCount"], 2)
        self.assertEqual(
            set(status["lastBlock"]["transactionHashes"]),
            {first_hash, second_hash},
        )
        first_receipt = self.chain.web3.eth.get_transaction_receipt(first_hash)
        second_receipt = self.chain.web3.eth.get_transaction_receipt(second_hash)
        self.assertEqual(first_receipt["status"], 1)
        self.assertEqual(second_receipt["status"], 1)
        self.assertEqual(first_receipt["blockNumber"], second_receipt["blockNumber"])

    def test_qgram_registration_is_batched_and_emits_search_data(self) -> None:
        role_data = self.chain.contract.functions.setStakeholderRole(
            self.accounts[1], 1
        )._encode_transaction_data()
        self._submit_signed(
            0,
            self.chain.web3.eth.get_transaction_count(self.accounts[0]),
            self.chain.contract_address,
            role_data,
        )
        self.chain.process_pending()
        self.chain.configure_batch_size(2)

        qgram_hashes = [
            Web3.keccak(text="tri"),
            Web3.keccak(text="rig"),
            Web3.keccak(text="ram"),
        ]
        register = self.chain.contract.get_function_by_signature(
            "registerProduct(bytes32,bytes32[])"
        )
        nonce = self.chain.web3.eth.get_transaction_count(self.accounts[1])
        transaction_hashes = []
        for sample_number in (1, 2):
            calldata = register(
                Web3.to_hex(sample_commitment("qgram-test", sample_number)),
                qgram_hashes,
            )._encode_transaction_data()
            transaction_hashes.append(
                self._submit_signed(
                    1,
                    nonce + sample_number - 1,
                    self.chain.contract_address,
                    calldata,
                    gas=1_000_000,
                )
            )

        self.chain.process_pending()

        self.assertEqual(self.chain.status()["pendingCount"], 0)
        receipt = self.chain.web3.eth.get_transaction_receipt(transaction_hashes[0])
        qgram_event = next(
            log
            for log in receipt["logs"]
            if Web3.to_hex(log["topics"][0]).lower()
            == self.chain.contract.events.ProductQgrams().topic.lower()
        )
        decoded_event = self.chain.contract.events.ProductQgrams().process_log(
            qgram_event
        )
        self.assertEqual(decoded_event["args"]["bloomGroup"], 1)
        self.assertEqual(
            decoded_event["args"]["blockNumber"],
            receipt["blockNumber"],
        )
        self.assertEqual(
            list(decoded_event["args"]["qgramHashes"]),
            qgram_hashes,
        )

    def test_block_qgram_bloom_screen_returns_only_blocks_meeting_overlap(self) -> None:
        role_data = self.chain.contract.functions.setStakeholderRole(
            self.accounts[1], 1
        )._encode_transaction_data()
        self._submit_signed(
            0,
            self.chain.web3.eth.get_transaction_count(self.accounts[0]),
            self.chain.contract_address,
            role_data,
        )
        self.chain.process_pending()
        self.chain.configure_batch_size(2)
        query_qgrams = [
            Web3.keccak(text="query-qgram-one"),
            Web3.keccak(text="query-qgram-two"),
        ]
        unrelated_qgrams = [
            Web3.keccak(text=f"unrelated-qgram-{index}")
            for index in range(1, 10)
        ]
        occupied_bits = {
            int.from_bytes(value, "big") % 8192
            for value in query_qgrams
        }
        self.assertTrue(
            all(
                int.from_bytes(value, "big") % 8192 not in occupied_bits
                for value in unrelated_qgrams
            )
        )

        register = self.chain.contract.get_function_by_signature(
            "registerProduct(bytes32,bytes32[])"
        )
        first_qgram_block = self.chain.web3.eth.block_number + 1
        nonce = self.chain.web3.eth.get_transaction_count(self.accounts[1])
        for index in range(20):
            if index == 0:
                qgrams = query_qgrams
            elif index == 10:
                qgrams = [query_qgrams[0]]
            elif index > 10:
                qgrams = [unrelated_qgrams[index - 11]]
            else:
                qgrams = []
            calldata = register(
                sample_commitment("qgram-bloom-screen", index + 1),
                qgrams,
            )._encode_transaction_data()
            self._submit_signed(
                1,
                nonce + index,
                self.chain.contract_address,
                calldata,
                gas=1_000_000,
            )
            self.chain.process_pending()

        candidate_blocks, total_blocks = (
            self.chain.contract.functions.getQgramCandidateBlocks(
                query_qgrams, 2, 0, 16
            ).call()
        )
        self.assertEqual(total_blocks, 6)
        self.assertEqual(candidate_blocks, [first_qgram_block])
        later_blocks, later_total = (
            self.chain.contract.functions.getQgramCandidateBlocks(
                query_qgrams, 2, 1, 1
            ).call()
        )
        self.assertEqual(later_total, 6)
        self.assertEqual(later_blocks, [])
        block_topics = [
            Web3.to_hex(self.chain.web3.codec.encode(["uint256"], [first_qgram_block])),
            Web3.to_hex(
                self.chain.web3.codec.encode(
                    ["uint256"], [first_qgram_block + 5]
                )
            ),
        ]
        qgram_logs = self.chain.web3.eth.get_logs(
            {
                "address": self.chain.contract_address,
                "fromBlock": 0,
                "toBlock": "latest",
                "topics": [
                    self.chain.contract.events.ProductQgrams().topic,
                    None,
                    None,
                    block_topics,
                ],
            }
        )
        self.assertEqual(len(qgram_logs), 3)

    def test_fuzzy_threshold_is_admin_configurable_and_defaults_to_ninety(self) -> None:
        self.assertEqual(
            self.chain.contract.functions.fuzzyThresholdPercent().call(), 90
        )
        for invalid_threshold in (0, 101):
            with self.subTest(invalid_threshold=invalid_threshold):
                with self.assertRaises(ContractLogicError):
                    self.chain.contract.functions.setFuzzyThresholdPercent(
                        invalid_threshold
                    ).call({"from": self.accounts[0]})

        calldata = self.chain.contract.functions.setFuzzyThresholdPercent(
            85
        )._encode_transaction_data()
        self._submit_signed(
            0,
            self.chain.web3.eth.get_transaction_count(self.accounts[0]),
            self.chain.contract_address,
            calldata,
        )
        self.chain.process_pending()
        self.assertEqual(
            self.chain.contract.functions.fuzzyThresholdPercent().call(), 85
        )

    def test_manufacturer_and_distributor_can_update_shared_fuzzy_threshold(self) -> None:
        self.chain.configure_batch_size(2)
        admin_nonce = self.chain.web3.eth.get_transaction_count(self.accounts[0])
        for index in (1, 2):
            calldata = self.chain.contract.functions.setStakeholderRole(
                self.accounts[index], index
            )._encode_transaction_data()
            self._submit_signed(
                0,
                admin_nonce + index - 1,
                self.chain.contract_address,
                calldata,
            )
        self.chain.process_pending()

        with self.assertRaisesRegex(ContractLogicError, "Authorized stakeholder"):
            self.chain.contract.functions.setFuzzyThresholdPercent(80).call(
                {"from": self.accounts[3]}
            )

        manufacturer_call = self.chain.contract.functions.setFuzzyThresholdPercent(80)
        distributor_call = self.chain.contract.functions.setFuzzyThresholdPercent(75)
        manufacturer_call.call({"from": self.accounts[1]})
        distributor_call.call({"from": self.accounts[2]})
        for index, function in ((1, manufacturer_call), (2, distributor_call)):
            calldata = function._encode_transaction_data()
            self._submit_signed(
                index,
                self.chain.web3.eth.get_transaction_count(self.accounts[index]),
                self.chain.contract_address,
                calldata,
            )
        self.chain.process_pending()

        self.assertEqual(
            self.chain.contract.functions.fuzzyThresholdPercent().call(), 75
        )

    def test_ten_type_two_registrations_mine_as_one_batch(self) -> None:
        role_data = self.chain.contract.functions.setStakeholderRole(
            self.accounts[1], 1
        )._encode_transaction_data()
        role_hash = self._submit_signed(
            0,
            self.chain.web3.eth.get_transaction_count(self.accounts[0]),
            self.chain.contract_address,
            role_data,
        )
        self.chain.process_pending()
        self.assertEqual(
            self.chain.web3.eth.get_transaction_receipt(role_hash)["status"], 1
        )

        self.chain.configure_batch_size(10)
        nonce = self.chain.web3.eth.get_transaction_count(self.accounts[1])
        hashes = []
        for sample_number in range(1, 11):
            calldata = self.chain.contract.functions.registerProduct(
                Web3.to_hex(sample_commitment("batch-test", sample_number))
            )._encode_transaction_data()
            hashes.append(
                self._submit_signed(
                    1,
                    nonce + sample_number - 1,
                    self.chain.contract_address,
                    calldata,
                )
            )

        self.chain.process_pending()

        status = self.chain.status()
        self.assertEqual(status["pendingCount"], 0)
        self.assertEqual(status["lastBlock"]["registrationCount"], 10)
        self.assertEqual(set(status["lastBlock"]["transactionHashes"]), set(hashes))
        receipts = [
            self.chain.web3.eth.get_transaction_receipt(transaction_hash)
            for transaction_hash in hashes
        ]
        self.assertTrue(all(receipt["status"] == 1 for receipt in receipts))
        self.assertEqual(
            len({receipt["blockNumber"] for receipt in receipts}),
            1,
        )

    def test_only_supported_batch_sizes_are_accepted(self) -> None:
        for batch_size in (2, 5, 10, 20, 50):
            self.chain.configure_batch_size(batch_size)
            self.assertEqual(self.chain.status()["minimumTransactions"], batch_size)

        for invalid_size in (0, 3, 10.5, True, "other"):
            with self.subTest(invalid_size=invalid_size):
                with self.assertRaises(ValueError):
                    self.chain.configure_batch_size(invalid_size)

    def test_network_id_matches_configured_chain_id(self) -> None:
        response = self.chain.handle_rpc(
            {"id": 1, "method": "net_version", "params": []}
        )
        self.assertEqual(response["result"], str(self.chain.web3.eth.chain_id))

        listening_response = self.chain.handle_rpc(
            {"id": 2, "method": "net_listening", "params": []}
        )
        self.assertIs(listening_response["result"], True)

    def test_fee_history_accepts_hex_quantity_block_count(self) -> None:
        response = self.chain.handle_rpc(
            {
                "id": 1,
                "method": "eth_feeHistory",
                "params": ["0x1", "latest", [10, 50, 90]],
            }
        )
        self.assertNotIn("error", response)
        result = response["result"]
        self.assertEqual(len(result["baseFeePerGas"]), 2)
        self.assertEqual(len(result["gasUsedRatio"]), 1)
        self.assertEqual(len(result["reward"]), 1)
        self.assertEqual(len(result["reward"][0]), 3)

    def test_hex_block_numbers_are_normalized_for_json_rpc(self) -> None:
        block_response = self.chain.handle_rpc(
            {
                "id": 1,
                "method": "eth_getBlockByNumber",
                "params": [hex(self.chain.web3.eth.block_number), False],
            }
        )
        self.assertNotIn("error", block_response)
        self.assertEqual(
            int(block_response["result"]["number"], 16),
            self.chain.web3.eth.block_number,
        )

        balance_response = self.chain.handle_rpc(
            {
                "id": 2,
                "method": "eth_getBalance",
                "params": [self.accounts[0], hex(self.chain.web3.eth.block_number)],
            }
        )
        self.assertNotIn("error", balance_response)

    def test_eth_get_logs_translates_json_rpc_block_filter_keys(self) -> None:
        topic = Web3.keccak(
            text="ProductQgrams(bytes32,uint256,uint256,bytes32[])"
        ).hex()
        response = self.chain.handle_rpc(
            {
                "id": 3,
                "method": "eth_getLogs",
                "params": [
                    {
                        "fromBlock": "0x0",
                        "toBlock": "latest",
                        "address": self.chain.contract_address,
                        "topics": [topic],
                    }
                ],
            }
        )
        self.assertNotIn("error", response)
        self.assertEqual(response["result"], [])

    def test_eth_call_without_from_uses_a_local_account(self) -> None:
        response = self.chain.handle_rpc(
            {
                "id": 4,
                "method": "eth_call",
                "params": [
                    {
                        "to": self.chain.contract_address,
                        "data": self.chain.contract.functions.administrator()
                        ._encode_transaction_data(),
                    },
                    "latest",
                ],
            }
        )

        self.assertNotIn("error", response)
        self.assertEqual(
            response["result"][-40:].lower(),
            self.accounts[0][2:].lower(),
        )

        explicit_sender_response = self.chain.handle_rpc(
            {
                "id": 5,
                "method": "eth_call",
                "params": [
                    {
                        "to": self.chain.contract_address,
                        "from": self.accounts[1],
                        "data": self.chain.contract.functions.stakeholderRoles(
                            self.accounts[1]
                        )._encode_transaction_data(),
                    },
                    "latest",
                ],
            }
        )
        self.assertNotIn("error", explicit_sender_response)

    def test_eth_estimate_gas_without_from_uses_a_local_account(self) -> None:
        response = self.chain.handle_rpc(
            {
                "id": 7,
                "method": "eth_estimateGas",
                "params": [
                    {
                        "to": self.chain.contract_address,
                        "data": self.chain.contract.functions.fuzzyThresholdPercent()
                        ._encode_transaction_data(),
                    }
                ],
            }
        )

        self.assertNotIn("error", response)
        self.assertGreater(int(response["result"], 16), 0)

    def test_backend_session_signer_preserves_manufacturer_and_nonce(self) -> None:
        role_data = self.chain.contract.functions.setStakeholderRole(
            self.accounts[1], 1
        )._encode_transaction_data()
        admin_nonce = self.chain.web3.eth.get_transaction_count(self.accounts[0])
        self._submit_signed(0, admin_nonce, self.chain.contract_address, role_data)
        self.chain.process_pending()
        self.chain.configure_batch_size(2)
        self.chain.users = {
            "manufacturer": {
                "username": "manufacturer",
                "passwordHash": hash_password("manufacturer-password-1"),
                "accountIndex": 1,
            }
        }

        self.assertIsNone(self.chain.authenticate("manufacturer", "wrong-password"))
        token = self.chain.authenticate("manufacturer", "manufacturer-password-1")
        self.assertIsNotNone(token)

        commitments = [
            Web3.to_hex(sample_commitment("backend-signing", number))
            for number in (1, 2)
        ]
        first_result = self.chain.submit_contract_transaction(
            token,
            "registerProduct",
            {
                "commitment": commitments[0],
                "qgramHashes": ["0x" + "11" * 32],
            },
        )
        pending = list(self.chain.pending_transactions.values())
        self.assertEqual([item["from"] for item in pending], [self.accounts[1]])
        self.assertEqual([item["nonce"] for item in pending], [0])
        self.assertGreaterEqual(pending[0]["gas"], 4_000_000)
        self.assertTrue(first_result["pending"])

        second_result = self.chain.submit_contract_transaction(
            token,
            "registerProduct",
            {"commitment": commitments[1], "qgramHashes": []},
        )
        self.assertFalse(second_result["pending"])
        self.assertEqual(
            self.chain.web3.eth.get_transaction(second_result["hash"])["nonce"], 1
        )
        self.assertEqual(
            self.chain.web3.eth.get_transaction(second_result["hash"])["from"],
            self.accounts[1],
        )
        for commitment, result in zip(
            commitments, (first_result, second_result)
        ):
            product = self.chain.contract.functions.getProduct(commitment).call()
            self.assertEqual(product[0], self.accounts[1])
            self.assertEqual(
                self.chain.web3.eth.get_transaction_receipt(result["hash"])["status"],
                1,
            )

    def test_unlocked_eth_send_transaction_is_disabled(self) -> None:
        response = self.chain.handle_rpc(
            {"id": 6, "method": "eth_sendTransaction", "params": [{}]}
        )
        self.assertEqual(response["error"]["code"], -32601)
        self.assertIn("authenticated", response["error"]["message"])

    def test_environment_user_config_requires_unique_accounts_and_admin_index_zero(self) -> None:
        users = [
            {
                "username": "admin",
                "passwordHash": hash_password("administrator-password-1"),
                "accountIndex": 0,
            },
            {
                "username": "manufacturer",
                "passwordHash": hash_password("manufacturer-password-1"),
                "accountIndex": 1,
            },
            {
                "username": "distributor",
                "passwordHash": hash_password("distributor-password-1"),
                "accountIndex": 2,
            },
        ]
        configured = load_users(json.dumps(users), account_count=10)
        self.assertEqual(configured["manufacturer"]["accountIndex"], 1)
        self.assertTrue(
            verify_password(
                "manufacturer-password-1",
                configured["manufacturer"]["passwordHash"],
            )
        )

        users[2]["accountIndex"] = 1
        with self.assertRaisesRegex(ValueError, "unique accountIndex"):
            load_users(json.dumps(users), account_count=10)

    def test_login_api_uses_http_only_cookie_and_rejects_cross_origin(self) -> None:
        self.chain.users = {
            "admin": {
                "username": "admin",
                "passwordHash": hash_password("administrator-password-1"),
                "accountIndex": 0,
            },
            "manufacturer": {
                "username": "manufacturer",
                "passwordHash": hash_password("manufacturer-password-1"),
                "accountIndex": 1,
            },
            "distributor": {
                "username": "distributor",
                "passwordHash": hash_password("distributor-password-1"),
                "accountIndex": 2,
            },
        }
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_web_handler(self.chain))
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        connection = http.client.HTTPConnection(*server.server_address, timeout=5)
        origin = f"http://{server.server_address[0]}:{server.server_address[1]}"
        body = json.dumps(
            {"username": "manufacturer", "password": "manufacturer-password-1"}
        )
        try:
            connection.request(
                "POST",
                "/api/auth/login",
                body,
                {"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            self.assertEqual(response.status, 403)
            response.read()

            connection.request(
                "POST",
                "/api/auth/login",
                body,
                {"Content-Type": "application/json", "Origin": origin},
            )
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            profile = json.loads(response.read())
            cookie = response.getheader("Set-Cookie")
            self.assertIn("HttpOnly", cookie)
            self.assertIn("SameSite=Strict", cookie)
            self.assertEqual(profile["address"], self.accounts[1])
            self.assertNotIn("passwordHash", profile)

            connection.request(
                "POST",
                "/api/transactions",
                json.dumps(
                    {
                        "operation": "registerProduct",
                        "arguments": {
                            "commitment": "0x" + "0" * 64,
                            "qgramHashes": [],
                        },
                    }
                ),
                {
                    "Content-Type": "application/json",
                    "Origin": origin,
                    "Cookie": cookie.split(";", 1)[0],
                },
            )
            response = connection.getresponse()
            self.assertEqual(response.status, 400)
            self.assertIn("Transaction would revert", json.loads(response.read())["error"])

            connection.request(
                "GET",
                "/api/auth/session",
                headers={"Cookie": cookie.split(";", 1)[0]},
            )
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(json.loads(response.read())["username"], "manufacturer")
        finally:
            connection.close()
            server.shutdown()
            server.server_close()
            server_thread.join(timeout=5)

    def test_non_manufacturer_registration_is_not_counted(self) -> None:
        initial_block = self.chain.web3.eth.block_number
        data = self.chain.contract.functions.registerProduct(
            "0x" + "0" * 61 + "201"
        )._encode_transaction_data()
        self._submit_signed(
            2,
            self.chain.web3.eth.get_transaction_count(self.accounts[2]),
            self.chain.contract_address,
            data,
        )

        self.chain.process_pending()

        self.assertEqual(self.chain.status()["pendingCount"], 0)
        self.assertIsNone(self.chain.status()["lastBlock"])
        self.assertEqual(self.chain.web3.eth.block_number, initial_block)

    def test_sample_commitments_are_unique_nonzero_bytes32_values(self) -> None:
        first = sample_commitment("test-run", 1)
        second = sample_commitment("test-run", 2)

        self.assertEqual(len(first), 32)
        self.assertNotEqual(first, bytes(32))
        self.assertNotEqual(first, second)

    def test_legacy_transactions_are_rejected_with_clear_error(self) -> None:
        data = self.chain.contract.functions.registerProduct(
            "0x" + "0" * 61 + "301"
        )._encode_transaction_data()

        with self.assertRaisesRegex(ValueError, "Legacy transactions are unsupported"):
            self._submit_signed(
                1,
                self.chain.web3.eth.get_transaction_count(self.accounts[1]),
                self.chain.contract_address,
                data,
                transaction_type=0,
            )

    def test_login_password_prompt_rejects_empty_input(self) -> None:
        with (
            patch("backend.scripts.add_sample_data.getpass.getpass", return_value=""),
            self.assertRaisesRegex(ValueError, "cannot be empty"),
        ):
            prompt_secret("Manufacturer password")


if __name__ == "__main__":
    unittest.main()
