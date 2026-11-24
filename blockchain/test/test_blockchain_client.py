import pytest
import numpy as np
from src.common.encoding.versioned_bloom import BloomNamespace, VersionedBloom

from src.rq2.blockchain_client import BlockchainClient


NAMESPACE = BloomNamespace("fixture-encoder", "fixture-key")

def test_hash_conversion_requires_exact_hex_bytes():
    client = BlockchainClient.__new__(BlockchainClient)

    assert client._to_bytes32("11" * 32) == bytes.fromhex("11" * 32)

    with pytest.raises(ValueError):
        client._to_bytes32("11")
    with pytest.raises(ValueError):
        client._to_bytes32("zz" * 32)


def test_mock_commit_requires_explicit_opt_in(monkeypatch):
    monkeypatch.setattr(BlockchainClient, "_initialize_connection", lambda self: None)
    client = BlockchainClient(
        contract_address="0x0000000000000000000000000000000000000001",
        bf_length=8, namespace=NAMESPACE,
        allow_mock_ledger=False,
    )
    client.is_live = False

    result = client.commit_harmonized_record(
        "R1",
        "C1",
        VersionedBloom(np.array([1, 0] * 4, dtype=np.uint8), NAMESPACE),
        "11" * 32,
    )

    assert result["status"] == "BLOCKCHAIN_UNAVAILABLE"


def test_mock_commit_tracks_new_cluster_gas(monkeypatch):
    monkeypatch.setattr(BlockchainClient, "_initialize_connection", lambda self: None)
    client = BlockchainClient(
        contract_address="0x0000000000000000000000000000000000000001",
        bf_length=8, namespace=NAMESPACE,
        allow_mock_ledger=True,
    )
    client.is_live = False
    filter_value = VersionedBloom(np.array([1, 0] * 4, dtype=np.uint8), NAMESPACE)

    first = client.commit_harmonized_record("R1", "C1", filter_value, "11" * 32)
    second = client.commit_harmonized_record("R2", "C1", filter_value, "22" * 32)
    third = client.commit_harmonized_record("R3", "C2", filter_value, "33" * 32)

    assert first["gas_used"] == 501138
    assert second["gas_used"] == 92450
    assert third["gas_used"] == 501138