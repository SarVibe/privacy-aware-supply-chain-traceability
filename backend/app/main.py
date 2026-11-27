
import os

from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.app.zkp_service import generate_proof
from backend.app.blockchain import (
    register_stakeholder,
    revoke_stakeholder,
    get_stakeholder_role,
    get_record_by_transaction_hash,
    get_verification_history,
    get_manufacturer_storage_history,
    get_manufacturer_verification_history,
)
from backend.app.access_policy import get_allowed_attributes
from backend.app.auth import (
    generate_login_challenge,
    verify_wallet_signature,
    create_access_token,
    get_current_user,
)


app = FastAPI(
    title="C3 ZKP Supply Chain Verification System",
    description="Selective Zero-Knowledge Proof Based Supply Chain Verification",
    version="1.0.0"
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

frontend_origins = [
    origin.strip()
    for origin in os.getenv("FRONTEND_ORIGINS", "").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=frontend_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class StakeholderRegistrationRequest(BaseModel):
    stakeholder_address: str
    role: int


class StakeholderRevocationRequest(BaseModel):
    stakeholder_address: str


class NonceRequest(BaseModel):
    wallet_address: str


class WalletVerificationRequest(BaseModel):
    wallet_address: str
    signature: str


class ZKPRequest(BaseModel):
    transaction_hash: str
    values: dict[str, str]
    salts: dict[str, str]


ROLE_NAMES = {
    1: "Admin",
    2: "Manufacturer",
    3: "Logistics Provider",
    4: "Warehouse",
    5: "Distributor",
    6: "Pharmacy",
}


def require_operational_stakeholder(current_user: dict) -> int:
    role = current_user["role"]

    if role not in [2, 3, 4, 5, 6]:
        raise HTTPException(
            status_code=403,
            detail="Your stakeholder role is not authorized for this operation."
        )

    return role


@app.post("/auth/nonce")
def request_login_nonce(request: NonceRequest):
    try:
        message = generate_login_challenge(request.wallet_address)

        return {"message": message}

    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))


@app.post("/auth/verify")
def authenticate_wallet(request: WalletVerificationRequest):
    try:
        is_verified = verify_wallet_signature(
            request.wallet_address,
            request.signature
        )

        if not is_verified:
            raise HTTPException(
                status_code=401,
                detail="Wallet signature verification failed."
            )

        role = get_stakeholder_role(request.wallet_address)

        if role == 0:
            raise HTTPException(
                status_code=403,
                detail="Wallet is not registered as a stakeholder."
            )

        if role not in ROLE_NAMES:
            raise HTTPException(
                status_code=403,
                detail="Invalid stakeholder role."
            )

        access_token = create_access_token(
            request.wallet_address,
            role
        )

        return {
            "message": "Wallet authentication successful",
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": 3600,
            "wallet_address": request.wallet_address,
            "role": role,
            "role_name": ROLE_NAMES[role]
        }

    except HTTPException:
        raise

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Wallet authentication failed."
        )


@app.post("/admin/register-stakeholder")
def admin_register_stakeholder(
    request: StakeholderRegistrationRequest,
    current_user: dict = Depends(get_current_user)
):
    if current_user["role"] != 1:
        raise HTTPException(
            status_code=403,
            detail="Only Admin users can register stakeholders."
        )

    try:
        if request.role not in [2, 3, 4, 5, 6]:
            raise ValueError("Invalid stakeholder role.")

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

    except Exception as error:
        print(
            f"Stakeholder registration error: {type(error).__name__}: {error}",
            flush=True
        )
        raise HTTPException(
            status_code=500,
            detail="Stakeholder registration failed."
        ) from error


@app.post("/admin/revoke-stakeholder")
def admin_revoke_stakeholder(
    request: StakeholderRevocationRequest,
    current_user: dict = Depends(get_current_user)
):
    if current_user["role"] != 1:
        raise HTTPException(
            status_code=403,
            detail="Only Admin users can revoke stakeholders."
        )

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
            detail="Stakeholder revocation failed."
        )


@app.get("/")
def root():
    return {
        "message": "C3 ZKP Backend is running successfully",
        "system": "System 1 - Selective ZKP",
        "status": "Active"
    }


