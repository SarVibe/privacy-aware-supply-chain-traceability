
# Define which attributes each stakeholder can access
ACCESS_POLICY = {
    "manufacturer": {
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
    },

    "logistics": {
        "product_id",
        "batch_number",
        "expiry_date",
        "shipment_id",
        "quantity",
        "source_location",
        "destination_location",
    },

    "warehouse": {
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
    },

    "distributor": {
        "product_id",
        "product_name",
        "batch_number",
        "manufacturing_date",
        "expiry_date",
        "manufacturer_id",
        "shipment_id",
        "source_location",
        "destination_location",
    },

    "pharmacy": {
        "product_id",
        "product_name",
        "batch_number",
        "manufacturing_date",
        "expiry_date",
    },
}


# Return the allowed attributes for a stakeholder
def get_allowed_attributes(stakeholder: str) -> set[str]:
    role = stakeholder.strip().lower().replace(" ", "")

    # Convert stakeholder names into policy role names
    role_aliases = {
        "logisticsprovider": "logistics",
        "logistics": "logistics",
    }

    role = role_aliases.get(role, role)

    return ACCESS_POLICY.get(role, set())


# Check whether the requested attributes are permitted
def check_access(
    stakeholder: str,
    requested_attributes: list[str],
) -> tuple[bool, list[str]]:

    allowed = get_allowed_attributes(stakeholder)

    # Identify attributes that the stakeholder cannot access
    denied = [
        attribute
        for attribute in requested_attributes
        if attribute not in allowed
    ]

    return len(denied) == 0, denied
