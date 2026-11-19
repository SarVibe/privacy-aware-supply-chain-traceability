import json
import gzip
import logging
import os
import re
import secrets
import socket
import subprocess
import threading
import time
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from eth_abi.exceptions import DecodingError
from eth_account import Account
from eth_account.typed_transactions import TypedTransaction
from hexbytes import HexBytes
from solcx import compile_standard, get_installed_solc_versions, install_solc
from web3 import Web3
from web3.exceptions import ContractLogicError, TransactionNotFound

from backend.app.auth import hash_password, load_users, verify_password

Account.enable_unaudited_hdwallet_features()


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROOT = PROJECT_ROOT
CONTRACTS_DIR = PROJECT_ROOT / "blockchain" / "contracts"
FRONTEND_DIR = PROJECT_ROOT / "frontend" / "dist"
SOLC_VERSION = "0.8.24"
CHAIN_ID = 131277322940537
RPC_HOST = "127.0.0.1"
RPC_PORT = 8546
WEB_HOST = "127.0.0.1"
WEB_PORT = 5173
POLL_INTERVAL_SECONDS = 0.25
BLOCK_GAS_LIMIT = 100_000_000
ALLOWED_BATCH_SIZES = (2, 5, 10, 20, 50)
ANVIL_ACCOUNTS = 10
ANVIL_ACCOUNT_BALANCE = 10000
ANVIL_MNEMONIC = (
    "test test test test test test test test test test test junk"
)
DATA_DIR = PROJECT_ROOT / "backend" / "data"
ANVIL_STATE_PATH = DATA_DIR / "anvil-state.json"
DEPLOYMENT_METADATA_PATH = DATA_DIR / "pharmachain-deployment.json"
LEGACY_REGISTRATION_SELECTOR = Web3.to_hex(
    Web3.keccak(text="registerProduct(bytes32)")[:4]
)
QGRAM_REGISTRATION_SELECTOR = Web3.to_hex(
    Web3.keccak(text="registerProduct(bytes32,bytes32[])")[:4]
)
REGISTRATION_SELECTORS = {
    LEGACY_REGISTRATION_SELECTOR,
    QGRAM_REGISTRATION_SELECTOR,
}
APPLICATION_SELECTORS = {
    *REGISTRATION_SELECTORS,
    Web3.to_hex(Web3.keccak(text="setStakeholderRole(address,uint8)")[:4]),
    Web3.to_hex(Web3.keccak(text="setFuzzyThresholdPercent(uint8)")[:4]),
    Web3.to_hex(Web3.keccak(text="transferToDistributor(bytes32,address)")[:4]),
    Web3.to_hex(Web3.keccak(text="acceptShipment(bytes32)")[:4]),
}
TRANSACTION_QUANTITY_FIELDS = (
    "nonce",
    "gas",
    "gasPrice",
    "value",
    "maxFeePerGas",
    "maxPriorityFeePerGas",
    "maxFeePerBlobGas",
    "type",
    "chainId",
)
BLOCK_NUMBER_PARAMETERS = {
    "eth_getBlockByNumber": (0,),
    "eth_getBlockTransactionCountByNumber": (0,),
    "eth_getUncleCountByBlockNumber": (0,),
    "eth_getTransactionByBlockNumberAndIndex": (0,),
    "eth_getUncleByBlockNumberAndIndex": (0,),
    "eth_getBalance": (1,),
    "eth_getTransactionCount": (1,),
    "eth_call": (1,),
    "eth_estimateGas": (1,),
    "eth_getCode": (1,),
    "eth_getStorageAt": (2,),
    "eth_getProof": (2,),
}
ZERO_BYTES32 = "0x" + "0" * 64
SESSION_LIFETIME_SECONDS = 8 * 60 * 60
SESSION_COOKIE_NAME = "pharmachain_session"
MAX_LOGIN_ATTEMPTS = 10
LOGIN_WINDOW_SECONDS = 5 * 60

logger = logging.getLogger("pharmachain.local_chain")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def parse_quantity(value: Any) -> int:
    if isinstance(value, str) and value.startswith("0x"):
        return int(value, 16)
    return int(value)


def compile_contracts() -> dict[str, dict[str, Any]]:
    if not any(str(version) == SOLC_VERSION for version in get_installed_solc_versions()):
        logger.info("Installing Solidity compiler %s", SOLC_VERSION)
        install_solc(SOLC_VERSION)

    sources = {
        path.relative_to(PROJECT_ROOT).as_posix(): {"content": path.read_text(encoding="utf-8")}
        for path in CONTRACTS_DIR.glob("*.sol")
    }
    if "blockchain/contracts/Verifier.sol" not in sources:
        raise FileNotFoundError(
            "blockchain/contracts/Verifier.sol is missing. Restore the generated Groth16 verifier source."
        )

    output = compile_standard(
        {
            "language": "Solidity",
            "sources": sources,
            "settings": {
                "outputSelection": {"*": {"*": ["abi", "evm.bytecode.object"]}}
            },
        },
        solc_version=SOLC_VERSION,
        allow_paths=str(PROJECT_ROOT),
    )
    return output["contracts"]


