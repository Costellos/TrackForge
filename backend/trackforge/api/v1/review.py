"""
Tag review endpoints — read/edit tags on pending_review requests before import.
"""

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from trackforge.api.deps import require_admin
from trackforge.database import get_db
from trackforge.db.models import AcquisitionJob, ImportCandidate, MediaAsset, Request, User
from trackforge.domain.services.processing_service import finalize_import
from trackforge.domain.services.review_service import read_tags, write_tags
from trackforge.domain.services.settings_service import get_setting

log = structlog.get_logger()

router = APIRouter(prefix="/review", tags=["review"])


# ── Response models ──────────────────────────────────────────────

class FileTagsResponse(BaseModel):
    filename: str
    tags: dict[str, str]
    format: str
    duration_ms: int | None = None


class MatchCandidateResponse(BaseModel):
    filename: str
    score: float
    decision: str
    components: dict[str, float]
    matched: bool
    version_id: str | None = None


class ReviewTagsResponse(BaseModel):
    request_id: str
    name: str
    artist: str | None = None
    files: list[FileTagsResponse]
    auto_import_at: str | None = None
    match_candidates: list[MatchCandidateResponse] | None = None


class PendingReviewItem(BaseModel):
    request_id: str
    name: str
    subtitle: str | None = None
    status: str
    pending_review_at: str | None = None
    auto_import_at: str | None = None
    library_path: str | None = None


class PendingReviewResponse(BaseModel):
    items: list[PendingReviewItem]
    timeout_minutes: int


# ── Request bodies ───────────────────────────────────────────────

class FileTagEdit(BaseModel):
    filename: str
    tags: dict[str, str]


class EditTagsBody(BaseModel):
    files: list[FileTagEdit]


# ── Helpers ──────────────────────────────────────────────────────

async def _get_pending_request(db: AsyncSession, request_id: str) -> Request:
    result = await db.execute(
        select(Request).where(Request.id == request_id)
    )
    req = result.scalar_one_or_none()
    if req is None:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.status != "pending_review":
        raise HTTPException(status_code=400, detail=f"Request is not pending review (status: {req.status})")
    return req


def _compute_auto_import_at(params: dict, timeout_minutes: int) -> str | None:
    from datetime import datetime, timedelta, timezone
    review_at_str = params.get("pending_review_at")
    if not review_at_str:
        return None
    review_at = datetime.fromisoformat(review_at_str)
    if review_at.tzinfo is None:
        review_at = review_at.replace(tzinfo=timezone.utc)
    return (review_at + timedelta(minutes=timeout_minutes)).isoformat()


async def _load_match_candidates(
    db: AsyncSession, request_id: str, library_path: str,
) -> list[MatchCandidateResponse]:
    """Load ImportCandidate match data for a request's files."""
    # Find acquisition jobs for this request
    job_result = await db.execute(
        select(AcquisitionJob).where(AcquisitionJob.request_id == request_id)
    )
    jobs = job_result.scalars().all()
    if not jobs:
        return []

    job_ids = [j.id for j in jobs]

    # Load import candidates with their media assets
    ic_result = await db.execute(
        select(ImportCandidate)
        .options(selectinload(ImportCandidate.media_asset))
        .where(ImportCandidate.acquisition_job_id.in_(job_ids))
    )
    candidates = ic_result.scalars().all()

    results = []
    for ic in candidates:
        asset = ic.media_asset
        if not asset:
            continue

        import os
        filename = os.path.basename(asset.file_path)
        match_data = ic.candidates[0] if ic.candidates else {}

        results.append(MatchCandidateResponse(
            filename=filename,
            score=match_data.get("best_score", 0),
            decision=match_data.get("decision", "unknown"),
            components=match_data.get("components", {}),
            matched=ic.stage == "approved",
            version_id=str(ic.selected_version_id) if ic.selected_version_id else None,
        ))

    return results


# ── Endpoints ────────────────────────────────────────────────────

@router.get("/pending", response_model=PendingReviewResponse)
async def list_pending_reviews(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """List all requests awaiting tag review."""
    timeout_str = await get_setting(db, "tag_review_timeout_minutes")
    timeout_minutes = max(1, int(timeout_str or "5"))

    result = await db.execute(
        select(Request)
        .where(Request.status == "pending_review")
        .order_by(Request.updated_at.asc())
    )
    requests = result.scalars().all()

    items = []
    for req in requests:
        params = req.search_params or {}
        items.append(PendingReviewItem(
            request_id=str(req.id),
            name=req.target_id,
            subtitle=params.get("artist_name"),
            status=req.status,
            pending_review_at=params.get("pending_review_at"),
            auto_import_at=_compute_auto_import_at(params, timeout_minutes),
            library_path=params.get("library_path"),
        ))

    return PendingReviewResponse(items=items, timeout_minutes=timeout_minutes)


@router.get("/{request_id}/tags", response_model=ReviewTagsResponse)
async def get_review_tags(
    request_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Read audio file tags for a pending_review request."""
    req = await _get_pending_request(db, request_id)
    params = req.search_params or {}
    library_path = params.get("library_path")

    if not library_path:
        raise HTTPException(status_code=400, detail="No library path for this request")

    timeout_str = await get_setting(db, "tag_review_timeout_minutes")
    timeout_minutes = max(1, int(timeout_str or "5"))

    files = read_tags(library_path)

    # Load import candidate match data if v2 pipeline ran
    match_candidates = None
    import_v2_data = params.get("import_v2")
    if import_v2_data and import_v2_data.get("candidates", 0) > 0:
        match_candidates = await _load_match_candidates(db, req.id, library_path)

    return ReviewTagsResponse(
        request_id=str(req.id),
        name=req.target_id,
        artist=params.get("artist_name"),
        files=[FileTagsResponse(**f) for f in files],
        auto_import_at=_compute_auto_import_at(params, timeout_minutes),
        match_candidates=match_candidates,
    )


@router.post("/{request_id}/tags")
async def edit_review_tags(
    request_id: str,
    body: EditTagsBody,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Edit audio file tags for a pending_review request."""
    req = await _get_pending_request(db, request_id)
    params = req.search_params or {}
    library_path = params.get("library_path")

    if not library_path:
        raise HTTPException(status_code=400, detail="No library path for this request")

    updated = write_tags(library_path, [f.model_dump() for f in body.files])

    return {"updated": updated}


@router.post("/{request_id}/approve")
async def approve_review(
    request_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Approve tags and import the request into the library."""
    req = await _get_pending_request(db, request_id)
    await finalize_import(db, req)
    log.info("review.approved", request_id=req.id)
    return {"status": "available", "request_id": str(req.id)}
