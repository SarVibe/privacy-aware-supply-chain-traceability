# RQ1 cleanup plan

Dry run for commit `bfb1b95432910c3933f6c6a94bac0116eea4c461` on `sarvi-component1`. The checkout was clean before creating the two requested documentation files. The `rq1-final` tag was absent at the start of the dry run. Create that tag against this commit before execution. The tag identifies the Git commit. The separate SHA-256 inventory covers the result artifacts and data, some of which are Git-ignored. [Protected baseline](cleanup_hashes_before.txt)

**No files moved or deleted.** `DELETE` means an exact path proposed for quarantine after approval. `ASK` means keep in place pending an explicit decision for that row. `KEEP` marks protected or out-of-scope paths. Paths are relative to the repository root. For protected trees with separately listed children, the parent size excludes those children. Sizes count regular file bytes. The inventory does not measure filesystem allocation.

## Proposed for quarantine

| Path                                  |              Size | Category          | Action     | Reason                                                                                                |
| ------------------------------------- | ----------------: | ----------------- | ---------- | ----------------------------------------------------------------------------------------------------- |
| `backend/app/__pycache__`             | 4,664 B (2 files) | Scratch/temporary | **DELETE** | Untracked Python bytecode. Matching source files exist. No exact path or cache-file references found. |
| `backend/app/experiments/__pycache__` |   311 B (2 files) | Scratch/temporary | **DELETE** | Untracked Python bytecode. Matching source files exist. No exact path or cache-file references found. |

The two proposed directories contain four files totaling **4,975 bytes** (about **4.86 KiB**). Quarantine would remove that payload from its current paths. The disk-space saving remains zero until the owner deletes the quarantine. No ASK bytes are included in this estimate.

Reference check for each proposed path used `rg -n -F` for the qualified directory paths, slash variants, and the contained bytecode names across first-party code, docs, tests and configs. It returned no matches. `git ls-files` returned no tracked files under either path. The generic bytecode ignore patterns in `.gitignore:7?8` apply to the file type. They do not name either specific path.

## Keep pending a decision

| Path                                      |                     Size | Category          | Action  | Reason                                                                                                                                                           |
| ----------------------------------------- | -----------------------: | ----------------- | ------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `.pytest_cache`                           |  Unknown (access denied) | Scratch/temporary | **ASK** | Windows denied enumeration. The ignore rule names this cache. Keep until its contents can be inspected.                                                          |
| `backend/app/results/rq1_repro`           | 13,513,850 B (412 files) | Scratch/temporary | **ASK** | Contains verification artifacts explicitly cited in RQ1_COMMANDS.md:133,170,427.                                                                                 |
| `backend/app/results/rq1/smoke`           |     238,662 B (21 files) | Scratch/temporary | **ASK** | Referenced in ARCHITECTURE.md:399,414 and RQ1_COMMANDS.md:136. The runner and tests also name the path.                                                          |
| `backend/app/results/rq1_audit/rerun`     |   4,728,024 B (13 files) | Scratch/temporary | **ASK** | The exact scratch replay location is cited in RQ1_AUDIT.md:41 and created by replay_seed0.py.                                                                    |
| `backend/app/experiments/rq2/__pycache__` |     134,242 B (11 files) | Scratch/temporary | **ASK** | Some bytecode has no corresponding source in this directory, including analyze.py, profile_data.py, run_dp_ablation.py and run_grid.py. Keep pending RQ2 review. |

## Protected and out of scope

