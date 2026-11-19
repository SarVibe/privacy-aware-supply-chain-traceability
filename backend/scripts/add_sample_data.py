import argparse
import getpass
import json
import re
import sys
import time
import uuid
from http.cookiejar import CookieJar
from typing import Any
from urllib.parse import urlsplit
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen

from web3 import Web3
from web3.exceptions import TransactionNotFound


EXPECTED_CHAIN_ID = 131277322940537
DEFAULT_RPC_URL = "http://127.0.0.1:8546"
DEFAULT_WEB_URL = "http://127.0.0.1:5173"
ALLOWED_BATCH_SIZES = (2, 5, 10, 20, 50)
CONTRACT_ABI = [
    {
        "inputs": [],
        "name": "administrator",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "address", "name": "", "type": "address"}],
        "name": "stakeholderRoles",
        "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "stakeholder", "type": "address"},
            {"internalType": "uint8", "name": "role", "type": "uint8"},
        ],
        "name": "setStakeholderRole",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "bytes32", "name": "commitment", "type": "bytes32"}],
        "name": "registerProduct",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]


def deployment_from_web(web_url: str) -> dict[str, Any]:
    request = Request(web_url.rstrip("/") + "/", headers={"Accept": "text/html"})
    try:
        with urlopen(request, timeout=10) as response:
            html = response.read().decode("utf-8")
    except (HTTPError, URLError, TimeoutError) as error:
        raise RuntimeError(f"Could not read the running app at {web_url}: {error}") from error

    match = re.search(
        r"window\.__PHARMACHAIN_DEPLOYMENT__=(\{[^;]+\});",
        html,
    )
    if not match:
        raise RuntimeError("The app did not provide its deployed contract address.")
    return json.loads(match.group(1))


def sample_commitment(run_id: str, sample_number: int) -> bytes:
    return Web3.keccak(text=f"PharmaChain CLI sample {run_id} product {sample_number}")


def prompt_secret(label: str) -> str:
    secret = getpass.getpass(f"{label}: ").strip()
    if not secret:
        raise ValueError(f"{label} cannot be empty.")
    return secret


def api_request(
    opener: Any, url: str, origin: str, payload: dict[str, Any]
) -> dict[str, Any]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Origin": origin},
        method="POST",
    )
    try:
        with opener.open(request, timeout=10) as response:
            result = json.loads(response.read())
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        try:
            message = json.loads(detail).get("error", detail)
        except json.JSONDecodeError:
            message = detail
        raise RuntimeError(
            str(message) or f"Application request failed: {error.code}"
        ) from error
    except (URLError, TimeoutError) as error:
        raise RuntimeError(f"Could not reach the application at {url}: {error}") from error
    if not isinstance(result, dict):
        raise RuntimeError("The application returned an invalid response.")
    return result


def sign_in(web_url: str, username: str, password: str) -> tuple[Any, dict[str, Any]]:
    parsed_url = urlsplit(web_url)
    if parsed_url.scheme != "http" or not parsed_url.netloc:
        raise ValueError("The local application URL must use HTTP.")
    origin = f"{parsed_url.scheme}://{parsed_url.netloc}"
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    profile = api_request(
        opener,
        web_url.rstrip("/") + "/api/auth/login",
        origin,
        {"username": username, "password": password},
    )
    return opener, profile


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Submit separate on-chain sample product registrations."
    )
    parser.add_argument(
        "--count",
        type=int,
        default=10,
        help="Number of sample registrations to submit (default: 10).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        choices=ALLOWED_BATCH_SIZES,
        default=10,
        help="Minimum registrations per block (default: 10).",
    )
    parser.add_argument("--rpc-url", default=DEFAULT_RPC_URL)
    parser.add_argument("--web-url", default=DEFAULT_WEB_URL)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.count < 1:
        raise ValueError("--count must be at least 1.")

    web3 = Web3(Web3.HTTPProvider(args.rpc_url, request_kwargs={"timeout": 10}))
    if not web3.is_connected():
        raise RuntimeError(f"Could not connect to the Python RPC at {args.rpc_url}.")
    if web3.eth.chain_id != EXPECTED_CHAIN_ID:
        raise RuntimeError(
            f"Wrong chain ID at {args.rpc_url}: expected {EXPECTED_CHAIN_ID}, "
            f"received {web3.eth.chain_id}."
        )

    deployment = deployment_from_web(args.web_url)
    if int(deployment["chainId"]) != EXPECTED_CHAIN_ID:
        raise RuntimeError("The frontend and Python RPC report different chain IDs.")
    contract_address = Web3.to_checksum_address(deployment["supplyChain"])
    contract = web3.eth.contract(address=contract_address, abi=CONTRACT_ABI)

    admin_username = input("Administrator username: ").strip()
    admin_password = prompt_secret("Administrator password")
    admin_opener, admin_profile = sign_in(args.web_url, admin_username, admin_password)
    if not admin_profile.get("isAdministrator"):
        raise RuntimeError("The configured administrator login is required.")
    result = api_request(
        admin_opener,
        args.web_url.rstrip("/") + "/api/batching",
        f"{urlsplit(args.web_url).scheme}://{urlsplit(args.web_url).netloc}",
        {"minimumTransactions": args.batch_size},
    )
    if "error" in result:
        raise RuntimeError(result["error"])

    manufacturer_username = input("Manufacturer username: ").strip()
    manufacturer_password = prompt_secret("Manufacturer password")
    manufacturer_opener, manufacturer_profile = sign_in(
        args.web_url, manufacturer_username, manufacturer_password
    )
    manufacturer_address = Web3.to_checksum_address(manufacturer_profile["address"])
    if contract.functions.stakeholderRoles(manufacturer_address).call() != 1:
        raise RuntimeError(
            "This account does not have the Manufacturer role. Sign in as admin "
            "and assign the role before importing samples."
        )

    run_id = uuid.uuid4().hex
    hashes = []
    origin = f"{urlsplit(args.web_url).scheme}://{urlsplit(args.web_url).netloc}"
    for sample_number in range(1, args.count + 1):
        result = api_request(
            manufacturer_opener,
            args.web_url.rstrip("/") + "/api/transactions",
            origin,
            {
                "operation": "registerProduct",
                "arguments": {
                    "commitment": Web3.to_hex(
                        sample_commitment(run_id, sample_number)
                    ),
                    "qgramHashes": [],
                },
            },
        )
        transaction_hash = Web3.to_bytes(hexstr=result["hash"])
        hashes.append(transaction_hash)
        print(
            f"Submitted sample registration {sample_number}/{args.count}: "
            f"{Web3.to_hex(transaction_hash)}"
        )

    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        receipts = []
        for transaction_hash in hashes:
            try:
                receipts.append(web3.eth.get_transaction_receipt(transaction_hash))
            except TransactionNotFound:
                receipts.append(None)
        if all(receipt is not None for receipt in receipts):
            break
        time.sleep(0.25)

    confirmed = [
        receipt for receipt in receipts if receipt is not None and receipt["status"] == 1
    ]
    pending_count = len(hashes) - len(confirmed)
    print(
        f"Confirmed {len(confirmed)} of {len(hashes)} sample registrations; "
        f"{pending_count} remain pending. Batch threshold: {args.batch_size}."
    )
    if pending_count:
        print("Pending transactions remain queued until the configured threshold is reached.")
    print(
        "These sample commitments are opaque demo values; they do not map to "
        "product details for form-based Groth16 verification."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