@app.get("/health")
def health_check():
    return {"status": "healthy"}


@app.get("/records/{transaction_hash}")
def get_record(
    transaction_hash: str,
    current_user: dict = Depends(get_current_user)
):
    role = require_operational_stakeholder(current_user)

    try:
        record = get_record_by_transaction_hash(transaction_hash)

        allowed_attributes = get_allowed_attributes(ROLE_NAMES[role])

        return {
            "transaction_hash": record["transaction_hash"],
            "record_id": record["record_id"],
            "manufacturer": record["manufacturer"],
            "created_at": record["created_at"],
            "commitments": record["commitments"],
            "allowed_attributes": [
                {
                    "name": attribute,
                    "index": index
                }
                for index, attribute in enumerate([
                    "product_id",
                    "product_name",
                    "batch_number",
                    "manufacturing_date",
                    "expiry_date",
                    "manufacturer_id",
                    "shipment_id",
                    "quantity",
                    "source_location",
                    "destination_location",
                ])
                if attribute in allowed_attributes
            ],
            "role": role,
            "role_name": ROLE_NAMES[role]
        }

    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve the supply-chain record."
        )


@app.post("/zkp/generate-proof")
def generate_zkp(
    request: ZKPRequest,
    current_user: dict = Depends(get_current_user)
):
    role = require_operational_stakeholder(current_user)

    try:
        record = get_record_by_transaction_hash(
            request.transaction_hash
        )

        proof_data = {
            "commitments": record["commitments"],
            "role": role,
            "values": request.values,
            "salts": request.salts
        }

        result = generate_proof(proof_data)

        return {
            "message": "Selective ZKP generated and verified successfully.",
            "transaction_hash": record["transaction_hash"],
            "record_id": record["record_id"],
            "proof": result["proof"],
            "public_signals": result["public_signals"],
            "proof_generation_time_seconds": (
                result["proof_generation_time_seconds"]
            ),
            "proof_verification_time_seconds": (
                result["proof_verification_time_seconds"]
            )
        }

    except (ValueError, FileNotFoundError, RuntimeError) as error:
        raise HTTPException(
            status_code=400,
            detail=str(error)
        )

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Internal ZKP generation error."
        )

@app.get("/history/verifications")
def verification_history(
    current_user: dict = Depends(get_current_user)
):
    require_operational_stakeholder(current_user)

    try:
        history = get_verification_history(
            current_user["wallet_address"]
        )

        return {
            "wallet_address": current_user["wallet_address"],
            "role": current_user["role"],
            "role_name": ROLE_NAMES[current_user["role"]],
            "history": history
        }

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error)
        )

    except Exception as error:
        print(
            f"Verification history error: {error}",
            flush=True
        )
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve verification history."
        )

@app.get("/history/storage")
def manufacturer_storage_history(
    current_user: dict = Depends(get_current_user)
):
    # Only manufacturers can view their stored records.
    if current_user["role"] != 2:
        raise HTTPException(
            status_code=403,
            detail="Only manufacturers can access storage history."
        )

    try:
        history = get_manufacturer_storage_history(
            current_user["wallet_address"]
        )

        return {
            "wallet_address": current_user["wallet_address"],
            "role_name": ROLE_NAMES[current_user["role"]],
            "history": history
        }

    except Exception as error:
        print(f"Storage history error: {error}", flush=True)
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve storage history."
        )


@app.get("/history/manufacturer-verifications")
def manufacturer_verification_history(
    current_user: dict = Depends(get_current_user)
):
    # Only manufacturers can view verification activity for their records.
    if current_user["role"] != 2:
        raise HTTPException(
            status_code=403,
            detail="Only manufacturers can access this verification history."
        )

    try:
        history = get_manufacturer_verification_history(
            current_user["wallet_address"]
        )

        return {
            "wallet_address": current_user["wallet_address"],
            "role_name": ROLE_NAMES[current_user["role"]],
            "history": history
        }

    except Exception as error:
        print(
            f"Manufacturer verification history error: {error}",
            flush=True
        )
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve manufacturer verification history."
        )

    