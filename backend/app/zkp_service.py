
import json
import os
import re
import subprocess
import tempfile
import time

from pathlib import Path

from backend.app.access_policy import get_allowed_attributes


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BLOCKCHAIN_DIR = PROJECT_ROOT / "blockchain"
SELECTIVE_DIR = (
    BLOCKCHAIN_DIR / "circuits" / "build" / "selective"
)
CIRCUIT_JS_DIR = SELECTIVE_DIR / "SelectiveSupplyChain_js"

INPUT_WASM = CIRCUIT_JS_DIR / "SelectiveSupplyChain.wasm"
WITNESS_SCRIPT = CIRCUIT_JS_DIR / "generate_witness.cjs"
R1CS_FILE = SELECTIVE_DIR / "SelectiveSupplyChain.r1cs"
PROVING_KEY = SELECTIVE_DIR / "SelectiveSupplyChain_final.zkey"
VERIFICATION_KEY = SELECTIVE_DIR / "verification_key.json"

NPX_COMMAND = "npx.cmd" if os.name == "nt" else "npx"

ATTRIBUTES = [
    "product_id",
    "product_name",
    "batch_number",
    "manufacturing_date",
    "expiry_date",
    "manufacturer_id",
    "shipment_id",
    "quantity",
    "source_location",
    "destination_location",
]

STRING_ATTRIBUTE_INDEXES = [0, 1, 2, 5, 6, 8, 9]

STRING_ATTRIBUTE_NAMES = [
    ATTRIBUTES[index]
    for index in STRING_ATTRIBUTE_INDEXES
]

ROLE_NAMES = {
    2: "manufacturer",
    3: "logistics",
    4: "warehouse",
    5: "distributor",
    6: "pharmacy",
}


def run_command(command: list[str]) -> None:
    result = subprocess.run(
        command,
        cwd=BLOCKCHAIN_DIR,
        capture_output=True,
        text=True,
        check=False
    )

    if result.returncode != 0:
        raise RuntimeError(
            result.stderr or result.stdout or "ZKP command failed"
        )


def validate_decimal(value, name: str, max_bits: int) -> str:
    value = str(value)

    if not re.fullmatch(r"[0-9]+", value):
        raise ValueError(f"Invalid numeric value for {name}.")

    number = int(value)

    if number >= 2 ** max_bits:
        raise ValueError(f"Value exceeds the allowed range for {name}.")

    return str(number)


def build_circuit_input(data: dict) -> dict:
    role = data.get("role")

    if role not in ROLE_NAMES:
        raise ValueError("Invalid stakeholder role.")

    allowed_attributes = get_allowed_attributes(
        ROLE_NAMES[role]
    )

    values = data.get("values")
    salts = data.get("salts")
    commitments = data.get("commitments")

    if not isinstance(values, dict) or not isinstance(salts, dict):
        raise ValueError("Invalid values or salts.")

    if not isinstance(commitments, list) or len(commitments) != 10:
        raise ValueError("Exactly 10 on-chain commitments are required.")

    encoded_commitments = [
        validate_decimal(value, ATTRIBUTES[index], 254)
        for index, value in enumerate(commitments)
    ]

    encoded_values = ["0"] * 10
    encoded_salts = ["0"] * 10

    for index, attribute in enumerate(ATTRIBUTES):
        if attribute not in allowed_attributes:
            continue

        if attribute not in values or attribute not in salts:
            raise ValueError(
                f"Missing value or salt for {attribute}."
            )

        if not isinstance(values[attribute], str):
            raise ValueError(f"Invalid value for {attribute}.")

        if not values[attribute].strip():
            raise ValueError(f"Empty value for {attribute}.")

        encoded_salts[index] = validate_decimal(
            salts[attribute],
            f"{attribute} salt",
            248
        )

        if index in STRING_ATTRIBUTE_INDEXES:
            string_value = values[attribute]
            string_bytes = string_value.encode("utf-8")

            if len(string_bytes) > 62:
                raise ValueError(
                    f"{attribute} must not exceed 62 UTF-8 bytes."
                )

            encoded_values[index] = string_value
        else:
            max_bits = 64 if attribute == "quantity" else 27

            encoded_values[index] = validate_decimal(
                values[attribute],
                attribute,
                max_bits
            )

    string_bytes = []
    string_lengths = []

    for attribute in STRING_ATTRIBUTE_NAMES:
        index = ATTRIBUTES.index(attribute)

        if attribute in allowed_attributes:
            raw_bytes = encoded_values[index].encode("utf-8")
        else:
            raw_bytes = b""

        padded_bytes = list(raw_bytes) + [0] * (62 - len(raw_bytes))

        string_bytes.append(padded_bytes)
        string_lengths.append(len(raw_bytes))

    return {
        "commitments": encoded_commitments,
        "role": str(role),
        "stringBytes": string_bytes,
        "stringLengths": string_lengths,
        "manufacturing_date": encoded_values[3],
        "expiry_date": encoded_values[4],
        "quantity": encoded_values[7],
        "salts": encoded_salts
    }


def generate_proof(data: dict) -> dict:
    required_files = [
        INPUT_WASM,
        WITNESS_SCRIPT,
        R1CS_FILE,
        PROVING_KEY,
        VERIFICATION_KEY
    ]

    for file_path in required_files:
        if not file_path.exists():
            raise FileNotFoundError(
                f"Required selective ZKP file not found: {file_path}"
            )

    circuit_input = build_circuit_input(data)

    with tempfile.TemporaryDirectory(prefix="zkp_") as temp_dir:
        temp_path = Path(temp_dir)

        input_file = temp_path / "input.json"
        witness_file = temp_path / "witness.wtns"
        proof_file = temp_path / "proof.json"
        public_file = temp_path / "public.json"

        input_file.write_text(
            json.dumps(circuit_input),
            encoding="utf-8"
        )

        run_command([
            "node",
            str(WITNESS_SCRIPT),
            str(INPUT_WASM),
            str(input_file),
            str(witness_file)
        ])

        run_command([
            NPX_COMMAND,
            "snarkjs",
            "wtns",
            "check",
            str(R1CS_FILE),
            str(witness_file)
        ])

        proof_start_time = time.perf_counter()

        run_command([
            NPX_COMMAND,
            "snarkjs",
            "groth16",
            "prove",
            str(PROVING_KEY),
            str(witness_file),
            str(proof_file),
            str(public_file)
        ])

        proof_generation_time = (
            time.perf_counter() - proof_start_time
        )

        verification_start_time = time.perf_counter()

        run_command([
            NPX_COMMAND,
            "snarkjs",
            "groth16",
            "verify",
            str(VERIFICATION_KEY),
            str(public_file),
            str(proof_file)
        ])

        proof_verification_time = (
            time.perf_counter() - verification_start_time
        )

        proof = json.loads(
            proof_file.read_text(encoding="utf-8")
        )

        public_signals = json.loads(
            public_file.read_text(encoding="utf-8")
        )

        if len(public_signals) != 11:
            raise RuntimeError(
                "Unexpected selective circuit public signal count."
            )

        expected_public_signals = (
            circuit_input["commitments"]
            + [circuit_input["role"]]
        )

        if public_signals != expected_public_signals:
            raise RuntimeError(
                "Generated public signals do not match the record commitments and role."
            )

        return {
            "proof": proof,
            "public_signals": public_signals,
            "proof_generation_time_seconds": proof_generation_time,
            "proof_verification_time_seconds": proof_verification_time
        }
