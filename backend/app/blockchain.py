
import json
import os
import time

from pathlib import Path
from dotenv import load_dotenv
from web3 import Web3


# Load blockchain configuration
PROJECT_ROOT = Path(__file__).resolve().parents[2]
BLOCKCHAIN_DIR = PROJECT_ROOT / "blockchain"

load_dotenv(PROJECT_ROOT / ".env")

RPC_URL = os.getenv("RPC_URL")
ADMIN_PRIVATE_KEY = os.getenv("ADMIN_PRIVATE_KEY")
ADMIN_ADDRESS = os.getenv("ADMIN_ADDRESS")
CONTRACT_ADDRESS = os.getenv("ZKP_VERIFIER_ADDRESS")

ABI_PATH = (
    BLOCKCHAIN_DIR
    / "artifacts"
    / "contracts"
    / "ZKPVerifier.sol"
    / "ZKPVerifier.json"
)


# Connect to the local blockchain
w3 = Web3(Web3.HTTPProvider(RPC_URL))

if not w3.is_connected():
    raise ConnectionError("Unable to connect to Hardhat blockchain")

# Load contract ABI
with open(ABI_PATH, "r", encoding="utf-8") as file:
    contract_abi = json.load(file)["abi"]

# Initialize smart contract
contract_address = Web3.to_checksum_address(CONTRACT_ADDRESS)

contract = w3.eth.contract(
    address=contract_address,
    abi=contract_abi
)

# Initialize Admin account
admin_account = w3.eth.account.from_key(ADMIN_PRIVATE_KEY)
admin_address = Web3.to_checksum_address(ADMIN_ADDRESS)

if admin_account.address.lower() != admin_address.lower():
    raise ValueError("Admin private key and address do not match")


# Send a signed blockchain transaction
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

    receipt = w3.eth.wait_for_transaction_receipt(
        transaction_hash
    )

    transaction_time = time.perf_counter() - transaction_start_time
    
    if receipt["status"] != 1:
        raise RuntimeError("Blockchain transaction failed")

    return {
        "transaction_hash": transaction_hash.hex(),
        "block_number": receipt["blockNumber"],
        "gas_used": receipt["gasUsed"],
        "transaction_time_seconds": transaction_time,
        "status": "success"
    }


# Register a stakeholder using Admin account
def register_stakeholder(
    stakeholder_address: str,
    role: int
) -> dict:

    stakeholder_address = Web3.to_checksum_address(
        stakeholder_address
    )

    function = contract.functions.registerStakeholder(
        stakeholder_address,
        role
    )

    return send_transaction(
        function,
        ADMIN_PRIVATE_KEY
    )


# Revoke a stakeholder using Admin account
def revoke_stakeholder(stakeholder_address: str) -> dict:

    stakeholder_address = Web3.to_checksum_address(
        stakeholder_address
    )

    function = contract.functions.revokeStakeholder(
        stakeholder_address
    )

    return send_transaction(
        function,
        ADMIN_PRIVATE_KEY
    )


# Get a stakeholder's registered role
def get_stakeholder_role(stakeholder_address: str) -> int:

    stakeholder_address = Web3.to_checksum_address(
        stakeholder_address
    )

    return contract.functions.stakeholderRoles(
        stakeholder_address
    ).call()


# Check attribute access permission
def can_access_attribute(
    role: int,
    attribute_index: int
) -> bool:

    return contract.functions.canAccessAttribute(
        role,
        attribute_index
    ).call()


# Verify a Groth16 proof on the blockchain
def verify_supply_chain(
    proof: dict,
    public_signals: list,
    requested_attributes: list[int],
    stakeholder_private_key: str
) -> dict:

    # Initialize stakeholder wallet
    stakeholder_account = w3.eth.account.from_key(
        stakeholder_private_key
    )

    stakeholder_address = stakeholder_account.address

    # Check stakeholder role
    role = get_stakeholder_role(stakeholder_address)

    if role in (0, 1):
        raise PermissionError(
            "Stakeholder is not authorized to verify records"
        )

    # Check requested attributes
    if not requested_attributes:
        raise ValueError("No attributes requested")

    if len(requested_attributes) != len(set(requested_attributes)):
        raise ValueError("Duplicate attributes requested")

    for index in requested_attributes:
        if not can_access_attribute(role, index):
            raise PermissionError(
                f"Access denied for attribute index {index}"
            )

    # Check public signals
    if len(public_signals) != 11:
        raise ValueError("Exactly 11 public signals are required")

    if int(public_signals[0]) != 1:
        raise ValueError(
            "Supply-chain data mismatch. Verification rejected."
        )

    # Prepare Groth16 proof coordinates
    p_a = [
        int(proof["pi_a"][0]),
        int(proof["pi_a"][1])
    ]

    p_b = [
        [
            int(proof["pi_b"][0][1]),
            int(proof["pi_b"][0][0])
        ],
        [
            int(proof["pi_b"][1][1]),
            int(proof["pi_b"][1][0])
        ]
    ]

    p_c = [
        int(proof["pi_c"][0]),
        int(proof["pi_c"][1])
    ]

    signals = [int(value) for value in public_signals]

    # Prepare blockchain verification transaction
    function = contract.functions.verifySupplyChain(
        p_a,
        p_b,
        p_c,
        signals,
        requested_attributes
    )

    # Check transaction before sending it
    function.call({
        "from": stakeholder_address
    })

    # Submit verification transaction
    return send_transaction(
        function,
        stakeholder_private_key
    )
