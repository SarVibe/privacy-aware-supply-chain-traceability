from bitarray import bitarray

from src.rq1.entity_resolver import EntityResolver


def test_matching_filter_is_added_to_existing_cluster():
    resolver = EntityResolver(threshold=0.9)
    filter_value = bitarray("11001100")

    first_cluster, first_score, first_is_new = resolver.resolve_record(
        "R1", filter_value
    )
    second_cluster, second_score, second_is_new = resolver.resolve_record(
        "R2", filter_value.copy()
    )

    assert first_cluster == "CANONICAL_CLUSTER_0001"
    assert first_score == 0.0
    assert first_is_new is True
    assert second_cluster == first_cluster
    assert second_score == 1.0
    assert second_is_new is False
    assert resolver.clusters[first_cluster].record_count == 2


def test_low_similarity_filter_creates_a_new_cluster():
    resolver = EntityResolver(threshold=0.9)

    resolver.resolve_record("R1", bitarray("11001100"))
    cluster_id, score, is_new = resolver.resolve_record(
        "R2", bitarray("00110011")
    )

    assert cluster_id == "CANONICAL_CLUSTER_0002"
    assert score == 0.0
    assert is_new is True