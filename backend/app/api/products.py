from fastapi import APIRouter, HTTPException, Query
from app.services.search_service import search_product

from app.blockchain.connection import get_web3
from app.blockchain.contract import load_contract_config

from app.blockchain.read_service import (
    get_product_ids,
    get_current_product,
    get_product_history,
    get_index_status,
)

from app.blockchain.write_service import (
    insert_product as blockchain_insert,
    update_product as blockchain_update,
    delete_product as blockchain_delete,
)
from app.schemas.product import (
    InsertProductRequest,
    UpdateProductRequest,
    DeleteProductRequest,
)
from app.services.canonicalizer import (
    canonical_json,
    calculate_record_digest,
)
from app.services.orchestration_service import (
    perform_mutation_and_rebuild,
    MutationCommittedIndexError,
)
from app.services.product_validator import normalize_record


router = APIRouter(prefix="/products", tags=["Products"])


def prepare_payload(payload: dict) -> tuple[str, str, str]:
    try:
        normalized = normalize_record(payload)
        canonical_payload = canonical_json(normalized)
        payload_digest = calculate_record_digest(normalized)

        return (
            normalized["product_id"],
            canonical_payload,
            payload_digest,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


def execute_mutation(mutation_function, *args):
    try:
        return perform_mutation_and_rebuild(
            mutation_function,
            *args,
        )

    except MutationCommittedIndexError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "message": str(exc),
                "mutation_committed": True,
                "mutation": exc.mutation_result,
                "index_fresh": False,
            },
        ) from exc

    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


@router.post("")
def create_product(request: InsertProductRequest):
    product_id, canonical_payload, digest = prepare_payload(
        request.payload
    )

    return execute_mutation(
        blockchain_insert,
        product_id,
        canonical_payload,
        digest,
    )


@router.put("/{product_id}")
def update_product(
    product_id: str,
    request: UpdateProductRequest,
):
    normalized_id, canonical_payload, digest = prepare_payload(
        request.payload
    )

    if normalized_id != product_id.strip().upper():
        raise HTTPException(
            status_code=400,
            detail="Payload product_id must match the URL product_id",
        )

    return execute_mutation(
        blockchain_update,
        normalized_id,
        request.expected_version_id,
        canonical_payload,
        digest,
    )


@router.delete("/{product_id}")
def remove_product(
    product_id: str,
    request: DeleteProductRequest,
):
    normalized_id = product_id.strip().upper()

    if not normalized_id:
        raise HTTPException(
            status_code=400,
            detail="product_id must not be empty",
        )

    return execute_mutation(
        blockchain_delete,
        normalized_id,
        request.expected_version_id,
    )

@router.get("")
def list_products(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
):
    product_ids = get_product_ids(
        offset=offset,
        limit=limit,
    )

    products = []

    for product_id in product_ids:
        current = get_current_product(product_id)

        products.append({
            "product_id": product_id,
            "active": current["active"],
            "version": current["version"],
        })

    return {
        "items": products,
        "offset": offset,
        "limit": limit,
        "count": len(products),
    }


@router.get("/{product_id}/history")
def product_history(
    product_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
):
    history = get_product_history(
        product_id.strip().upper(),
        offset=offset,
        limit=limit,
    )

    if not history:
        raise HTTPException(
            status_code=404,
            detail="Product history not found",
        )

    return {
        "product_id": product_id.strip().upper(),
        "history": history,
        "offset": offset,
        "limit": limit,
        "count": len(history),
    }


@router.get("/{product_id}")
def read_product(product_id: str):
    normalized_id = product_id.strip().upper()

    history = get_product_history(
        normalized_id,
        offset=0,
        limit=1,
    )

    if not history:
        raise HTTPException(
            status_code=404,
            detail="Product not found",
        )

    current = get_current_product(normalized_id)

    return {
        "product_id": normalized_id,
        "active": current["active"],
        "version": current["version"],
    }


@router.get("/index/status")
def read_index_status():
    return get_index_status()


@router.get("/search/{product_id}")
def search_product_endpoint(product_id: str):
    try:
        return search_product(product_id)

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc

@router.get("/blockchain/status")
def blockchain_status():
    try:
        web3 = get_web3()
        config = load_contract_config()

        actual_chain_id = web3.eth.chain_id

        return {
            "connected": True,
            "chain_id": actual_chain_id,
            "expected_chain_id": config["chainId"],
            "network_match": actual_chain_id == config["chainId"],
            "contract_address": config["address"],
            "latest_block": web3.eth.block_number,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Blockchain connection failed: {str(exc)}",
        ) from exc