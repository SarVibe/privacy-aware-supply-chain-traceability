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
backend\venv313\Scripts\python.exe -m experiments.exp2_collision_tuning
backend\venv313\Scripts\python.exe -m experiments.exp3_ldp_privacy_tradeoff
backend\venv313\Scripts\python.exe -m experiments.exp_scalability_benchmarks
```

Each experiment writes its CSV result to `data\tables`.
