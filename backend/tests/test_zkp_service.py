import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from backend.app import zkp_service


class TestZKPService(unittest.TestCase):

    @patch("backend.app.zkp_service.run_command")
    def test_generate_valid_proof(self, mock_run_command):

        with TemporaryDirectory() as temp_dir:

            temp_path = Path(temp_dir)

            # Create temporary ZKP files
            file_paths = [
                "input.js",
                "generate_witness.js",
                "SupplyChain.wasm",
                "SupplyChain.r1cs",
                "SupplyChain_final.zkey",
                "verification_key.json"
            ]

            created_files = []

            for filename in file_paths:
                file_path = temp_path / filename
                file_path.touch()
                created_files.append(file_path)

            proof_data = {
                "pi_a": ["1", "2"],
                "pi_b": [["3", "4"], ["5", "6"]],
                "pi_c": ["7", "8"],
                "protocol": "groth16"
            }

            public_signals = ["1"] + ["0"] * 10

            def create_mock_outputs(command):

                # Identify proof and public output paths
                if "groth16" in command and "prove" in command:
                    Path(command[-2]).write_text(
                        json.dumps(proof_data),
                        encoding="utf-8"
                    )
                    Path(command[-1]).write_text(
                        json.dumps(public_signals),
                        encoding="utf-8"
                    )

            mock_run_command.side_effect = create_mock_outputs

            # Replace actual ZKP file paths
            with (
                patch.object(zkp_service, "INPUT_SCRIPT", created_files[0]),
                patch.object(zkp_service, "WITNESS_SCRIPT", created_files[1]),
                patch.object(zkp_service, "WASM_FILE", created_files[2]),
                patch.object(zkp_service, "R1CS_FILE", created_files[3]),
                patch.object(zkp_service, "PROVING_KEY", created_files[4]),
                patch.object(zkp_service, "VERIFICATION_KEY", created_files[5])
            ):

                result = zkp_service.generate_proof({
                    "actual": {},
                    "expected": {}
                })

            self.assertTrue(result["is_valid"])
            self.assertEqual(result["public_signals"], public_signals)
            self.assertEqual(result["proof"], proof_data)
            self.assertIn("proof_generation_time_seconds", result)
            self.assertIn("proof_verification_time_seconds", result)

            self.assertEqual(mock_run_command.call_count, 5)

    @patch("backend.app.zkp_service.run_command")
    def test_generate_invalid_data_result(self, mock_run_command):

        with TemporaryDirectory() as temp_dir:

            temp_path = Path(temp_dir)

            filenames = [
                "input.js",
                "generate_witness.js",
                "SupplyChain.wasm",
                "SupplyChain.r1cs",
                "SupplyChain_final.zkey",
                "verification_key.json"
            ]

            created_files = []

            for filename in filenames:
                file_path = temp_path / filename
                file_path.touch()
                created_files.append(file_path)

            proof_data = {"proof": "mock"}

            public_signals = ["0"] + ["0"] * 10

            def create_mock_outputs(command):

                if "groth16" in command and "prove" in command:
                    Path(command[-2]).write_text(
                        json.dumps(proof_data),
                        encoding="utf-8"
                    )
                    Path(command[-1]).write_text(
                        json.dumps(public_signals),
                        encoding="utf-8"
                    )

            mock_run_command.side_effect = create_mock_outputs

            with (
                patch.object(zkp_service, "INPUT_SCRIPT", created_files[0]),
                patch.object(zkp_service, "WITNESS_SCRIPT", created_files[1]),
                patch.object(zkp_service, "WASM_FILE", created_files[2]),
                patch.object(zkp_service, "R1CS_FILE", created_files[3]),
                patch.object(zkp_service, "PROVING_KEY", created_files[4]),
                patch.object(zkp_service, "VERIFICATION_KEY", created_files[5])
            ):

                result = zkp_service.generate_proof({
                    "actual": {},
                    "expected": {}
                })

            self.assertFalse(result["is_valid"])
            self.assertEqual(result["public_signals"][0], "0")

    def test_missing_required_file(self):

        with patch.object(
            zkp_service,
            "INPUT_SCRIPT",
            Path("missing_input.js")
        ):

            with self.assertRaises(FileNotFoundError):
                zkp_service.generate_proof({
                    "actual": {},
                    "expected": {}
                })


if __name__ == "__main__":
    unittest.main()