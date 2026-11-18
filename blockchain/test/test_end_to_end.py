from src.rq2.harmonization_pipeline import HarmonizationPipeline


def test_off_chain_pipeline_harmonizes_matching_records():
    pipeline = HarmonizationPipeline(
        length=128,
        num_hashes=3,
        threshold=0.9,
        enable_blockchain_commit=False,
    )

    first = pipeline.process_single_record(
        "R1",
        "Didanosine 200mg tablets",
        stakeholder_org="OrgA",
    )
    second = pipeline.process_single_record(
        "R2",
        "Didanosine 200mg tablets",
        stakeholder_org="OrgB",
    )

    assert first["predicted_cluster_id"] == "CANONICAL_CLUSTER_0001"
    assert second["predicted_cluster_id"] == first["predicted_cluster_id"]
    assert second["is_new_cluster"] is False
    assert second["onchain_status"] == "NOT_COMMITTED"


def test_pipeline_rejects_empty_input():
    pipeline = HarmonizationPipeline(enable_blockchain_commit=False)

    try:
        pipeline.process_single_record("R1", "")
    except ValueError as exc:
        assert "raw_description" in str(exc)
    else:
        raise AssertionError("Expected empty descriptions to be rejected")