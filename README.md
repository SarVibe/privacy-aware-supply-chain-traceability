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

Run the research experiments from `backend\app`:

```powershell
$env:PYTHONPATH = "backend\app"
backend\venv313\Scripts\python.exe -m experiments.rq2.analyze
backend\venv313\Scripts\python.exe -m experiments.rq2.run_dp_ablation
backend\venv313\Scripts\python.exe -m experiments.rq2.profile_data
```

Each experiment writes its CSV result to `data\tables`.

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
