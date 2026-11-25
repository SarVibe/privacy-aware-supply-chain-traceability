
# Load environment variables and access configured frontend URLs.
import os
from dotenv import load_dotenv
from pathlib import Path

# Import FastAPI dependency support for protected endpoints.
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel


# Enable cross-origin requests from the React frontend.
from fastapi.middleware.cors import CORSMiddleware

from backend.app.zkp_service import generate_proof
from backend.app.blockchain import (
    verify_supply_chain,
    register_stakeholder,
    revoke_stakeholder,
    get_stakeholder_role,
    can_access_attribute
)

# Import wallet authentication and JWT functions.
from backend.app.auth import (
    generate_login_challenge,
    verify_wallet_signature,
    create_access_token
)
# Import the JWT authentication dependency for protected API routes.
from backend.app.auth import get_current_user

# Initialize FastAPI application
app = FastAPI(
    title="C3 ZKP Supply Chain Verification System",
    description="Zero-Knowledge Proof Based Supply Chain Verification",
    version="1.0.0"
)

# Load environment variables from the project root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

# Read the permitted frontend URLs from the environment.
frontend_origins = [
    origin.strip()
    for origin in os.getenv("FRONTEND_ORIGINS", "").split(",")
    if origin.strip()
]

# Configure CORS for the permitted frontend applications.
app.add_middleware(
    CORSMiddleware,
    allow_origins=frontend_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Define supply-chain verification request
class ZKPRequest(BaseModel):
    actual: dict[str, str]
    expected: dict[str, str]

# Define the ZKP verification request without collecting private keys.
class BlockchainVerificationRequest(BaseModel):
    proof: dict
    public_signals: list[str]
    requested_attributes: list[int]

# Define stakeholder registration request
class StakeholderRegistrationRequest(BaseModel):
    stakeholder_address: str
    role: int


# Define stakeholder revocation request
class StakeholderRevocationRequest(BaseModel):
    stakeholder_address: str

# Define the wallet nonce request.
class NonceRequest(BaseModel):
    wallet_address: str


# Define the wallet signature verification request.
class WalletVerificationRequest(BaseModel):
    wallet_address: str
    signature: str



# Generate a one-time message for MetaMask wallet authentication.
@app.post("/auth/nonce")
def request_login_nonce(request: NonceRequest):
    try:
        # Generate a unique message that the wallet must sign.
        message = generate_login_challenge(request.wallet_address)

        return {
            "message": message
        }

    except ValueError as error:
        # Return an error when the wallet address is invalid.
        raise HTTPException(status_code=400, detail=str(error))


# Verify the wallet signature and issue a JWT access token.
@app.post("/auth/verify")
def authenticate_wallet(request: WalletVerificationRequest):
    try:
        # Verify that the signature belongs to the requested wallet.
        is_verified = verify_wallet_signature(
            request.wallet_address,
            request.signature
        )

        if not is_verified:
            raise HTTPException(
                status_code=401,
                detail="Wallet signature verification failed."
            )

        # Retrieve the stakeholder's registered blockchain role.
        role = get_stakeholder_role(request.wallet_address)

        # Reject wallets that are not registered stakeholders.
        if role == 0:
            raise HTTPException(
                status_code=403,
                detail="Wallet is not registered as a stakeholder."
            )

        # Convert the role number into a readable role name.
        role_names = {
            1: "Admin",
            2: "Manufacturer",
            3: "Logistics Provider",
            4: "Warehouse",
            5: "Distributor",
            6: "Pharmacy"
        }

        # Reject unsupported stakeholder roles.
        if role not in role_names:
            raise HTTPException(
                status_code=403,
                detail="Invalid stakeholder role."
            )

        # Generate a JWT for the authenticated stakeholder.
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
            "role_name": role_names[role]
        }

    except HTTPException:
        raise

    except Exception:
        # Handle unexpected authentication or blockchain errors.
        raise HTTPException(
            status_code=500,
            detail="Wallet authentication failed."
        )


# Register a stakeholder using Admin account
# Only authenticated Admin users can register stakeholders.
@app.post("/admin/register-stakeholder")
def admin_register_stakeholder(
    request: StakeholderRegistrationRequest,
    current_user: dict = Depends(get_current_user)
):
    # Reject users who do not have the Admin role.
    if current_user["role"] != 1:
        raise HTTPException(
            status_code=403,
            detail="Only Admin users can register stakeholders."
        )
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


# Only authenticated Admin users can revoke stakeholders.
@app.post("/admin/revoke-stakeholder")
def admin_revoke_stakeholder(
    request: StakeholderRevocationRequest,
    current_user: dict = Depends(get_current_user)
):
    # Reject users who do not have the Admin role.
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


# Only authenticated Manufacturer users can generate ZKP proofs.
@app.post("/zkp/generate-proof")
def generate_zkp(
    request: ZKPRequest,
    current_user: dict = Depends(get_current_user)
):
    # Reject users who are not Manufacturers.
    if current_user["role"] != 2:
        raise HTTPException(
            status_code=403,
            detail="Only Manufacturer users can generate ZKP proofs."
        )
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

# Only authenticated supply-chain stakeholders can verify proofs.
@app.post("/zkp/verify-on-chain")
def verify_zkp_on_chain(
    request: BlockchainVerificationRequest,
    current_user: dict = Depends(get_current_user)
):
    # Only operational stakeholders can verify supply-chain records.
    role = current_user["role"]

    if role not in [2, 3, 4, 5, 6]:
        raise HTTPException(
            status_code=403,
            detail="Your stakeholder role is not authorized for verification."
        )

    try:
        # Validate that exactly 11 public signals are provided.
        if len(request.public_signals) != 11:
            raise ValueError("Exactly 11 public signals are required.")

        # Reject mismatched supply-chain data before blockchain submission.
        if int(request.public_signals[0]) != 1:
            raise ValueError("Supply-chain data mismatch. Verification rejected.")

        # At least one attribute must be requested.
        if not request.requested_attributes:
            raise ValueError("No attributes requested.")

        # Reject duplicate attribute requests.
        if len(request.requested_attributes) != len(set(request.requested_attributes)):
            raise ValueError("Duplicate attributes requested.")

        # Check stakeholder permissions for every requested attribute.
        for index in request.requested_attributes:
            if index < 0 or index >= 10:
                raise ValueError(f"Invalid attribute index: {index}")

            if not can_access_attribute(role, index):
                raise PermissionError(
                    f"Access denied for attribute index {index}."
                )

        # Return validated data for the frontend to submit through MetaMask.
        return {
            "message": "ZKP verification request validated successfully.",
            "proof": request.proof,
            "public_signals": request.public_signals,
            "requested_attributes": request.requested_attributes,
            "wallet_address": current_user["wallet_address"],
            "status": "ready_for_metamask_submission"
        }

    except (ValueError, PermissionError) as error:
        raise HTTPException(
            status_code=400,
            detail=str(error)
        )

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="ZKP verification validation failed."
        )