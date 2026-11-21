
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from backend.app.zkp_service import generate_proof
from backend.app.blockchain import (
    verify_supply_chain,
    register_stakeholder,
    revoke_stakeholder
)


# Initialize FastAPI application
app = FastAPI(
    title="C3 ZKP Supply Chain Verification System",
    description="Zero-Knowledge Proof Based Supply Chain Verification",
    version="1.0.0"
)


# Define supply-chain verification request
class ZKPRequest(BaseModel):
    actual: dict[str, str]
    expected: dict[str, str]

# Define blockchain verification request
class BlockchainVerificationRequest(BaseModel):
    proof: dict
    public_signals: list[str]
    requested_attributes: list[int]
    stakeholder_private_key: str

# Define stakeholder registration request
class StakeholderRegistrationRequest(BaseModel):
    stakeholder_address: str
    role: int


# Define stakeholder revocation request
class StakeholderRevocationRequest(BaseModel):
    stakeholder_address: str


# Register a stakeholder using Admin account
@app.post("/admin/register-stakeholder")
def admin_register_stakeholder(
    request: StakeholderRegistrationRequest
):
    try:
        if request.role not in [2, 3, 4, 5, 6]:
            raise ValueError("Invalid stakeholder role")

        result = register_stakeholder(
            stakeholder_address=request.stakeholder_address,
            role=request.role
        )

        return {
            "message": "Stakeholder registered successfully",
            "stakeholder_address": request.stakeholder_address,
            "role": request.role,
            "transaction": result
        }

    except (ValueError, TypeError) as error:
        raise HTTPException(status_code=400, detail=str(error))

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Stakeholder registration failed"
        )

# Revoke a stakeholder using Admin account
@app.post("/admin/revoke-stakeholder")
def admin_revoke_stakeholder(
    request: StakeholderRevocationRequest
):
    try:
        result = revoke_stakeholder(
            stakeholder_address=request.stakeholder_address
        )

        return {
            "message": "Stakeholder access revoked successfully",
            "stakeholder_address": request.stakeholder_address,
            "transaction": result
        }

    except (ValueError, TypeError) as error:
        raise HTTPException(status_code=400, detail=str(error))

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Stakeholder revocation failed"
        )

    
# Root endpoint
@app.get("/")
def root():
    return {
        "message": "C3 ZKP Backend is running successfully",
        "system": "System 1 - ZKP",
        "status": "Active"
    }


# Health check endpoint
@app.get("/health")
def health_check():
    return {
        "status": "healthy"
    }


# Generate a zero-knowledge proof
@app.post("/zkp/generate-proof")
def generate_zkp(request: ZKPRequest):
    try:
        data = {
            "actual": request.actual,
            "expected": request.expected
        }

        result = generate_proof(data)

        return {
            "message": "ZKP generated successfully",
            "is_valid": result["is_valid"],
            "public_signals": result["public_signals"],
            "proof": result["proof"]
        }

    except (ValueError, FileNotFoundError, RuntimeError) as error:
        raise HTTPException(
            status_code=400,
            detail=str(error)
        )

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Internal ZKP generation error"
        )

# Verify a zero-knowledge proof on the blockchain
@app.post("/zkp/verify-on-chain")
def verify_zkp_on_chain(request: BlockchainVerificationRequest):
    try:
        result = verify_supply_chain(
            proof=request.proof,
            public_signals=request.public_signals,
            requested_attributes=request.requested_attributes,
            stakeholder_private_key=request.stakeholder_private_key
        )

        return {
            "message": "Blockchain verification successful",
            "transaction": result
        }

    except (ValueError, PermissionError) as error:
        raise HTTPException(
            status_code=400,
            detail=str(error)
        )

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Blockchain verification failed"
        )