class LocalChain:
    def __init__(
        self,
        users: dict[str, dict[str, Any]] | None = None,
        *,
        reset: bool = False,
    ) -> None:
        self.lock = threading.RLock()
        self.anvil_process: subprocess.Popen[bytes] | None = None
        self.users = users or {}
        self._start_or_connect_anvil(reset=reset)
        self.web3 = Web3(Web3.HTTPProvider(f"http://{RPC_HOST}:{RPC_PORT}"))
        if not self.web3.is_connected():
            raise RuntimeError(
                f"Could not connect to Anvil at http://{RPC_HOST}:{RPC_PORT}"
            )
        self.accounts = [
            Account.from_mnemonic(
                ANVIL_MNEMONIC,
                account_path=f"m/44'/60'/0'/0/{index}",
            ).address
            for index in range(ANVIL_ACCOUNTS)
        ]
        self.account_keys = [
            Account.from_mnemonic(
                ANVIL_MNEMONIC,
                account_path=f"m/44'/60'/0'/0/{index}",
            ).key
            for index in range(ANVIL_ACCOUNTS)
        ]
        if int(self.web3.eth.chain_id) != CHAIN_ID:
            raise RuntimeError(
                f"Anvil chain ID is {self.web3.eth.chain_id}; "
                f"expected {CHAIN_ID}"
            )
        if reset:
            response = self.web3.provider.make_request("anvil_reset", [])
            if "error" in response:
                raise RuntimeError(response["error"]["message"])
        self.provider = self.web3.provider
        self.users = users or {}
        self.sessions: dict[str, tuple[str, float]] = {}
        self.dummy_password_hash = hash_password(
            "dummy-password-used-for-constant-work"
        )
        self.pending_transactions: dict[str, dict[str, Any]] = {}
        self.pending_registrations: list[dict[str, Any]] = []
        self.minimum_transactions = 10
        self.last_block: dict[str, Any] | None = None
        self.error = ""
        self.stopped = threading.Event()
        self._set_anvil_automine(False)
        self._connect_or_deploy_contracts()

    def _anvil_executable(self) -> Path:
        configured = os.environ.get("ANVIL_EXECUTABLE")
        if configured:
            executable = Path(configured)
            if executable.is_file():
                return executable
        candidates = (
            ROOT / ".tools" / "foundry" / "anvil.exe",
            ROOT / ".tools" / "foundry" / "anvil",
            Path(os.environ.get("USERPROFILE", "")) / ".foundry" / "bin" / "anvil.exe",
            Path(os.environ.get("USERPROFILE", "")) / ".foundry" / "bin" / "anvil",
        )
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        raise RuntimeError(
            "Anvil is not installed. Install Foundry or set ANVIL_EXECUTABLE "
            "to the anvil executable."
        )

    def _anvil_is_listening(self) -> bool:
        try:
            with socket.create_connection((RPC_HOST, RPC_PORT), timeout=0.5):
                return True
        except OSError:
            return False

    def _start_or_connect_anvil(self, reset: bool) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if reset:
            DEPLOYMENT_METADATA_PATH.unlink(missing_ok=True)
            ANVIL_STATE_PATH.unlink(missing_ok=True)

        if not self._anvil_is_listening():
            command = [
                str(self._anvil_executable()),
                "--chain-id",
                str(CHAIN_ID),
                "--accounts",
                str(ANVIL_ACCOUNTS),
                "--balance",
                str(ANVIL_ACCOUNT_BALANCE),
                "--mnemonic",
                ANVIL_MNEMONIC,
                "--host",
                RPC_HOST,
                "--port",
                str(RPC_PORT),
            ]
            if ANVIL_STATE_PATH.is_file():
                command.extend(["--load-state", str(ANVIL_STATE_PATH)])
            command.extend(["--dump-state", str(ANVIL_STATE_PATH)])
            self.anvil_process = subprocess.Popen(
                command,
                cwd=str(ROOT),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if self._anvil_is_listening():
                break
            if self.anvil_process is not None and self.anvil_process.poll() is not None:
                raise RuntimeError(
                    f"Anvil exited during startup with code "
                    f"{self.anvil_process.returncode}"
                )
            time.sleep(0.1)
        if not self._anvil_is_listening():
            raise RuntimeError("Timed out waiting for Anvil to start.")

    def _set_anvil_automine(self, enabled: bool) -> None:
        response = self.web3.provider.make_request(
            "evm_setAutomine",
            [enabled],
        )
        if "error" in response:
            raise RuntimeError(response["error"]["message"])

    def _mine_one_anvil_block(self) -> dict[str, Any]:
        response = self.web3.provider.make_request("evm_mine", [])
        if "error" in response:
            raise RuntimeError(response["error"]["message"])
        return response

    def authenticate(self, username: str, password: str) -> str | None:
        user = self.users.get(username)
        password_hash = (
            user["passwordHash"] if user is not None else self.dummy_password_hash
        )
        password_matches = verify_password(password, password_hash)
        if user is None or not password_matches:
            return None

        token = secrets.token_urlsafe(32)
        with self.lock:
            self.sessions[token] = (
                username,
                time.monotonic() + SESSION_LIFETIME_SECONDS,
            )
        return token

    def logout(self, token: str | None) -> None:
        if token is None:
            return
        with self.lock:
            self.sessions.pop(token, None)

    def session_profile(self, token: str | None) -> dict[str, Any] | None:
        if token is None:
            return None
        with self.lock:
            session = self.sessions.get(token)
            if session is None:
                return None
            username, expires_at = session
            if expires_at <= time.monotonic():
                self.sessions.pop(token, None)
                return None
            user = self.users[username]
            address = self.accounts[user["accountIndex"]]
            role = self.contract.functions.stakeholderRoles(address).call()
            administrator = self.contract.functions.administrator().call()
            return {
                "username": username,
                "address": address,
                "role": int(role),
                "administrator": administrator,
                "isAdministrator": address.lower() == administrator.lower(),
                "chainId": CHAIN_ID,
            }

    def configured_accounts(self, token: str) -> list[dict[str, Any]]:
        profile = self.session_profile(token)
        if profile is None or not profile["isAdministrator"]:
            raise PermissionError("Administrator login required.")
        return [
            {
                "username": user["username"],
                "address": self.accounts[user["accountIndex"]],
                "role": int(
                    self.contract.functions.stakeholderRoles(
                        self.accounts[user["accountIndex"]]
                    ).call()
                ),
            }
            for user in self.users.values()
        ]

    def submit_contract_transaction(
        self, token: str, operation: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        profile = self.session_profile(token)
        if profile is None:
            raise PermissionError("Login expired. Sign in again.")
        user = self.users[profile["username"]]
        sender = profile["address"]

        try:
            if operation == "registerProduct":
                commitment = self._validated_bytes32(arguments, "commitment")
                qgram_hashes = arguments.get("qgramHashes")
                if (
                    not isinstance(qgram_hashes, list)
                    or len(qgram_hashes) > 256
                ):
                    raise ValueError("qgramHashes must be a list of at most 256 hashes.")
                hashes = [
                    self._validated_bytes32({"value": value}, "value")
                    for value in qgram_hashes
                ]
                function = self.contract.functions.registerProduct(
                    commitment, hashes
                )
            elif operation == "transferToDistributor":
                commitment = self._validated_bytes32(arguments, "commitment")
                distributor = Web3.to_checksum_address(arguments.get("distributor", ""))
                function = self.contract.functions.transferToDistributor(
                    commitment, distributor
                )
            elif operation == "acceptShipment":
                commitment = self._validated_bytes32(arguments, "commitment")
                function = self.contract.functions.acceptShipment(commitment)
            elif operation == "setStakeholderRole":
                stakeholder = Web3.to_checksum_address(arguments.get("stakeholder", ""))
                role = arguments.get("role")
                if isinstance(role, bool) or role not in (0, 1, 2):
                    raise ValueError("Stakeholder role must be 0, 1, or 2.")
                function = self.contract.functions.setStakeholderRole(
                    stakeholder, role
                )
            elif operation == "setFuzzyThresholdPercent":
                threshold = arguments.get("threshold")
                if (
                    isinstance(threshold, bool)
                    or not isinstance(threshold, int)
                    or not 1 <= threshold <= 100
                ):
                    raise ValueError("Dice threshold must be a whole percentage from 1 to 100.")
                if (
                    sender.lower() != self.contract.functions.administrator().call().lower()
                    and int(
                        self.contract.functions.stakeholderRoles(sender).call()
                    ) == 0
                ):
                    raise PermissionError(
                        "Administrator, manufacturer, or distributor access is required."
                    )
                function = self.contract.functions.setFuzzyThresholdPercent(threshold)
            else:
                raise ValueError("Unsupported contract transaction.")
        except (TypeError, ValueError) as error:
            raise ValueError(str(error) or "Invalid transaction arguments.") from error

        with self.lock:
            nonce = self._pending_nonce(sender)
            gas_estimate = function.estimate_gas({"from": sender})
            priority_fee = self.web3.eth.max_priority_fee
            if operation == "registerProduct":
                registration_qgram_count = len(
                    arguments.get("qgramHashes", [])
                    if isinstance(arguments.get("qgramHashes", []), list)
                    else []
                )
                gas_limit = 4_000_000 if registration_qgram_count > 0 else 1_000_000
            else:
                gas_limit = 1_000_000
            transaction = function.build_transaction(
                {
                    "chainId": CHAIN_ID,
                    "from": sender,
                    "nonce": nonce,
                    "gas": min(
                        BLOCK_GAS_LIMIT,
                        max(
                            21_000,
                            gas_limit,
                            gas_estimate + gas_estimate // 5,
                        ),
                    ),
                    "type": 2,
                    "accessList": [],
                    "maxPriorityFeePerGas": priority_fee,
                    "maxFeePerGas": max(
                        self.web3.eth.gas_price * 2, priority_fee * 2
                    ),
                }
            )
            signed = Account.sign_transaction(
                transaction,
                self.account_keys[user["accountIndex"]],
            )
            response = self.handle_rpc(
                {
                    "id": 1,
                    "method": "eth_sendRawTransaction",
                    "params": [Web3.to_hex(signed.raw_transaction)],
                }
            )
            if "error" in response:
                raise ValueError(response["error"]["message"])
            transaction_hash = response["result"]

        self.process_pending()
        try:
            receipt = self.web3.eth.get_transaction_receipt(transaction_hash)
        except TransactionNotFound:
            receipt = None
        if receipt is not None and receipt["status"] != 1:
            raise ValueError(f"Transaction reverted: {transaction_hash}")
        return {
            "hash": transaction_hash,
            "pending": receipt is None,
            "status": None if receipt is None else int(receipt["status"]),
        }

    @staticmethod
    def _validated_bytes32(arguments: dict[str, Any], field: str) -> bytes:
        value = arguments.get(field)
        try:
            encoded = Web3.to_bytes(hexstr=value)
        except (TypeError, ValueError) as error:
            raise ValueError(f"{field} must be a 32-byte hexadecimal value.") from error
        if len(encoded) != 32:
            raise ValueError(f"{field} must be a 32-byte hexadecimal value.")
        return encoded

    def _connect_or_deploy_contracts(self) -> None:
        if DEPLOYMENT_METADATA_PATH.is_file():
            try:
                metadata = json.loads(
                    DEPLOYMENT_METADATA_PATH.read_text(encoding="utf-8")
                )
                verifier_address = Web3.to_checksum_address(metadata["verifier"])
                contract_address = Web3.to_checksum_address(metadata["supplyChain"])
                if (
                    int(metadata["chainId"]) == CHAIN_ID
                    and len(self.web3.eth.get_code(verifier_address)) > 0
                    and len(self.web3.eth.get_code(contract_address)) > 0
                ):
                    compiled = compile_contracts()
                    supply_chain_artifact = compiled[
                        "blockchain/contracts/PharmaSupplyChain.sol"
                    ]["PharmaSupplyChain"]
                    self.verifier_address = verifier_address
                    self.contract_address = contract_address
                    self.contract = self.web3.eth.contract(
                        address=self.contract_address,
                        abi=supply_chain_artifact["abi"],
                    )
                    logger.info(
                        "Reconnected to deployed PharmaChain contracts "
                        "at %s and %s",
                        self.verifier_address,
                        self.contract_address,
                    )
                    return
            except (json.JSONDecodeError, KeyError, OSError, ValueError, TypeError):
                logger.warning(
                    "Invalid Anvil deployment metadata; redeploying contracts."
                )
        self._deploy_contracts()

    def _send_signed_deployment_transaction(
        self,
        transaction_function: Any,
        sender: str,
    ) -> Any:
        nonce = self.web3.eth.get_transaction_count(sender, "pending")
        gas_estimate = transaction_function.estimate_gas({"from": sender})
        transaction = transaction_function.build_transaction(
            {
                "chainId": CHAIN_ID,
                "from": sender,
                "nonce": nonce,
                "gas": min(BLOCK_GAS_LIMIT, max(21_000, gas_estimate + gas_estimate // 5)),
                "type": 2,
                "accessList": [],
                "maxPriorityFeePerGas": self.web3.eth.max_priority_fee,
                "maxFeePerGas": max(
                    self.web3.eth.gas_price * 2,
                    self.web3.eth.max_priority_fee * 2,
                ),
            }
        )
        signed = Account.sign_transaction(transaction, self.account_keys[0])
        transaction_hash = self.web3.eth.send_raw_transaction(
            signed.raw_transaction
        )
        self._mine_one_anvil_block()
        receipt = self.web3.eth.wait_for_transaction_receipt(
            transaction_hash,
            timeout=30,
        )
        if receipt["status"] != 1:
            raise RuntimeError(
                f"Contract deployment transaction reverted: {transaction_hash.hex()}"
            )
        return receipt

    def _deploy_contracts(self) -> None:
        compiled = compile_contracts()
        verifier_artifact = compiled["blockchain/contracts/Verifier.sol"]["Groth16Verifier"]
        supply_chain_artifact = compiled["blockchain/contracts/PharmaSupplyChain.sol"][
            "PharmaSupplyChain"
        ]
        deployer = self.accounts[0]
        verifier_factory = self.web3.eth.contract(
            abi=verifier_artifact["abi"],
            bytecode=verifier_artifact["evm"]["bytecode"]["object"],
        )
        verifier_receipt = self._send_signed_deployment_transaction(
            verifier_factory.constructor(),
            deployer,
        )

        supply_chain_factory = self.web3.eth.contract(
            abi=supply_chain_artifact["abi"],
            bytecode=supply_chain_artifact["evm"]["bytecode"]["object"],
        )
        supply_receipt = self._send_signed_deployment_transaction(
            supply_chain_factory.constructor(verifier_receipt.contractAddress),
            deployer,
        )

        self.verifier_address = Web3.to_checksum_address(verifier_receipt.contractAddress)
        self.contract_address = Web3.to_checksum_address(supply_receipt.contractAddress)
        self.contract = self.web3.eth.contract(
            address=self.contract_address,
            abi=supply_chain_artifact["abi"],
        )
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        DEPLOYMENT_METADATA_PATH.write_text(
            json.dumps(
                {
                    "chainId": CHAIN_ID,
                    "verifier": self.verifier_address,
                    "supplyChain": self.contract_address,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        for account_index, role in ((1, 1), (2, 2)):
            role_function = self.contract.functions.setStakeholderRole(
                self.accounts[account_index],
                role,
            )
            self._send_signed_deployment_transaction(
                role_function,
                deployer,
            )
        logger.info("Python EVM chain ID: %s", self.web3.eth.chain_id)
        logger.info("Groth16 verifier deployed at %s", self.verifier_address)
        logger.info("Supply-chain contract deployed at %s", self.contract_address)

    def status(self) -> dict[str, Any]:
        with self.lock:
            return {
                "minimumTransactions": self.minimum_transactions,
                "allowedBatchSizes": list(ALLOWED_BATCH_SIZES),
                "pendingRegistrations": list(self.pending_registrations),
                "pendingCount": len(self.pending_registrations),
                "remainingTransactions": max(
                    0, self.minimum_transactions - len(self.pending_registrations)
                ),
                "lastBlock": self.last_block,
                "error": self.error,
            }

    def configure_batch_size(self, value: Any) -> dict[str, Any]:
        if isinstance(value, bool):
            raise ValueError("Minimum transactions must be 2, 5, 10, 20, or 50.")
        if isinstance(value, int):
            batch_size = value
        elif isinstance(value, str) and value.isdecimal():
            batch_size = int(value)
        else:
            raise ValueError("Minimum transactions must be 2, 5, 10, 20, or 50.")
        if batch_size not in ALLOWED_BATCH_SIZES:
            raise ValueError("Minimum transactions must be 2, 5, 10, 20, or 50.")
        with self.lock:
            self.minimum_transactions = batch_size
        self.process_pending()
        return {"minimumTransactions": batch_size}

    def _get_pending_transactions(self) -> list[dict[str, Any]]:
        return list(self.pending_transactions.values())

    def _queue_raw_transaction(self, raw_transaction: str) -> str:
        raw_bytes = HexBytes(raw_transaction)
        if len(raw_bytes) < 1 or raw_bytes[0] != 2:
            raise ValueError(
                "Legacy transactions are unsupported on this local chain. "
                "Submit an EIP-1559 type-2 transaction instead."
            )
        typed = TypedTransaction.from_bytes(raw_bytes)
        decoded = typed.as_dict()
        chain_id = decoded.get("chainId")
        if chain_id != CHAIN_ID:
            raise ValueError(f"Transaction chain ID must be {CHAIN_ID}.")
        nonce = decoded["nonce"]
        sender = Account.recover_transaction(raw_bytes)

        latest_nonce = self.web3.eth.get_transaction_count(sender, "latest")
        queued_nonces = [
            item["nonce"]
            for item in self.pending_transactions.values()
            if item["from"].lower() == sender.lower()
        ]
        expected_nonce = max([latest_nonce, *(nonce + 1 for nonce in queued_nonces)])
        if nonce != expected_nonce:
            raise ValueError(
                f"Invalid transaction nonce: expected {expected_nonce}, "
                f"received {nonce}."
            )

        transaction_hash = self.web3.eth.send_raw_transaction(raw_bytes).hex().lower()
        if transaction_hash in self.pending_transactions:
            return transaction_hash
        rpc_transaction = dict(
            self.web3.eth.get_transaction(transaction_hash)
        )
        pending = {
            "hash": transaction_hash,
            "transaction_type": 2,
            "nonce": nonce,
            "block_hash": rpc_transaction.get("blockHash"),
            "block_number": rpc_transaction.get("blockNumber"),
            "transaction_index": rpc_transaction.get("transactionIndex"),
            "from": sender,
            "to": rpc_transaction.get("to"),
            "value": rpc_transaction.get("value", 0),
            "gas": rpc_transaction.get("gas", 0),
            "data": Web3.to_hex(rpc_transaction.get("input", "0x")),
            "chain_id": chain_id,
            "access_list": rpc_transaction.get("accessList", []),
            "max_fee_per_gas": rpc_transaction.get("maxFeePerGas"),
            "max_priority_fee_per_gas": rpc_transaction.get("maxPriorityFeePerGas"),
        }
        self.pending_transactions[transaction_hash] = pending
        return transaction_hash

    @staticmethod
    def _pending_rpc_transaction(transaction: dict[str, Any]) -> dict[str, Any]:
        result = dict(transaction)
        transaction_type = result.pop("transaction_type")
        result["input"] = result.pop("data")
        if "max_fee_per_gas" in result:
            result["gas_price"] = result["max_fee_per_gas"]
        result["type"] = hex(transaction_type)
        return result

    @staticmethod
    def _calldata(transaction: dict[str, Any]) -> str:
        data = transaction.get("input") or transaction.get("data") or "0x"
        if isinstance(data, bytes):
            data = Web3.to_hex(data)
        return str(data).lower()

    def _valid_registrations(
        self, transactions: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        pending_commitments: set[str] = set()
        registrations = []
        for transaction in transactions:
            if (transaction.get("to") or "").lower() != self.contract_address.lower():
                continue
            data = self._calldata(transaction)
            selector = data[:10]
            if selector not in REGISTRATION_SELECTORS:
                continue

            if selector == LEGACY_REGISTRATION_SELECTOR:
                # The legacy registration selector carries one bytes32 argument.
                if len(data) != 74:
                    continue
                commitment = "0x" + data[10:]
            else:
                try:
                    _, decoded = self.contract.decode_function_input(data)
                except (DecodingError, TypeError, ValueError):
                    continue
                commitment = Web3.to_hex(decoded["commitment"]).lower()
                if len(decoded["qgramHashes"]) > 256:
                    continue
            if commitment == ZERO_BYTES32 or commitment in pending_commitments:
                continue
            role = self.contract.functions.stakeholderRoles(
                Web3.to_checksum_address(transaction["from"])
            ).call()
            if role != 1:
                continue
            product = self.contract.functions.getProduct(commitment).call()
            if product[-1]:
                continue

            pending_commitments.add(commitment)
            registrations.append(
                {
                    "hash": transaction["hash"],
                    "from": transaction["from"],
                    "nonce": parse_quantity(transaction["nonce"]),
                    "commitment": commitment,
                }
            )

        registrations.sort(
            key=lambda item: (item["from"].lower(), item["nonce"])
        )
        return registrations

    def _is_application_transaction(self, transaction: dict[str, Any]) -> bool:
        if (transaction.get("to") or "").lower() != self.contract_address.lower():
            return False
        data = self._calldata(transaction)
        selector = data[:10]
        if selector not in APPLICATION_SELECTORS:
            return False
        return selector not in REGISTRATION_SELECTORS

    def _mine_batch(
        self,
        pending_transactions: list[dict[str, Any]],
        registrations: list[dict[str, Any]],
    ) -> bool:
        candidate_hashes = {item["hash"].lower() for item in registrations}
        if not candidate_hashes:
            candidate_hashes = {
                item["hash"].lower()
                for item in pending_transactions
                if self._is_application_transaction(item)
            }
        currently_pending = {
            item["hash"].lower() for item in self._get_pending_transactions()
        }
        if not candidate_hashes.intersection(currently_pending):
            return False

        if registrations:
            fresh_pending = self._get_pending_transactions()
            registrations = self._valid_registrations(fresh_pending)
            if len(registrations) < self.minimum_transactions:
                return False

        queued = list(self.pending_transactions.items())
        self._mine_one_anvil_block()
        block = self.web3.eth.get_block("latest", full_transactions=False)
        block_hashes = {
            (
                item.hex().lower()
                if hasattr(item, "hex")
                else str(item).lower()
            )
            for item in block["transactions"]
        }
        included_registrations = []
        for item in registrations:
            transaction_hash = item["hash"].lower()
            if transaction_hash not in block_hashes:
                continue
            receipt = self.web3.eth.get_transaction_receipt(item["hash"])
            if receipt["status"] == 1 and receipt["blockNumber"] == block["number"]:
                included_registrations.append(item["hash"])

        if registrations:
            self.last_block = {
                "number": block["number"],
                "hash": block["hash"].hex(),
                "transactionCount": len(block["transactions"]),
                "registrationCount": len(included_registrations),
                "transactionHashes": included_registrations,
            }
        for transaction_hash, _ in queued:
            self.pending_transactions.pop(transaction_hash, None)
        logger.info(
            "Mined block %s; %s product registration(s) confirmed",
            block["number"],
            len(included_registrations),
        )
        return True

    def process_pending(self) -> None:
        if not self.lock.acquire(blocking=False):
            return
        try:
            transactions = self._get_pending_transactions()
            registrations = self._valid_registrations(transactions)
            self.pending_registrations = registrations
            if len(registrations) >= self.minimum_transactions:
                if self._mine_batch(transactions, registrations):
                    self.pending_registrations = []
            elif (
                not registrations
                and any(self._is_application_transaction(item) for item in transactions)
            ):
                self._mine_batch(transactions, [])
            self.error = ""
        except Exception as error:
            message = str(error) or type(error).__name__
            if message != self.error:
                logger.exception("Local batch miner error")
            self.error = message
        finally:
            self.lock.release()

    def handle_rpc(self, payload: dict[str, Any]) -> dict[str, Any]:
        request_id = payload.get("id")
        method = payload.get("method")
        params = payload.get("params", [])
        if not isinstance(method, str) or not isinstance(params, list):
            return self._rpc_error(request_id, -32600, "Invalid JSON-RPC request.")

        try:
            with self.lock:
                if method == "evm_setAutomine":
                    if params and params[0] is True:
                        return self._rpc_error(
                            request_id, -32600, "Automining is disabled for this app."
                        )
                    self._set_anvil_automine(False)
                    result: Any = True
                elif method == "net_version":
                    result = str(CHAIN_ID)
                elif method == "net_listening":
                    result = True
                elif method == "eth_feeHistory":
                    result = self._fee_history(params)
                elif method == "evm_mine":
                    self._mine_one_anvil_block()
                    self.pending_transactions.clear()
                    result = None
                elif method == "eth_pendingTransactions":
                    result = [
                        self._pending_rpc_transaction(item)
                        for item in self._get_pending_transactions()
                    ]
                elif method == "eth_getTransactionByHash" and params:
                    transaction = self.pending_transactions.get(params[0].lower())
                    if transaction is None:
                        response = self.web3.provider.make_request(method, params)
                        if "error" in response:
                            if "not found" in response["error"].get("message", "").lower():
                                result = None
                                return {
                                    "jsonrpc": "2.0",
                                    "id": request_id,
                                    "result": None,
                                }
                            return {
                                "jsonrpc": "2.0",
                                "id": request_id,
                                "error": response["error"],
                            }
                        result = response.get("result")
                    else:
                        result = self._pending_rpc_transaction(transaction)
                elif method == "eth_getTransactionReceipt" and params and params[0].lower() in self.pending_transactions:
                    result = None
                elif method == "eth_sendRawTransaction" and params:
                    result = self._queue_raw_transaction(params[0])
                elif method == "eth_sendTransaction":
                    return self._rpc_error(
                        request_id,
                        -32601,
                        "Unsigned transactions are disabled. Sign in and use the "
                        "authenticated application transaction endpoint.",
                    )
                elif method == "eth_getTransactionCount" and len(params) > 1 and params[1] == "pending":
                    result = self._pending_nonce(params[0])
                else:
                    response = self.web3.provider.make_request(
                        method, self._provider_params(method, params)
                    )
                    if "error" in response:
                        if (
                            method == "eth_getTransactionReceipt"
                            and "not found"
                            in response["error"].get("message", "").lower()
                        ):
                            result = None
                            return {
                                "jsonrpc": "2.0",
                                "id": request_id,
                                "result": None,
                            }
                        return {
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "error": response["error"],
                        }
                    result = response.get("result")
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": self._rpc_value(result),
                }
        except Exception as error:
            logger.exception("RPC %s raised an exception", method)
            return self._rpc_error(request_id, -32000, str(error))

    def _pending_nonce(self, address: str) -> int:
        latest = self.web3.eth.get_transaction_count(
            Web3.to_checksum_address(address), "latest"
        )
        nonces = [
            item["nonce"]
            for item in self._get_pending_transactions()
            if item["from"].lower() == address.lower()
        ]
        return max([latest, *(nonce + 1 for nonce in nonces)])

    def _fee_history(self, params: list[Any]) -> dict[str, Any]:
        if len(params) < 2:
            raise ValueError("eth_feeHistory requires a block count and newest block.")

        block_count = parse_quantity(params[0])
        if block_count < 1 or block_count > 1024:
            raise ValueError("eth_feeHistory block count must be between 1 and 1024.")

        newest_block = params[1]
        if newest_block in ("latest", "safe", "finalized", "pending"):
            newest_number = self.web3.eth.block_number
        else:
            newest_number = parse_quantity(newest_block)
        newest_number = min(newest_number, self.web3.eth.block_number)
        oldest_number = max(0, newest_number - block_count + 1)

        percentiles = params[2] if len(params) > 2 else []
        if not isinstance(percentiles, list) or any(
            not isinstance(percentile, (int, float))
            or isinstance(percentile, bool)
            or percentile < 0
            or percentile > 100
            for percentile in percentiles
        ):
            raise ValueError("eth_feeHistory reward percentiles must be between 0 and 100.")
        if percentiles != sorted(percentiles):
            raise ValueError("eth_feeHistory reward percentiles must be sorted.")

        blocks = [
            self.web3.eth.get_block(number, full_transactions=True)
            for number in range(oldest_number, newest_number + 1)
        ]
        base_fees = [int(block["baseFeePerGas"]) for block in blocks]
        gas_used_ratios = [
            int(block["gasUsed"]) / int(block["gasLimit"]) for block in blocks
        ]
        if blocks:
            last_block = blocks[-1]
            base_fees.append(
                self._next_base_fee(
                    int(last_block["baseFeePerGas"]),
                    int(last_block["gasUsed"]),
                    int(last_block["gasLimit"]),
                )
            )

        result: dict[str, Any] = {
            "oldestBlock": oldest_number,
            "baseFeePerGas": base_fees,
            "gasUsedRatio": gas_used_ratios,
        }
        if percentiles:
            result["reward"] = [
                self._fee_rewards(block, percentiles)
                for block in blocks
            ]
        return result

    @staticmethod
    def _next_base_fee(base_fee: int, gas_used: int, gas_limit: int) -> int:
        target_gas = gas_limit // 2
        if gas_used == target_gas:
            return base_fee
        if gas_used > target_gas:
            increase = max(
                1,
                base_fee * (gas_used - target_gas) // target_gas // 8,
            )
            return base_fee + increase
        decrease = base_fee * (target_gas - gas_used) // target_gas // 8
        return base_fee - decrease

    @staticmethod
    def _fee_rewards(block: Any, percentiles: list[float]) -> list[int]:
        base_fee = int(block["baseFeePerGas"])
        rewards = []
        for transaction in block["transactions"]:
            gas_used = int(transaction.get("gas", 0))
            if "maxFeePerGas" in transaction or "max_fee_per_gas" in transaction:
                max_fee = int(
                    transaction.get(
                        "maxFeePerGas", transaction.get("max_fee_per_gas", 0)
                    )
                )
                priority_fee = int(
                    transaction.get(
                        "maxPriorityFeePerGas",
                        transaction.get("max_priority_fee_per_gas", 0),
                    )
                )
                tip = min(priority_fee, max(0, max_fee - base_fee))
            else:
                gas_price = int(
                    transaction.get("gasPrice", transaction.get("gas_price", 0))
                )
                tip = max(0, gas_price - base_fee)
            if gas_used:
                rewards.append((tip, gas_used))

        rewards.sort(key=lambda item: item[0])
        total_gas = sum(gas for _, gas in rewards)
        if not total_gas:
            return [0 for _ in percentiles]

        result = []
        for percentile in percentiles:
            gas_threshold = total_gas * percentile / 100
            accumulated_gas = 0
            selected_tip = rewards[-1][0]
            for tip, gas_used in rewards:
                accumulated_gas += gas_used
                if accumulated_gas >= gas_threshold:
                    selected_tip = tip
                    break
            result.append(selected_tip)
        return result

    def _provider_params(self, method: str, params: list[Any]) -> list[Any]:
        normalized_params = list(params)
        if method not in {
            "eth_call",
            "eth_estimateGas",
            "eth_sendTransaction",
            "eth_getProof",
        } or not normalized_params or not isinstance(normalized_params[0], dict):
            return normalized_params
        transaction = dict(normalized_params[0])
        if method == "eth_call":
            transaction.setdefault("from", self.accounts[0])
        if method == "eth_estimateGas":
            transaction.setdefault("from", self.accounts[0])
            transaction.pop("nonce", None)
        return [transaction, *normalized_params[1:]]

    @classmethod
    def _rpc_value(cls, value: Any) -> Any:
        if isinstance(value, bool) or value is None:
            return value
        if isinstance(value, int):
            return hex(value)
        if isinstance(value, bytes):
            return Web3.to_hex(value)
        if isinstance(value, dict):
            formatted = {}
            for key, item in value.items():
                rpc_key = re.sub(r"_([a-z])", lambda match: match.group(1).upper(), key)
                if key == "coinbase":
                    rpc_key = "miner"
                formatted[rpc_key] = cls._rpc_value(item)
            return formatted
        if isinstance(value, (list, tuple)):
            return [cls._rpc_value(item) for item in value]
        return value

    @staticmethod
    def _rpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }

    def close(self) -> None:
        self.stopped.set()
        if self.anvil_process is not None:
            if self.web3.is_connected():
                try:
                    response = self.web3.provider.make_request(
                        "anvil_dumpState",
                        [],
                    )
                    encoded_state = response.get("result")
                    if isinstance(encoded_state, str) and encoded_state.startswith("0x"):
                        DATA_DIR.mkdir(parents=True, exist_ok=True)
                        compressed_state = bytes.fromhex(encoded_state[2:])
                        ANVIL_STATE_PATH.write_bytes(gzip.decompress(compressed_state))
                except Exception as error:
                    logger.warning("Could not dump Anvil state: %s", error)
            if self.anvil_process.poll() is None:
                self.anvil_process.terminate()
                try:
                    self.anvil_process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    self.anvil_process.kill()
                    self.anvil_process.wait(timeout=10)


def make_rpc_handler(chain: LocalChain) -> type[BaseHTTPRequestHandler]:
    class RpcHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            if self.path != "/":
                self.send_error(404)
                return
            origin = self.headers.get("Origin")
            if origin and origin != f"http://{WEB_HOST}:{WEB_PORT}":
                self.send_error(403)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length > 1_000_000:
                    self.send_error(413)
                    return
                payload = json.loads(self.rfile.read(length))
                if isinstance(payload, list):
                    response: Any = [chain.handle_rpc(item) for item in payload]
                    requests = payload
                    responses = response
                else:
                    response = chain.handle_rpc(payload)
                    requests = [payload]
                    responses = [response]
                for request, item_response in zip(requests, responses):
                    if "error" in item_response:
                        rpc_error = item_response["error"]
                        logger.warning(
                            "RPC %s failed (code=%s, data=%r): %s",
                            request.get("method", "unknown"),
                            rpc_error.get("code"),
                            rpc_error.get("data"),
                            rpc_error.get("message", "Unknown RPC error."),
                        )
                body = json.dumps(response).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header(
                    "Access-Control-Allow-Origin", f"http://{WEB_HOST}:{WEB_PORT}"
                )
                self.send_header("Vary", "Origin")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
                self.end_headers()
                self.wfile.write(body)
            except (json.JSONDecodeError, UnicodeDecodeError):
                body = json.dumps(
                    chain._rpc_error(None, -32700, "Invalid JSON request.")
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        def do_OPTIONS(self) -> None:
            self.send_response(204)
            self.send_header(
                "Access-Control-Allow-Origin", f"http://{WEB_HOST}:{WEB_PORT}"
            )
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
            self.end_headers()

        def log_message(self, format_string: str, *args: Any) -> None:
            logger.debug("RPC %s - %s", self.address_string(), format_string % args)

    return RpcHandler


def make_web_handler(chain: LocalChain) -> type[SimpleHTTPRequestHandler]:
    class WebHandler(SimpleHTTPRequestHandler):
        login_attempts: dict[str, list[float]] = {}

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(FRONTEND_DIR), **kwargs)

        def do_GET(self) -> None:
            if self.path == "/api/batching":
                self._send_json(chain.status())
                return
            if self.path == "/api/auth/session":
                profile = chain.session_profile(self._session_token())
                if profile is None:
                    self._send_json({"error": "Login required."}, 401)
                else:
                    self._send_json(profile)
                return
            if self.path == "/api/admin/users":
                try:
                    self._send_json({"users": chain.configured_accounts(self._session_token() or "")})
                except PermissionError as error:
                    self._send_json({"error": str(error)}, 403)
                return
            if self.path == "/":
                self._send_index()
                return
            super().do_GET()

        def do_POST(self) -> None:
            if not self._same_origin():
                self._send_json({"error": "Cross-origin requests are not allowed."}, 403)
                return
            try:
                body = self._read_json()
                if self.path == "/api/auth/login":
                    self._login(body)
                    return
                if self.path == "/api/auth/logout":
                    chain.logout(self._session_token())
                    self._send_json(
                        {"ok": True},
                        headers={
                            "Set-Cookie": (
                                f"{SESSION_COOKIE_NAME}=; Path=/; Max-Age=0; "
                                "HttpOnly; SameSite=Strict"
                            )
                        },
                    )
                    return

                profile = chain.session_profile(self._session_token())
                if profile is None:
                    self._send_json({"error": "Login required."}, 401)
                    return
                if self.path == "/api/batching":
                    if not profile["isAdministrator"]:
                        self._send_json({"error": "Administrator login required."}, 403)
                        return
                    result = chain.configure_batch_size(
                        body.get("minimumTransactions")
                    )
                    self._send_json(result)
                    return
                if self.path == "/api/transactions":
                    result = chain.submit_contract_transaction(
                        self._session_token() or "",
                        body.get("operation"),
                        body.get("arguments", {}),
                    )
                    self._send_json(result)
                    return
                self._send_json({"error": "Not found."}, 404)
            except (
                json.JSONDecodeError,
                UnicodeDecodeError,
                ValueError,
                TypeError,
            ) as error:
                self._send_json(
                    {"error": str(error) or "Invalid JSON request."}, 400
                )
            except PermissionError as error:
                self._send_json({"error": str(error)}, 403)
            except ContractLogicError as error:
                message = str(error) or "The contract rejected this transaction."
                logger.warning("Contract transaction would revert: %s", message)
                self._send_json({"error": f"Transaction would revert: {message}"}, 400)
            except RuntimeError as error:
                logger.exception("Could not complete local application request")
                self._send_json({"error": str(error)}, 500)

        def _read_json(self) -> dict[str, Any]:
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip()
            if content_type != "application/json":
                raise ValueError("Content-Type must be application/json.")
            length = int(self.headers.get("Content-Length", "0"))
            if length > 64_000:
                raise ValueError("Request body is too large.")
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError("JSON request body must be an object.")
            return body

        def _same_origin(self) -> bool:
            origin = self.headers.get("Origin")
            if not origin:
                return False
            parsed = urlsplit(origin)
            return (
                parsed.scheme == "http"
                and parsed.netloc == self.headers.get("Host")
                and parsed.path == ""
                and parsed.query == ""
                and parsed.fragment == ""
            )

        def _session_token(self) -> str | None:
            cookies = SimpleCookie()
            try:
                cookies.load(self.headers.get("Cookie", ""))
            except CookieError:
                return None
            cookie = cookies.get(SESSION_COOKIE_NAME)
            return None if cookie is None else cookie.value

        def _login(self, body: dict[str, Any]) -> None:
            client_ip = self.client_address[0]
            now = time.monotonic()
            recent_attempts = [
                attempt
                for attempt in self.login_attempts.get(client_ip, [])
                if now - attempt < LOGIN_WINDOW_SECONDS
            ]
            if len(recent_attempts) >= MAX_LOGIN_ATTEMPTS:
                self.login_attempts[client_ip] = recent_attempts
                self._send_json({"error": "Too many login attempts. Try again later."}, 429)
                return

            username = body.get("username")
            password = body.get("password")
            if (
                not isinstance(username, str)
                or not isinstance(password, str)
                or not username
                or not password
            ):
                raise ValueError("Username and password are required.")
            token = chain.authenticate(username, password)
            if token is None:
                recent_attempts.append(now)
                self.login_attempts[client_ip] = recent_attempts
                self._send_json({"error": "Invalid username or password."}, 401)
                return

            self.login_attempts.pop(client_ip, None)
            profile = chain.session_profile(token)
            if profile is None:
                raise RuntimeError("Could not establish an authenticated session.")
            self._send_json(
                profile,
                headers={
                    "Set-Cookie": (
                        f"{SESSION_COOKIE_NAME}={token}; Path=/; "
                        f"Max-Age={SESSION_LIFETIME_SECONDS}; HttpOnly; SameSite=Strict"
                    )
                },
            )

        def _send_index(self) -> None:
            index_path = FRONTEND_DIR / "index.html"
            if not index_path.is_file():
                self._send_json(
                    {
                        "error": (
                            "The static frontend is missing. Restore client/dist or "
                            "build it before starting the Python app."
                        )
                    },
                    503,
                )
                return
            html = index_path.read_text(encoding="utf-8")
            deployment = json.dumps(
                {
                    "chainId": CHAIN_ID,
                    "verifier": chain.verifier_address,
                    "supplyChain": chain.contract_address,
                }
            )
            script = (
                f"<script>window.__PHARMACHAIN_DEPLOYMENT__={deployment};</script>"
            )
            module_script = html.find("<script")
            if module_script < 0:
                self._send_json({"error": "Built frontend has no application script."}, 503)
                return
            html = html[:module_script] + script + html[module_script:]
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _send_json(
            self,
            value: dict[str, Any],
            status_code: int = 200,
            headers: dict[str, str] | None = None,
        ) -> None:
            body = json.dumps(value).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for name, header_value in (headers or {}).items():
                self.send_header(name, header_value)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format_string: str, *args: Any) -> None:
            logger.info("WEB %s - %s", self.address_string(), format_string % args)

    return WebHandler


def run() -> None:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / "backend" / ".env")
    raw_users = os.environ.get("PHARMACHAIN_USERS_JSON", "")
    if not raw_users:
        raise ValueError(
            "Configure PHARMACHAIN_USERS_JSON in backend/.env; see backend/.env.example "
            "and the README."
        )
    users = load_users(raw_users, account_count=10)

    if not (FRONTEND_DIR / "index.html").is_file():
        raise FileNotFoundError(
            f"Frontend build not found: {FRONTEND_DIR}. "
            "Restore the bundled static frontend before running the Python app."
        )

    chain = LocalChain(users)
    web_server = ThreadingHTTPServer(
        (WEB_HOST, WEB_PORT), make_web_handler(chain)
    )
    web_thread = threading.Thread(target=web_server.serve_forever, daemon=True)
    monitor_thread = threading.Thread(
        target=_monitor_batches, args=(chain,), daemon=True
    )
    web_thread.start()
    monitor_thread.start()

    logger.info("Python local blockchain RPC: http://%s:%s", RPC_HOST, RPC_PORT)
    logger.info("PharmaChain frontend: http://%s:%s", WEB_HOST, WEB_PORT)
    logger.info("Anvil state file: %s", ANVIL_STATE_PATH)
    logger.info("Automining disabled; default registration batch size is 10.")
    logger.warning(
        "The following stable Anvil development addresses and funds persist "
        "through normal restarts. Private keys remain local to the backend."
    )
    for index, address in enumerate(chain.accounts):
        logger.info("Account #%s: %s", index, address)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Stopping Python local blockchain.")
    finally:
        chain.close()
        web_server.shutdown()
        web_server.server_close()


def _monitor_batches(chain: LocalChain) -> None:
    while not chain.stopped.wait(POLL_INTERVAL_SECONDS):
        chain.process_pending()


def main() -> None:
    try:
        run()
    except (OSError, ValueError) as error:
        logger.error("Could not start the Python app: %s", error)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
