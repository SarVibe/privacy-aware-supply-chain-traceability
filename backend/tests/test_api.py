
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from backend.app.main import app
# Import the authentication dependency used by protected API endpoints.
from backend.app.auth import get_current_user

class TestSupplyChainAPI(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    # Simulate an authenticated stakeholder for API tests.
    def authenticate_as(self, role):
        self.client.app.dependency_overrides[get_current_user] = (
            lambda: {
                "wallet_address": "0xTestStakeholder",
                "role": role
            }
        )

    # Clear authentication overrides after each test.
    def tearDown(self):
        self.client.app.dependency_overrides.clear()

    # Root endpoint
    def test_root_endpoint(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["system"],
            "System 1 - ZKP"
        )

    # Health endpoint
    def test_health_endpoint(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["status"],
            "healthy"
        )

    # Successful ZKP generation
    @patch("backend.app.main.generate_proof")
    def test_generate_proof_success(self, mock_generate):

        mock_generate.return_value = {
            "proof": {"pi_a": ["1", "2"]},
            "public_signals": ["1"] + ["0"] * 10,
            "is_valid": True,
            "proof_generation_time_seconds": 1.2,
            "proof_verification_time_seconds": 0.8
        }

        # Authenticate as Manufacturer before generating a proof.
        self.authenticate_as(2)

        response = self.client.post(
            "/zkp/generate-proof",
            json={
                "actual": {"product_id": "P001"},
                "expected": {"product_id": "P001"}
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["is_valid"])
        self.assertIn("proof", response.json())

    # ZKP generation error
    @patch("backend.app.main.generate_proof")
    def test_generate_proof_error(self, mock_generate):

        mock_generate.side_effect = RuntimeError(
            "ZKP command failed"
        )

        # Authenticate as Manufacturer before generating a proof.
        self.authenticate_as(2)

        response = self.client.post(
            "/zkp/generate-proof",
            json={
                "actual": {"product_id": "P001"},
                "expected": {"product_id": "P001"}
            }
        )

        self.assertEqual(response.status_code, 400)

    # Successful blockchain verification
    @patch("backend.app.main.verify_supply_chain")
    def test_blockchain_verification_success(self, mock_verify):

        mock_verify.return_value = {
            "status": "success",
            "gas_used": 300000
        }

        # Authenticate as Manufacturer before blockchain verification.
        self.authenticate_as(2)

        response = self.client.post(
            "/zkp/verify-on-chain",
            json={
                "proof": {"pi_a": ["1", "2"]},
                "public_signals": ["1"] + ["0"] * 10,
                "requested_attributes": [0, 2, 4],
                "stakeholder_private_key": "test-private-key"
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["transaction"]["status"],
            "success"
        )

    # Unauthorized verification
    @patch("backend.app.main.verify_supply_chain")
    def test_blockchain_verification_denied(self, mock_verify):

        mock_verify.side_effect = PermissionError(
            "Stakeholder is not authorized"
        )

        # Authenticate as Manufacturer before blockchain verification.
        self.authenticate_as(2)

        response = self.client.post(
            "/zkp/verify-on-chain",
            json={
                "proof": {"pi_a": ["1", "2"]},
                "public_signals": ["1"] + ["0"] * 10,
                "requested_attributes": [0],
                "stakeholder_private_key": "test-private-key"
            }
        )

        self.assertEqual(response.status_code, 400)

    # Successful stakeholder registration
    @patch("backend.app.main.register_stakeholder")
    def test_register_stakeholder_success(self, mock_register):

        mock_register.return_value = {
            "status": "success",
            "gas_used": 48760
        }

        # Authenticate as Admin before managing stakeholders.
        self.authenticate_as(1)

        response = self.client.post(
            "/admin/register-stakeholder",
            json={
                "stakeholder_address":
                    "0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65",
                "role": 4
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["role"],
            4
        )

    # Invalid stakeholder role
    def test_register_invalid_role(self):

        # Authenticate as Admin before managing stakeholders.
        self.authenticate_as(1)

        response = self.client.post(
            "/admin/register-stakeholder",
            json={
                "stakeholder_address":
                    "0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65",
                "role": 1
            }
        )

        self.assertEqual(response.status_code, 400)

    # Successful stakeholder revocation
    @patch("backend.app.main.revoke_stakeholder")
    def test_revoke_stakeholder_success(self, mock_revoke):

        mock_revoke.return_value = {
            "status": "success",
            "gas_used": 25925
        }

        # Authenticate as Admin before managing stakeholders.
        self.authenticate_as(1)

        response = self.client.post(
            "/admin/revoke-stakeholder",
            json={
                "stakeholder_address":
                    "0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65"
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "revoked successfully",
            response.json()["message"]
        )


if __name__ == "__main__":
    unittest.main()