| Path                                                                    |                    Size | Category  | Action   | Reason                                                                                              |
| ----------------------------------------------------------------------- | ----------------------: | --------- | -------- | --------------------------------------------------------------------------------------------------- |
| `backend/app/results/rq1`                                               |    523,686 B (21 files) | Protected | **KEEP** | Frozen primary outputs. Smoke is assessed separately.                                               |
| `backend/app/results/rq1_posthoc`                                       |  1,462,077 B (38 files) | Protected | **KEEP** | Frozen post-hoc outputs, including the alternate splits.                                            |
| `backend/app/results/rq1_audit`                                         |    146,362 B (24 files) | Protected | **KEEP** | Audit scripts, logs, CSVs and recorded hashes. Cache and replay directories are listed separately.  |
| `backend/app/data/raw`                                                  |   3,831,321 B (1 files) | Protected | **KEEP** | Original RQ1 input data.                                                                            |
| `backend/app/data/generated/prepared`                                   |     185,591 B (2 files) | Protected | **KEEP** | Prepared table and entity map.                                                                      |
| `backend/app/data/generated/splits`                                     |     21,330 B (10 files) | Protected | **KEEP** | Frozen entity-level split files.                                                                    |
| `backend/app/data/generated/noisy`                                      |  6,781,251 B (60 files) | Protected | **KEEP** | Frozen noisy inputs and edit logs.                                                                  |
| `backend/app/configs`                                                   |       1,114 B (2 files) | Protected | **KEEP** | Experiment settings, paths and research key configuration.                                          |
| `backend/app/src`                                                       |    233,765 B (52 files) | Protected | **KEEP** | Application and shared research code. Includes bytecode inside this protected tree.                 |
| `backend/app/experiments/rq1`                                           |    214,409 B (14 files) | Protected | **KEEP** | Current RQ1 entry points. The **pycache** here stays under the protected directory.                 |
| `backend/app/tests`                                                     |    261,044 B (47 files) | Protected | **KEEP** | Test suite. Includes bytecode inside this protected tree.                                           |
| `backend/requirements.txt`                                              |         277 B (1 files) | Protected | **KEEP** | Dependency specification.                                                                           |
| `backend/app/results/rq2`                                               |           0 B (0 files) | Protected | **KEEP** | Other experiment outputs outside the RQ1 cleanup.                                                   |
| `backend/app/results/rq1_audit/mplconfig`                               |     223,175 B (1 files) | Protected | **KEEP** | Temporary contents inside the protected audit tree. Only rerun/ is eligible for consideration here. |
| `backend/app/results/rq1_audit/pytest-aa5e071202534885bfd1a6ca19d93642` | 1,284,139 B (171 files) | Protected | **KEEP** | Temporary contents inside the protected audit tree. Only rerun/ is eligible for consideration here. |
| `docs/ARCHITECTURE.md`                                                  |      61,284 B (1 files) | Protected | **KEEP** | Study design, evidence, documentation or reproducibility instructions.                              |
| `docs/RQ1_AUDIT.md`                                                     |      65,153 B (1 files) | Protected | **KEEP** | Study design, evidence, documentation or reproducibility instructions.                              |
| `docs/RQ1_COMMANDS.md`                                                  |      30,899 B (1 files) | Protected | **KEEP** | Study design, evidence, documentation or reproducibility instructions.                              |
| `docs/RQ1_CONTEXT.md`                                                   |       8,666 B (1 files) | Protected | **KEEP** | Study design, evidence, documentation or reproducibility instructions.                              |
| `docs/RQ1_RESULTS.md`                                                   |      27,046 B (1 files) | Protected | **KEEP** | Study design, evidence, documentation or reproducibility instructions.                              |
| `docs/cleanup_hashes_before.txt`                                        |      16,594 B (1 files) | Protected | **KEEP** | The 131-file protected baseline for post-move verification.                                         |
| `docs/RQ1_CLEANUP_PLAN.md`                                              |                    Self | Protected | **KEEP** | This dry-run plan.                                                                                  |
| `.venv`                                                                 |                Excluded | Protected | **KEEP** | Virtual environment. Contents were excluded from the cleanup inventory.                             |
| `backend/venv313`                                                       |                Excluded | Protected | **KEEP** | Active Python environment.                                                                          |
| `backend/venv313_old`                                                   |                Excluded | Protected | **KEEP** | Old Python environment. The same no-touch rule applies.                                             |
| `.git`                                                                  |                Excluded | Protected | **KEEP** | Git internals are outside cleanup scope.                                                            |
| `.qodo, .vscode, .env, .env.example`                                    |            Not measured | Protected | **KEEP** | Local tooling and configuration. No cleanup proposed.                                               |
| `frontend, blockchain`                                                  |                Excluded | Protected | **KEEP** | Separate project trees. No RQ1 cleanup proposed.                                                    |

The scan covered the repository root and the backend tree, including hidden cache names. No further in-scope stray logs, temporary-file suffixes or editor/OS junk were found outside the subtrees already classified as protected, legacy or scratch. The root pytest cache could not be enumerated. Virtual environments, Git internals, and separate frontend and blockchain trees were excluded from cleanup.

## Decide in Phase 8

| Path                                                     |                   Size | Category | Action   | Reason                                                                                   |
| -------------------------------------------------------- | ---------------------: | -------- | -------- | ---------------------------------------------------------------------------------------- |
| `backend/app/results/rq1_legacy`                         | 3,232,970 B (27 files) | Legacy   | **KEEP** | Archived RQ1 artifacts and archive manifest.                                             |
| `backend/app/src/rq1`                                    |   132,306 B (18 files) | Legacy   | **KEEP** | Legacy RQ1 modules and their local caches.                                               |
| `backend/app/src/rq2`                                    |   269,829 B (49 files) | Legacy   | **KEEP** | Existing RQ2 implementation and its local caches.                                        |
| `backend/app/experiments/rq1/grid_runner.py`             |     42,517 B (1 files) | Legacy   | **KEEP** | Legacy RQ1 benchmark entry point.                                                        |
| `backend/app/experiments/rq1/noise_dataset_generator.py` |      5,746 B (1 files) | Legacy   | **KEEP** | Legacy noise generator. Existing RQ2 fixtures rely on the legacy data layout.            |
| `backend/app/data/generated (63 top-level CSVs)`         | 3,895,308 B (63 files) | Legacy   | **KEEP** | Three catalog/pair exports and 60 seeded noise fixtures. Review dependencies in Phase 8. |

## After explicit approval

- Recheck Git status. The two files produced by this dry run are expected until committed. Stop if unrelated changes have appeared or if HEAD changed without a fresh review of the approved list and baseline.
- Use only the approved exact paths. Resolve and check each source and destination against the repository root and protected paths before moving. Quarantine under `_to_delete/` with the original relative layout so rollback can restore each original path. Add the root quarantine to `.gitignore` at execution time.
- Recompute and diff all 131 protected hashes. Run the full test suite with a fresh basetemp in the quarantine, requiring 233 passes. Validate the frozen RQ1 files and require 14 PASS, 1 WARN and 0 FAIL. Check local file links in RQ1_RESULTS.md, ARCHITECTURE.md and RQ1_AUDIT.md and report any breakage.
- If verification fails, restore the moved files and report the failure. The owner handles permanent deletion after verification.
