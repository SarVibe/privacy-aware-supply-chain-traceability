
import json
import os
import shutil
import subprocess
import tempfile
import time

from pathlib import Path


# Define project and blockchain paths
PROJECT_ROOT = Path(__file__).resolve().parents[2]
BLOCKCHAIN_DIR = PROJECT_ROOT / "blockchain"

# Define ZKP file paths
INPUT_SCRIPT = BLOCKCHAIN_DIR / "generate_input.js"
WITNESS_SCRIPT = BLOCKCHAIN_DIR / "SupplyChain_js" / "generate_witness.js"
WASM_FILE = BLOCKCHAIN_DIR / "SupplyChain_js" / "SupplyChain.wasm"
R1CS_FILE = BLOCKCHAIN_DIR / "SupplyChain.r1cs"
PROVING_KEY = BLOCKCHAIN_DIR / "SupplyChain_final.zkey"
VERIFICATION_KEY = BLOCKCHAIN_DIR / "verification_key.json"

# Select npm command based on operating system
NPX_COMMAND = "npx.cmd" if os.name == "nt" else "npx"


# Run an external command and handle errors
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


# Generate a Groth16 proof from actual and expected data
def generate_proof(data: dict) -> dict:

    # Check required blockchain files
    required_files = [
        INPUT_SCRIPT,
        WITNESS_SCRIPT,
        WASM_FILE,
        R1CS_FILE,
        PROVING_KEY,
        VERIFICATION_KEY
    ]

    for file_path in required_files:
        if not file_path.exists():
            raise FileNotFoundError(
                f"Required ZKP file not found: {file_path}"
            )

    # Create temporary storage for sensitive input and proof files
    with tempfile.TemporaryDirectory(prefix="zkp_") as temp_dir:

        temp_path = Path(temp_dir)

        source_file = temp_path / "source.json"
        input_file = temp_path / "input.json"
        witness_file = temp_path / "witness.wtns"
        proof_file = temp_path / "proof.json"
        public_file = temp_path / "public.json"

        # Save actual and expected values temporarily
        source_file.write_text(
            json.dumps(data),
            encoding="utf-8"
        )

        # Generate Circom input using Poseidon hashing
        run_command([
            "node",
            str(INPUT_SCRIPT),
            str(source_file),
            str(input_file)
        ])

        # Generate Circom witness
        run_command([
            "node",
            str(WITNESS_SCRIPT),
            str(WASM_FILE),
            str(input_file),
            str(witness_file)
        ])

        # Validate generated witness
        run_command([
            NPX_COMMAND,
            "snarkjs",
            "wtns",
            "check",
            str(R1CS_FILE),
            str(witness_file)
        ])

        # Generate Groth16 proof
        # Measure Groth16 proof generation time
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

        proof_generation_time = time.perf_counter() - proof_start_time

        # Verify generated Groth16 proof
        # Measure Groth16 proof verification time
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

        proof_verification_time = time.perf_counter() - verification_start_time

        # Read generated proof and public signals
        proof = json.loads(proof_file.read_text(encoding="utf-8"))
        public_signals = json.loads(
            public_file.read_text(encoding="utf-8")
        )

        # Read the public validity result
        is_valid = public_signals[0] == "1"

        return {
            "proof": proof,
            "public_signals": public_signals,
            "is_valid": is_valid,
            "proof_generation_time_seconds": proof_generation_time,
            "proof_verification_time_seconds": proof_verification_time
        }
