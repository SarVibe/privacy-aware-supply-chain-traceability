# Final System

Single project scaffold with three components:

- `frontend/` — React and Vite
- `backend/` — Python 3.13 and FastAPI
- `blockchain/` — Hardhat, Solidity, and Circom circuit workspace

## Initial setup

Create and install the Python environment:

```powershell
py -3.13 -m venv backend\venv313
backend\venv313\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
```

Install JavaScript dependencies for each workspace:

```powershell
npm install --prefix blockchain
npm install --prefix frontend
```

The backend and blockchain use the project-root `.env`. Do not commit
`BLOCKCHAIN_PRIVATE_KEY`; provide it through a local ignored environment file
when deploying or submitting live transactions. Mock-ledger behavior is
disabled by default and can be enabled explicitly with
`ALLOW_MOCK_LEDGER=true` for local tests only.

Start a local Hardhat node, then compile and deploy:

```powershell
npx --prefix blockchain hardhat node
npm --prefix blockchain run compile
node blockchain/scripts/deploy.js
```

Run the available blockchain test command with:

```powershell
npm --prefix blockchain test
```

Run the Python unit and integration tests with:

```powershell
python -m pytest
```

## Phase 4 application

Start the FastAPI backend from the project root:

```powershell
$env:PYTHONPATH = "backend\app"
backend\venv313\Scripts\python.exe -m uvicorn main:app --app-dir backend\app --reload
```

The API exposes `GET /health`, `POST /api/v1/harmonize`, and
`GET /api/v1/ledger/summary`. Blockchain commits remain disabled by default;
set `API_ENABLE_BLOCKCHAIN_COMMIT=true` only when the deployed contract and
live transaction configuration are ready.

In a second terminal, start the Vite frontend:

```powershell
npm run dev --prefix frontend
```

The frontend proxies API requests to `http://127.0.0.1:8000`. Build it for
production with:

```powershell
npm --prefix frontend run build
```

Run the RQ2 collision experiment from the repository root with `RQ2_HMAC_ROOT_KEY` set in the environment.

```powershell
$env:PYTHONPATH = "backend\app"
backend\venv313\Scripts\python.exe -m experiments.rq2.collision_runner
```

The collision runner writes its tables, figures, summary and RQ3 recommendation to `backend/app/results/rq2`. The default benchmark evaluates 12 configurations on five paired seeds. See [RQ2 commands and protocol](docs/RQ2_COLLISION.md) for the key format, regression gate, and optional robustness inputs.

### Legacy RQ2 metric dictionary

| Metric | Unit | Range | Definition |
|---|---|---:|---|
| `f1_unc` | score | [0, 1] | Test F1 at the validation-split best-F1 tau, without an FPR constraint |
| `f1_01`, `f1_05` | score | [0, 1] | Test F1 at the best validation tau constrained to FPR <= 0.01 or 0.05 |
| `anonymity_set` | count | [1, dictionary size] | Median number of dictionary entries tied with or above the true entry |
| `mean_rank` | rank | [1, dictionary size] | Mean tie-averaged rank of the true dictionary entry |
| `mrr` | score | (0, 1] | Mean reciprocal tie-averaged rank |
| `reid_cands_delta`, `reid_ties` | count | >= 1 | Mean near-candidate or exact-tie counts; the normalized `*_frac` columns are separate |

Absolute score differences are reported in percentage points (`pp`); relative
changes are labeled `% relative`. Positive paired differences always mean
`tuned - standard`.

## Threat Model

The empirical privacy evaluation uses three attack classes. See [`docs/threat_model.md`](docs/threat_model.md) for the full threat model specification.

| Attack | Attacker type | Knowledge | PRIMARY? |
|--------|--------------|-----------|----------|
| **A1** – Dictionary re-identification | Insider (consortium member) | HMAC key known | **YES** (shared-key architecture) |
| **A2** – Frequency alignment | External observer | Key secret | No – meaningful only at noise=0 |
| **A3** – Bit/q-gram frequency | External observer | Key secret | No – simplified attack, lower bound |

> **Key management in C1: SHARED KEY** — all organizations hold the HMAC key to encode their own records; therefore A1 represents a realistic insider threat from any consortium participant.

> **Limitations**: Empirical privacy against tested attacks only; not a formal guarantee. A3 is a simplified attack, not a reimplementation of published cryptanalysis.

### RQ1 reproducible benchmark

Generate the single-source seeded inputs before running RQ1:

```powershell
$env:PYTHONPATH = "backend\app"
.\backend\venv313\Scripts\python.exe -m experiments.rq1.noise_generator --seeds 42 43 44 45 46 47 48 49 50 51
.\backend\venv313\Scripts\python.exe -m experiments.rq1.noise_generator --seeds 42 43 44 45 46 47 48 49 50 51 --all-fields
.\backend\venv313\Scripts\python.exe -m experiments.rq1.run_grid --noise-source files
```

RQ1 tunes the headline threshold on seeds 42-46 and reports final results on
seeds 47-51. The all-fields robustness run uses the separate generated
directory and a suffixed output set:

```powershell
.\backend\venv313\Scripts\python.exe -m experiments.rq1.run_grid `
  --noise-source files --data-dir backend\app\data\generated\all_fields `
  --output-suffix _all_fields
```

Pairwise precision is defined as `TP / (TP + FP)`; therefore precision is
reported as 0 when no predicted pairs exist, including exact matching at high
noise. Description-only BF can produce false positives at zero noise because
117 duplicate-description groups represent only 96 entity groups. The dataset
contains 481 records from 149 entities and one source; seed changes affect
noise, not the underlying sample.
