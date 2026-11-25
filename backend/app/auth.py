
import os
import secrets
import time

import jwt

from eth_account import Account
from eth_account.messages import encode_defunct

from dotenv import load_dotenv
from web3 import Web3

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from backend.app.blockchain import get_stakeholder_role

# Load project environment variables
load_dotenv()


# JWT configuration
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_SECONDS = 3600


# Temporary login challenges
login_challenges = {}


if not JWT_SECRET_KEY:
    raise RuntimeError("JWT_SECRET_KEY is not configured.")

# Generate a one-time authentication challenge for a wallet
# nonce generation function
def generate_login_challenge(wallet_address: str) -> str:
    """Generate a one-time authentication challenge for a wallet."""

    if not Web3.is_address(wallet_address):
        raise ValueError("Invalid wallet address.")

    wallet_address = Web3.to_checksum_address(wallet_address)

    nonce = secrets.token_urlsafe(32)
    issued_at = int(time.time())
    expires_at = issued_at + 300  # 5 minutes

    message = (
        "C3 ZKP Supply Chain Verification System\n"
        "Sign this message to authenticate your wallet.\n\n"
        f"Wallet: {wallet_address}\n"
        f"Nonce: {nonce}\n"
        f"Issued At: {issued_at}\n"
        f"Expiration: {expires_at}"
    )

    login_challenges[wallet_address.lower()] = {
        "message": message,
        "expires_at": expires_at
    }

    return message


def verify_wallet_signature(wallet_address: str, signature: str) -> bool:
    """Verify the wallet signature using its stored one-time challenge."""

    # Reject invalid Ethereum wallet addresses.
    if not Web3.is_address(wallet_address):
        return False

    # Convert the address into its standard checksum format.
    wallet_address = Web3.to_checksum_address(wallet_address)

    # Retrieve and immediately consume the challenge to prevent reuse.
    challenge = login_challenges.pop(wallet_address.lower(), None)

    # Reject missing or already-used challenges.
    if not challenge:
        return False

    # Reject challenges that have expired.
    if time.time() > challenge["expires_at"]:
        return False

    try:
        # Convert the original challenge into an Ethereum signable message.
        message = encode_defunct(text=challenge["message"])

        # Recover the wallet address that signed the challenge.
        recovered_address = Account.recover_message(
            message,
            signature=signature
        )

        # Accept only when the recovered address matches the requested wallet.
        return (
            Web3.to_checksum_address(recovered_address)
            == wallet_address
        )

    except Exception:
        # Reject invalid signatures or signature verification errors.
        return False


def create_access_token(wallet_address: str, role: int) -> str:
    """Create a signed JWT for an authenticated stakeholder."""

    # Record the token creation time.
    issued_at = int(time.time())

    # Set the token expiration time to one hour.
    expires_at = issued_at + JWT_EXPIRATION_SECONDS

    # Define the information stored inside the JWT.
    payload = {
        "sub": Web3.to_checksum_address(wallet_address),
        "role": role,
        "iat": issued_at,
        "exp": expires_at
    }

    # Sign the payload using the secret key and HS256 algorithm.
    token = jwt.encode(
        payload,
        JWT_SECRET_KEY,
        algorithm=JWT_ALGORITHM
    )

    return token


def decode_access_token(token: str) -> dict:
    """Validate a JWT and return its authentication details."""

    try:
        # Verify the token signature and expiration time.
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM]
        )

        # Ensure the token contains the required authentication details.
        if not payload.get("sub") or not payload.get("role"):
            raise ValueError("Invalid token payload.")

        return payload

    except jwt.ExpiredSignatureError:
        # Reject tokens that have passed their expiration time.
        raise ValueError("Authentication token has expired.")

    except jwt.InvalidTokenError:
        # Reject invalid, modified, or incorrectly signed tokens.
        raise ValueError("Invalid authentication token.")



# Extract Bearer tokens from incoming API requests.
security = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """Authenticate a request using JWT and verify the stakeholder's current role."""

    # Reject requests that do not contain a Bearer token.
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required."
        )

    try:
        # Decode the JWT and retrieve the authenticated wallet details.
        payload = decode_access_token(credentials.credentials)

        wallet_address = payload["sub"]
        token_role = int(payload["role"])

        # Check the stakeholder's current role directly on the blockchain.
        current_role = get_stakeholder_role(wallet_address)

        # Reject stakeholders who have been revoked or are no longer registered.
        if current_role == 0:
            raise HTTPException(
                status_code=403,
                detail="Stakeholder access has been revoked."
            )

        # Reject tokens if the stakeholder's role has changed.
        if current_role != token_role:
            raise HTTPException(
                status_code=403,
                detail="Stakeholder role has changed. Please log in again."
            )

        # Return the verified wallet address and current role.
        return {
            "wallet_address": wallet_address,
            "role": current_role
        }

    except HTTPException:
        raise

    except Exception:
        # Reject requests when token validation or blockchain verification fails.
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication or blockchain verification failed."
        )


