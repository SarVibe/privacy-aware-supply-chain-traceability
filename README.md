# C3-ZKP-Sys

## Project Title
Zero-Knowledge Proof-Based Supply Chain Verification System

## Project Overview
This project implements a blockchain-based supply chain verification system using Zero-Knowledge Proofs (ZKP).

The system enables authorized supply-chain stakeholders to verify product information without revealing the original private supply-chain records.

## Technology Stack

- Frontend: React + Vite
- Backend: Python + FastAPI
- ZKP Circuit: Circom
- Proof System: Groth16
- Proof Library: snarkjs
- Hash Function: Poseidon
- Smart Contract: Solidity
- Blockchain Development: Hardhat
- Wallet: MetaMask

## Project Structure

```text
C3-ZKP-Sys/
├── backend/
│   └── app/
├── frontend/
└── blockchain/
    ├── circuits/
    │   └── build/
    ├── zkp/
    │   └── keys/
    ├── contracts/
    ├── scripts/
    ├── test/
    └── ignition/
```

## Main Objectives

1. Implement ZKP-based supply-chain verification.
2. Support selective attribute verification.
3. Protect confidential supply-chain information.
4. Integrate ZKP verification with blockchain smart contracts.
5. Evaluate verification performance and blockchain gas consumption.

