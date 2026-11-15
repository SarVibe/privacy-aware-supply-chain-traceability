
# Privacy-Aware Supply Chain Traceability

A decentralized, privacy-preserving supply chain traceability system using blockchain technology and Bloom filters.

## Project Components

- **Frontend:** React and Vite
- **Backend:** Python and FastAPI
- **Blockchain:** Hardhat and Solidity
- **Zero-Knowledge Proofs:** Circom

## Research Components

- **C1 – Data Harmonization:** DP Bloom filters and entity resolution.
- **C2 – Dynamic Bloom Filter Updates:** Updating Bloom filters dynamically.
- **C3 – Attribute-Level Selective Disclosure:** Privacy-aware selective disclosure of product attributes.
- **C4 – Privacy-Aware Verification:** Bloom-filter-based privacy-aware verification.

## Project Structure

```text
Final_System/
├── frontend/
├── backend/
├── blockchain/
├── package.json
├── package-lock.json
├── README.md
└── .gitignore
```

## Initial Setup

### 1. Install JavaScript Dependencies

```powershell
npm install
```

### 2. Set Up Python Environment

```powershell
py -3.13 -m venv backend\venv313
backend\venv313\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
```

### 3. Run Frontend

```powershell
npm run dev:frontend
```

### 4. Compile Blockchain

```powershell
npm run compile:blockchain
```

## Project Repository

This repository contains the implementation of the Privacy-Aware Supply Chain Traceability research project.