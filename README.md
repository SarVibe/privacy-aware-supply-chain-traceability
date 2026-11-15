# Final System

Single project scaffold with three components:

- `frontend/` — React and Vite
- `backend/` — Python 3.13 and FastAPI
- `blockchain/` — Hardhat, Solidity, and Circom circuit workspace

## Initial setup

From this directory, install JavaScript dependencies:

```powershell
npm install
```

Create and install the Python environment:

```powershell
py -3.13 -m venv backend\venv313
backend\venv313\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
```

Run the frontend with `npm run dev:frontend`, or compile the empty Hardhat
workspace with `npm run compile:blockchain`.

The scaffold contains setup and minimal application entry points only; feature
implementation has not been added.
