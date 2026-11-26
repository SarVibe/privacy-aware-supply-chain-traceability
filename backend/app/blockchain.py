
import json
import os
import time
import re

from pathlib import Path

from dotenv import load_dotenv
from web3 import Web3
from web3.exceptions import TransactionNotFound


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BLOCKCHAIN_DIR = PROJECT_ROOT / "blockchain"

load_dotenv(PROJECT_ROOT / ".env")

RPC_URL = os.getenv("RPC_URL", "http://127.0.0.1:8545")
ADMIN_PRIVATE_KEY = os.getenv("ADMIN_PRIVATE_KEY")
ADMIN_ADDRESS = os.getenv("ADMIN_ADDRESS")
CONTRACT_ADDRESS = os.getenv("ZKP_VERIFIER_ADDRESS")

ABI_PATH = (
    BLOCKCHAIN_DIR
    / "artifacts"
    / "contracts"
    / "SelectiveZKPVerifier.sol"
    / "SelectiveZKPVerifier.json"
)

if not ADMIN_PRIVATE_KEY or not ADMIN_ADDRESS:
    raise RuntimeError("Admin blockchain configuration is missing.")

if not CONTRACT_ADDRESS:
    raise RuntimeError("ZKP_VERIFIER_ADDRESS is not configured.")

w3 = Web3(Web3.HTTPProvider(RPC_URL))

if not w3.is_connected():
    raise ConnectionError("Unable to connect to Hardhat blockchain.")

with open(ABI_PATH, "r", encoding="utf-8") as file:
    contract_abi = json.load(file)["abi"]

contract_address = Web3.to_checksum_address(CONTRACT_ADDRESS)

contract = w3.eth.contract(
    address=contract_address,
    abi=contract_abi
)

admin_account = w3.eth.account.from_key(ADMIN_PRIVATE_KEY)
admin_address = Web3.to_checksum_address(ADMIN_ADDRESS)

if admin_account.address.lower() != admin_address.lower():
    raise ValueError("Admin private key and address do not match.")


def send_transaction(function, private_key: str) -> dict:
    account = w3.eth.account.from_key(private_key)
    address = account.address

    transaction = function.build_transaction({
        "from": address,
        "nonce": w3.eth.get_transaction_count(address),
        "chainId": w3.eth.chain_id,
        "gas": 600000,
        "gasPrice": w3.eth.gas_price
    })

    signed_transaction = account.sign_transaction(transaction)

    transaction_start_time = time.perf_counter()

    transaction_hash = w3.eth.send_raw_transaction(
        signed_transaction.raw_transaction
    )

    receipt = w3.eth.wait_for_transaction_receipt(transaction_hash)

    transaction_time = time.perf_counter() - transaction_start_time

    if receipt["status"] != 1:
        raise RuntimeError("Blockchain transaction failed.")

    return {
        "transaction_hash": transaction_hash.hex(),
        "block_number": receipt["blockNumber"],
        "gas_used": receipt["gasUsed"],
        "transaction_time_seconds": transaction_time,
        "status": "success"
    }


def register_stakeholder(
    stakeholder_address: str,
    role: int
) -> dict:
    stakeholder_address = Web3.to_checksum_address(stakeholder_address)

    function = contract.functions.registerStakeholder(
        stakeholder_address,
        role
    )

    return send_transaction(function, ADMIN_PRIVATE_KEY)


def revoke_stakeholder(stakeholder_address: str) -> dict:
    stakeholder_address = Web3.to_checksum_address(stakeholder_address)

    function = contract.functions.revokeStakeholder(
        stakeholder_address
    )

    return send_transaction(function, ADMIN_PRIVATE_KEY)


def get_stakeholder_role(stakeholder_address: str) -> int:
    stakeholder_address = Web3.to_checksum_address(stakeholder_address)

    return contract.functions.stakeholderRoles(
        stakeholder_address
    ).call()


def can_access_attribute(role: int, attribute_index: int) -> bool:
    return contract.functions.canAccessAttribute(
        role,
        attribute_index
    ).call()


def get_record_by_transaction_hash(transaction_hash: str) -> dict:
    if not isinstance(transaction_hash, str) or not re.fullmatch(r"0x[0-9a-fA-F]{64}", transaction_hash):        raise ValueError("Invalid transaction hash.")

    try:
        receipt = w3.eth.get_transaction_receipt(transaction_hash)
    except TransactionNotFound:
        raise ValueError("Record transaction was not found.")

    if receipt["status"] != 1:
        raise ValueError("Record storage transaction failed.")

    if (
        receipt["to"] is None
        or receipt["to"].lower() != contract_address.lower()
    ):
        raise ValueError("Transaction does not belong to the selective contract.")

    events = contract.events.RecordStored().process_receipt(receipt)

    if len(events) != 1:
        raise ValueError("RecordStored event was not found.")

    event_args = events[0]["args"]

    record_id = int(event_args["recordId"])

    manufacturer, created_at, exists = (
        contract.functions.getRecordInfo(record_id).call()
    )

    if not exists:
        raise ValueError("Record does not exist.")

    if manufacturer.lower() != event_args["manufacturer"].lower():
        raise ValueError("Record manufacturer mismatch.")

    commitments = contract.functions.getRecordCommitments(
        record_id
    ).call()

    return {
        "transaction_hash": Web3.to_hex(receipt["transactionHash"]),
        "record_id": record_id,
        "manufacturer": Web3.to_checksum_address(manufacturer),
        "created_at": int(created_at),
        "commitments": [str(value) for value in commitments]
    }
