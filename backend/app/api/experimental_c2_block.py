from fastapi import APIRouter, HTTPException

from app.api.products import prepare_payload
from app.blockchain.write_service import (
    delete_product as blockchain_delete,
    insert_product as blockchain_insert,
    update_product as blockchain_update,
)
from app.schemas.product import (
    DeleteProductRequest,
    InsertProductRequest,
    UpdateProductRequest,
)
from app.services.experimental_c2_block_service import (
    ExperimentalBlockMutationCommittedError,
    get_block_status,
    mutate_and_publish_block,
    recover_block_state,
)


router = APIRouter(
    prefix="/experimental/c2-block",
    tags=["Experimental C2 (block-level)"],
)


def _run_mutation(action: str, product_id: str, mutation_function, *args):
    try:
        return mutate_and_publish_block(
            lambda: mutation_function(*args, include_timing=True),
            action,
            product_id,
        )
    except ExperimentalBlockMutationCommittedError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "message": str(exc),
                "mutation_committed": True,
                "mutation": exc.mutation_result,
                "index_fresh": False,
                "recovery_required": True,
            },
        ) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/products")
def create_block_product(request: InsertProductRequest):
    product_id, canonical_payload, digest = prepare_payload(request.payload)
    return _run_mutation(
        "insert", product_id, blockchain_insert, product_id, canonical_payload, digest
    )


@router.put("/products/{product_id}")
def update_block_product(product_id: str, request: UpdateProductRequest):
    normalized_id, canonical_payload, digest = prepare_payload(request.payload)
    if normalized_id != product_id.strip().upper():
        raise HTTPException(
            status_code=400,
            detail="Payload product_id must match the URL product_id",
        )
    return _run_mutation(
        "update",
        normalized_id,
        blockchain_update,
        normalized_id,
        request.expected_version_id,
        canonical_payload,
        digest,
    )


@router.delete("/products/{product_id}")
def delete_block_product(product_id: str, request: DeleteProductRequest):
    normalized_id = product_id.strip().upper()
    if not normalized_id:
        raise HTTPException(status_code=400, detail="product_id must not be empty")
    return _run_mutation(
        "delete",
        normalized_id,
        blockchain_delete,
        normalized_id,
        request.expected_version_id,
    )


@router.get("/status")
def block_status():
    try:
        return get_block_status()
    except (ConnectionError, FileNotFoundError, PermissionError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/recover")
def recover_block():
    try:
        return recover_block_state()
    except (ConnectionError, FileNotFoundError, PermissionError, ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc