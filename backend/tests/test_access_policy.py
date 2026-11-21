import unittest

from backend.app.access_policy import (
    get_allowed_attributes,
    check_access
)


class TestAccessPolicy(unittest.TestCase):

    def setUp(self):
        self.all_attributes = {
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
        }

    def test_manufacturer_access(self):
        self.assertEqual(
            get_allowed_attributes("manufacturer"),
            self.all_attributes
        )

    def test_logistics_access(self):
        self.assertEqual(
            len(get_allowed_attributes("logistics")),
            7
        )

    def test_warehouse_access(self):
        self.assertEqual(
            get_allowed_attributes("warehouse"),
            self.all_attributes
        )

    def test_distributor_access(self):
        self.assertEqual(
            len(get_allowed_attributes("distributor")),
            9
        )

    def test_pharmacy_access(self):
        self.assertEqual(
            len(get_allowed_attributes("pharmacy")),
            5
        )

    def test_admin_has_no_attribute_access(self):
        self.assertEqual(
            get_allowed_attributes("admin"),
            set()
        )

    def test_unauthorized_attribute_denied(self):
        allowed, denied = check_access(
            "logistics",
            ["product_id", "product_name"]
        )

        self.assertFalse(allowed)
        self.assertEqual(denied, ["product_name"])


if __name__ == "__main__":
    unittest.main()