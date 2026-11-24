from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from src.common.data.loader import load_noisy
from src.common.encoding.bloom_filter import BloomFilterEncoder
from src.common.encoding.versioned_bloom import IncompatibleBloomError, VersionedBloom
from src.common.preprocessing.field_builder import build_field_strings
from src.rq2.blockchain_client import BlockchainClient
from src.rq2.harmonization_pipeline import HarmonizationPipeline

FIXTURE_KEY = "public test key for serving parity"


@pytest.mark.parametrize("length, hashes", [(1024, 4), (512, 10), (256, 30)])
def test_serving_pipeline_encodes_the_same_200_records(golden_config, monkeypatch, length, hashes):
    monkeypatch.setenv("SHARED_SECRET_KEY", FIXTURE_KEY)
    pipeline = HarmonizationPipeline(length=length, num_hashes=hashes, enable_blockchain_commit=False)
    cfg = golden_config
    frame = load_noisy(cfg.seeds[0], 0, cfg)
    assert len(frame) == 200
    strings = build_field_strings(frame, "composite", cfg, normalize=True)
    encoder = BloomFilterEncoder(length, hashes, cfg.bloom.q, FIXTURE_KEY.encode(), cfg.bloom.pad_char)
    vectors = []
    resolve = pipeline.resolver.resolve_record

    def capture(*args, **kwargs):
        vectors.append(kwargs["bf"].bits)
        return resolve(*args, **kwargs)

    monkeypatch.setattr(pipeline.resolver, "resolve_record", capture)
    results = pipeline.process_batch(frame)
    assert results.encoder_version.unique().tolist() == [pipeline.encoder_version]
    assert results.record_id.tolist() == strings.index.tolist()
    np.testing.assert_array_equal(np.stack(vectors), encoder.encode_many(strings))
    assert f"-l{length}-k{hashes}" in pipeline.encoder_version
    assert pipeline.q == 2 and pipeline.threshold == 0.80


def test_missing_key_fails_before_connection(monkeypatch):
    monkeypatch.delenv("SHARED_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SHARED_SECRET_KEY is required"):
        HarmonizationPipeline(enable_blockchain_commit=False)


def test_version_and_key_must_match_before_comparison(monkeypatch):
    monkeypatch.setenv("SHARED_SECRET_KEY", FIXTURE_KEY)
    pipeline = HarmonizationPipeline(enable_blockchain_commit=False)
    vector = pipeline.bf_engine.encode_record("aaa")
    pipeline.resolver.resolve_record("first", vector)
    for namespace in (replace(vector.namespace, encoder_version="other"), replace(vector.namespace, key_id="other")):
        with pytest.raises(IncompatibleBloomError, match="namespace mismatch"):
            pipeline.resolver.resolve_record("second", VersionedBloom(vector.bits, namespace))


def test_contract_round_trip_rejects_untagged_candidates_even_with_mock_fallback(monkeypatch):
    monkeypatch.setenv("SHARED_SECRET_KEY", FIXTURE_KEY)
    pipeline = HarmonizationPipeline(enable_blockchain_commit=False)
    vector = pipeline.bf_engine.encode_record("aaa", "20mg", "tablet", "10")
    client = BlockchainClient(namespace=vector.namespace, bf_length=1024, allow_mock_ledger=True, connect=False)
    namespace = vector.namespace
    assert len(vector.packed_bytes()) == 128
    assert client.commit_harmonized_record("record", "C1", vector, "11" * 32)["encoder_version"] == pipeline.encoder_version
    assert client.get_record(0)["encoder_version"] == pipeline.encoder_version
    client.is_live = True
    leaders = [namespace.qualify("C1")]
    client.contract = SimpleNamespace(functions=SimpleNamespace(
        getClusterLeaders=lambda: SimpleNamespace(call=lambda: (leaders, [vector.packed_bytes()])),
    ))
    restored = client.retrieve_stored_candidates()["C1"]
    np.testing.assert_array_equal(restored.bits, vector.bits)
    assert restored.namespace == namespace
    for incompatible_id in ("C1", replace(namespace, encoder_version="other").qualify("C1")):
        leaders[0] = incompatible_id
        with pytest.raises(IncompatibleBloomError, match="Unversioned or incompatible"):
            client.retrieve_stored_candidates()


def test_commit_uses_the_existing_contract_arguments_and_records_the_namespace(monkeypatch):
    monkeypatch.setenv("SHARED_SECRET_KEY", FIXTURE_KEY)
    pipeline = HarmonizationPipeline(enable_blockchain_commit=False)
    vector = pipeline.bf_engine.encode_record("aaa", "20mg", "tablet", "10")
    client = pipeline.blockchain
    client.is_live = True
    client.account = SimpleNamespace(address="fixture")
    sent = []

    def store(*args):
        sent.append(args)
        return SimpleNamespace(estimate_gas=lambda _: 100, build_transaction=lambda values: values)

    client.contract = SimpleNamespace(functions=SimpleNamespace(storeHarmonizedRecord=store))
    client.w3 = SimpleNamespace(eth=SimpleNamespace(
        get_transaction_count=lambda *_: 1,
        account=SimpleNamespace(sign_transaction=lambda *_args, **_kw: SimpleNamespace(raw_transaction=b"signed")),
        send_raw_transaction=lambda _: b"hash",
        wait_for_transaction_receipt=lambda *_args, **_kw: SimpleNamespace(status=1, gasUsed=100, blockNumber=2),
    ))
    monkeypatch.setattr(client, "_get_fee_fields", lambda: {"gasPrice": 1})
    receipt = client.commit_harmonized_record("record", "C1", vector, "22" * 32)
    assert receipt["status"] == "SUCCESS"
    assert sent == [("record", vector.namespace.qualify("C1"), vector.packed_bytes(), bytes.fromhex("22" * 32))]
