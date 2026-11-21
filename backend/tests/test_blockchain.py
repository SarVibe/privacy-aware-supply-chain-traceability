
import unittest
from unittest.mock import patch

from backend.app import blockchain


class TestBlockchainVerification(unittest.TestCase):

    def setUp(self):
        self.valid_proof = {
            "pi_a": ["1", "2"],
            "pi_b": [["3", "4"], ["5", "6"]],
            "pi_c": ["7", "8"]
        }

        self.valid_signals = ["1"] + ["0"] * 10

        self.valid_attributes = [0, 2, 4]


    @patch("backend.app.blockchain.contract")
    @patch("backend.app.blockchain.send_transaction")
    @patch("backend.app.blockchain.can_access_attribute")
    @patch("backend.app.blockchain.get_stakeholder_role")
    def test_valid_verification(
        self,
        mock_role,
        mock_access,
        mock_transaction,
        mock_contract
    ):
        mock_role.return_value = 3
        mock_access.return_value = True

        mock_transaction.return_value = {
            "status": "success",
            "gas_used": 300000
        }

        mock_contract.functions.verifySupplyChain.return_value.call.return_value = True

        result = blockchain.verify_supply_chain(
            self.valid_proof,
            self.valid_signals,
            self.valid_attributes,
            "0x" + "11" * 32
        )

        self.assertEqual(result["status"], "success")
        mock_transaction.assert_called_once()

    @patch("backend.app.blockchain.get_stakeholder_role")
    def test_unauthorized_stakeholder(self, mock_role):
        mock_role.return_value = 0

        with self.assertRaises(PermissionError):
            blockchain.verify_supply_chain(
                self.valid_proof,
                self.valid_signals,
                self.valid_attributes,
                "0x" + "11" * 32
            )

    @patch("backend.app.blockchain.get_stakeholder_role")
    def test_admin_cannot_verify(self, mock_role):
        mock_role.return_value = 1

        with self.assertRaises(PermissionError):
            blockchain.verify_supply_chain(
                self.valid_proof,
                self.valid_signals,
                self.valid_attributes,
                "0x" + "11" * 32
            )

    @patch("backend.app.blockchain.get_stakeholder_role")
    def test_empty_requested_attributes(self, mock_role):
        mock_role.return_value = 3

        with self.assertRaises(ValueError):
            blockchain.verify_supply_chain(
                self.valid_proof,
                self.valid_signals,
                [],
                "0x" + "11" * 32
            )

    @patch("backend.app.blockchain.get_stakeholder_role")
    def test_duplicate_requested_attributes(self, mock_role):
        mock_role.return_value = 3

        with self.assertRaises(ValueError):
            blockchain.verify_supply_chain(
                self.valid_proof,
                self.valid_signals,
                [0, 0],
                "0x" + "11" * 32
            )

    @patch("backend.app.blockchain.can_access_attribute")
    @patch("backend.app.blockchain.get_stakeholder_role")
    def test_unauthorized_attribute(
        self,
        mock_role,
        mock_access
    ):
        mock_role.return_value = 3
        mock_access.return_value = False

        with self.assertRaises(PermissionError):
            blockchain.verify_supply_chain(
                self.valid_proof,
                self.valid_signals,
                [1],
                "0x" + "11" * 32
            )

    @patch("backend.app.blockchain.can_access_attribute")
    @patch("backend.app.blockchain.get_stakeholder_role")
    def test_invalid_public_signal_count(self, mock_role, mock_access):
        mock_role.return_value = 3
        mock_access.return_value = True

        with self.assertRaises(ValueError):
            blockchain.verify_supply_chain(
                self.valid_proof,
                ["1", "0"],
                self.valid_attributes,
                "0x" + "11" * 32
            )
                
    @patch("backend.app.blockchain.can_access_attribute")
    @patch("backend.app.blockchain.get_stakeholder_role")
    def test_invalid_proof_result(self, mock_role, mock_access):
        mock_role.return_value = 3
        mock_access.return_value = True

        invalid_signals = ["0"] + ["0"] * 10

        with self.assertRaises(ValueError):
            blockchain.verify_supply_chain(
                self.valid_proof,
                invalid_signals,
                self.valid_attributes,
                "0x" + "11" * 32
            )
            
if __name__ == "__main__":
    unittest.main()
