"""Compare streaming representatives with connected components at serving tau."""

import hashlib

import pandas as pd
from sklearn.metrics import adjusted_rand_score

from experiments.rq1.diagnostic_inputs import GOLDEN_ROOT, OUTPUT_ROOT, diagnostic_cases
from src.common.config import SERVING_TAU, load_config
from src.common.encoding.versioned_bloom import CompositeBloomEncoder
from src.common.evaluation.metrics import evaluate_clusters
from src.common.experiment.io import read_csv, write_csv
from src.common.linking.bloom import BloomLinker
from src.rq1.entity_resolver import EntityResolver


def main():
    cfg = load_config("rq1")
    rid, eid = cfg.columns.record_id, cfg.columns.entity_id
    encoder = CompositeBloomEncoder(cfg.bloom, bytes.fromhex(cfg.bloom.hmac_key))
    linker = BloomLinker("bloom", "composite", SERVING_TAU, cfg)
    rows, after = [], []
    for case in diagnostic_cases(cfg):
        observed = case.observed
        resolver = EntityResolver(SERVING_TAU, namespace=encoder.namespace)
        streamed = []
        baseline = case.dataset == "golden_200" and case.noise == 0
        for record_id, *fields in observed[[rid, *cfg.columns.text]].itertuples(index=False, name=None):
            vector = encoder.encode_record(*fields)
            cluster, score, new = resolver.resolve_record(record_id, vector)
            streamed.append(cluster)
            if baseline:
                after.append({
                    "record_id": record_id, "packed_vector_sha256": hashlib.sha256(vector.packed_bytes()).hexdigest(),
                    "cluster_id": cluster, "score": score, "is_new_cluster": new,
                })
        truth = observed.set_index(rid)[eid]
        streaming = pd.Series(streamed, index=truth.index)
        connected = linker.link(observed.drop(columns=eid))
        agreement = adjusted_rand_score(streaming, connected)
        for method, labels in (("streaming_representative", streaming), ("connected_components", connected)):
            rows.append({
                "dataset": case.dataset, "seed": case.seed, "noise": case.noise, "tau": SERVING_TAU,
                "method": method, "adjusted_rand_agreement": agreement,
                **evaluate_clusters(truth, labels),
            })
    path = OUTPUT_ROOT / "serving_agreement"
    write_csv(pd.DataFrame(rows), path / "clustering_agreement.csv")
    old = read_csv(GOLDEN_ROOT / "serving_before" / "records.csv")
    new = pd.DataFrame(after)
    comparison = old.merge(new, on="record_id", suffixes=("_before", "_after"), validate="one_to_one")
    write_csv(comparison, path / "serving_before_after.csv")
    print(f"Saved {len(rows)} comparisons to {path}")


if __name__ == "__main__":
    main()
