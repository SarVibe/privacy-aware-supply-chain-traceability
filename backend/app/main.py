from functools import lru_cache
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from src.application_config import Config
from src.common.encoding.versioned_bloom import IncompatibleBloomError
from src.rq2.harmonization_pipeline import HarmonizationPipeline


class HarmonizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_id: str = Field(min_length=1, max_length=256)
    raw_description: str = Field(min_length=1, max_length=4096)
    true_entity_id: str = Field(default="", max_length=256)
    stakeholder_org: str = Field(default="Generic_Org", min_length=1, max_length=256)
    dosage: Optional[str] = Field(default=None, max_length=256)
    dosage_form: Optional[str] = Field(default=None, max_length=256)
    pack_size: Optional[str] = Field(default=None, max_length=128)


class HarmonizeResponse(BaseModel):
    encoder_version: str
    record_id: str
    predicted_cluster_id: str
    similarity_score: float
    is_new_cluster: bool
    stakeholder_org: str
    preledger_latency_ms: float
    total_latency_ms: float
    gas_used: int
    tx_hash: str
    onchain_status: str


@lru_cache(maxsize=1)
def get_pipeline() -> HarmonizationPipeline:
    return HarmonizationPipeline(
        epsilon=Config.DEFAULT_EPSILON,
        enable_blockchain_commit=Config.API_ENABLE_BLOCKCHAIN_COMMIT,
        connect_ledger=True,
    )


app = FastAPI(
    title="Component 1 Harmonization API",
    version="1.0.0",
    description="Pre-ledger supply-chain record harmonization service.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "blockchain_commit_enabled": Config.API_ENABLE_BLOCKCHAIN_COMMIT,
    }


@app.post("/api/v1/harmonize", response_model=HarmonizeResponse)
def harmonize(request: HarmonizeRequest) -> HarmonizeResponse:
    try:
        result = get_pipeline().process_single_record(
            record_id=request.record_id,
            raw_description=request.raw_description,
            true_entity_id=request.true_entity_id,
            stakeholder_org=request.stakeholder_org,
            dosage=request.dosage,
            dosage_form=request.dosage_form,
            pack_size=request.pack_size,
        )
    except IncompatibleBloomError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return HarmonizeResponse(**result)


@app.get("/api/v1/ledger/summary")
def ledger_summary() -> dict:
    try:
        return get_pipeline().blockchain.get_ledger_summary()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
