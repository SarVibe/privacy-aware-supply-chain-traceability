import numpy as np

from src.common.linking.clustering import labels_from_pairs


def test_components_include_transitive_chains_and_singletons():
    i, j = np.array([0, 1, 3]), np.array([1, 2, 4])
    scores = np.array([0.85, 0.92, 0.95])
    labels = labels_from_pairs(6, i, j, scores, 0.85)
    assert labels[0] == labels[1] == labels[2]
    assert labels[3] == labels[4]
    assert len({labels[0], labels[3], labels[5]}) == 3
    np.testing.assert_array_equal(np.unique(labels), np.arange(3))


def test_threshold_filters_edges():
    i, j = np.array([0, 1, 2]), np.array([1, 2, 3])
    scores = np.array([0.85, 0.79, 0.80])
    labels = labels_from_pairs(4, i, j, scores, 0.80)
    assert labels[0] == labels[1] != labels[2] == labels[3]
    np.testing.assert_array_equal(np.unique(labels), np.arange(2))


def test_empty_graph_and_graph_without_edges():
    indices, scores = np.array([], dtype=int), np.array([], dtype=float)
    np.testing.assert_array_equal(labels_from_pairs(0, indices, indices, scores, 0.9), np.empty(0, dtype=int))
    np.testing.assert_array_equal(labels_from_pairs(3, indices, indices, scores, 0.9), np.arange(3))
