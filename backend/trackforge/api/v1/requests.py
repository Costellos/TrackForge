"""
Requests endpoint.

POST /requests — submit a request for an artist or collection from a MB search result.
GET  /requests — list requests (own requests for users, all for admins).
GET  /requests/{id} — get a single request.
POST /requests/{id}/approve — admin approves a request.
POST /requests/{id}/cancel — cancel a request.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from trackforge.api.deps import get_current_user, require_admin
from trackforge.database import get_db
from trackforge.db.models import AcquisitionJob, Artist, Collection, ExternalIdentifier, Request, Song, User
from trackforge.domain.services.request_service import (
    create_request,
    get_or_create_artist,
    get_or_create_collection,
    get_or_create_song,
)
from trackforge.domain.services.notification_service import notify_request_status
from trackforge.domain.services.settings_service import get_all_settings as get_db_settings, get_setting_bool

router = APIRouter(prefix="/requests", tags=["requests"])


# ─────────────────────────────────────────────
# SCHEMAS
# ─────────────────────────────────────────────

class ArtistRequestBody(BaseModel):
    mbid: str
    name: str
    sort_name: str | None = None
    user_notes: str | None = None


class CollectionRequestBody(BaseModel):
    mbid: str
    title: str
    type: str = "album"
    first_release_date: str | None = None
    artist_mbid: str | None = None
    artist_name: str | None = None
    user_notes: str | None = None


class SongRequestBody(BaseModel):
    recording_mbid: str
    title: str
    artist_mbid: str | None = None
    artist_name: str | None = None
    length_ms: int | None = None
    user_notes: str | None = None


class MbidStatusBody(BaseModel):
    mbids: list[str]


class MbidStatusResponse(BaseModel):
    # maps mbid -> status string (or None if no active request)
    statuses: dict[str, str | None]


class RequestResponse(BaseModel):
    id: str
    target_type: str
    target_id: str
    status: str
    user_notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────
# MBID STATUS CHECK
# ─────────────────────────────────────────────

@router.post("/status", response_model=MbidStatusResponse)
async def check_mbid_statuses(
    body: MbidStatusBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Given a list of MusicBrainz IDs, return the user's active request status
    for each one (or None if no active request exists).
    """
    if not body.mbids:
        return MbidStatusResponse(statuses={})

    # Find all external identifiers matching the given MBIDs
    ext_result = await db.execute(
        select(ExternalIdentifier).where(
            ExternalIdentifier.provider == "musicbrainz",
            ExternalIdentifier.external_id.in_(body.mbids),
        )
    )
    ext_ids = ext_result.scalars().all()

    # Build a map: entity_id -> mbid
    entity_to_mbid: dict[str, str] = {e.entity_id: e.external_id for e in ext_ids}

    if not entity_to_mbid:
        return MbidStatusResponse(statuses={mbid: None for mbid in body.mbids})

    # Find active requests for this user against those entity IDs
    active_statuses = ["pending_approval", "approved", "searching", "downloading", "processing", "available"]
    req_result = await db.execute(
        select(Request).where(
            Request.user_id == user.id,
            Request.target_id.in_(list(entity_to_mbid.keys())),
            Request.status.in_(active_statuses),
        )
    )
    requests = req_result.scalars().all()

    # Build a map: entity_id -> status
    entity_status: dict[str, str] = {r.target_id: r.status for r in requests}

    # Map back to MBIDs
    statuses: dict[str, str | None] = {}
    for mbid in body.mbids:
        # Find entity_id for this mbid
        entity_id = next((e.entity_id for e in ext_ids if e.external_id == mbid), None)
        statuses[mbid] = entity_status.get(entity_id) if entity_id else None

    return MbidStatusResponse(statuses=statuses)


# ─────────────────────────────────────────────
# SUBMIT REQUESTS
# ─────────────────────────────────────────────

@router.post("/artist", response_model=RequestResponse, status_code=status.HTTP_201_CREATED)
async def request_artist(
    body: ArtistRequestBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    artist = await get_or_create_artist(db, body.mbid, body.name, body.sort_name)

    # Admins always auto-approved; regular users auto-approved if approval not required
    is_admin = user.role in ("admin", "moderator")
    require_approval = await get_setting_bool(db, "require_approval")
    auto_approve = is_admin or not require_approval

    try:
        request = await create_request(
            db=db,
            user_id=user.id,
            target_type="artist",
            target_id=artist.id,
            user_notes=body.user_notes,
            auto_approve=auto_approve,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    await db.commit()
    await db.refresh(request)
    await notify_request_status(db, request)
    return request


@router.post("/collection", response_model=RequestResponse, status_code=status.HTTP_201_CREATED)
async def request_collection(
    body: CollectionRequestBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    collection = await get_or_create_collection(
        db=db,
        mbid=body.mbid,
        title=body.title,
        collection_type=body.type,
        artist_mbid=body.artist_mbid,
        artist_name=body.artist_name,
        release_date=body.first_release_date,
    )

    is_admin = user.role in ("admin", "moderator")
    require_approval = await get_setting_bool(db, "require_approval")
    auto_approve = is_admin or not require_approval

    try:
        request = await create_request(
            db=db,
            user_id=user.id,
            target_type="collection",
            target_id=collection.id,
            user_notes=body.user_notes,
            search_params={
                "title": body.title,
                "artist_name": body.artist_name,
                "artist_mbid": body.artist_mbid,
                "mbid": body.mbid,
            },
            auto_approve=auto_approve,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    await db.commit()
    await db.refresh(request)
    await notify_request_status(db, request)
    return request


@router.post("/song", response_model=RequestResponse, status_code=status.HTTP_201_CREATED)
async def request_song(
    body: SongRequestBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    song = await get_or_create_song(
        db=db,
        recording_mbid=body.recording_mbid,
        title=body.title,
        artist_mbid=body.artist_mbid,
        artist_name=body.artist_name,
        length_ms=body.length_ms,
    )

    is_admin = user.role in ("admin", "moderator")
    require_approval = await get_setting_bool(db, "require_approval")
    auto_approve = is_admin or not require_approval

    try:
        request = await create_request(
            db=db,
            user_id=user.id,
            target_type="song",
            target_id=song.id,
            user_notes=body.user_notes,
            search_params={
                "title": body.title,
                "artist_name": body.artist_name,
                "recording_mbid": body.recording_mbid,
            },
            auto_approve=auto_approve,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    await db.commit()
    await db.refresh(request)
    await notify_request_status(db, request)
    return request


# ─────────────────────────────────────────────
# LIST / GET
# ─────────────────────────────────────────────

@router.get("", response_model=list[RequestResponse])
async def list_requests(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role in ("admin", "moderator"):
        result = await db.execute(select(Request).order_by(Request.created_at.desc()))
    else:
        result = await db.execute(
            select(Request).where(Request.user_id == user.id).order_by(Request.created_at.desc())
        )
    return result.scalars().all()


class LibraryEntryResponse(BaseModel):
    id: str
    target_type: str
    target_id: str
    status: str
    user_notes: str | None
    created_at: datetime
    name: str
    subtitle: str | None
    year: str | None
    requested_by: str | None  # username of the requester
    mbid: str | None = None  # MusicBrainz ID for cover art
    jellyfin_item_id: str | None = None  # Jellyfin item ID for direct link

    model_config = {"from_attributes": True}


class LibraryResponse(BaseModel):
    entries: list[LibraryEntryResponse]
    jellyfin_url: str | None = None


@router.get("/library", response_model=LibraryResponse)
async def list_library(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return active/available requests for the library page."""
    visible_statuses = ["pending_approval", "approved", "searching", "downloading", "processing", "available", "failed"]
    if user.role in ("admin", "moderator"):
        result = await db.execute(
            select(Request).where(Request.status.in_(visible_statuses)).order_by(Request.created_at.desc())
        )
    else:
        result = await db.execute(
            select(Request).where(
                Request.user_id == user.id,
                Request.status.in_(visible_statuses),
            ).order_by(Request.created_at.desc())
        )
    requests = result.scalars().all()

    # Batch-load users for username display
    user_ids = list({r.user_id for r in requests})
    users_result = await db.execute(select(User).where(User.id.in_(user_ids)))
    users_map: dict[str, User] = {u.id: u for u in users_result.scalars().all()}

    # Collect IDs by type for batch loading
    artist_ids = [r.target_id for r in requests if r.target_type == "artist"]
    collection_ids = [r.target_id for r in requests if r.target_type == "collection"]
    song_ids = [r.target_id for r in requests if r.target_type == "song"]

    artists: dict[str, Artist] = {}
    if artist_ids:
        a_result = await db.execute(select(Artist).where(Artist.id.in_(artist_ids)))
        artists = {a.id: a for a in a_result.scalars().all()}

    collections: dict[str, Collection] = {}
    collection_artist_ids: list[str] = []
    if collection_ids:
        c_result = await db.execute(select(Collection).where(Collection.id.in_(collection_ids)))
        for c in c_result.scalars().all():
            collections[c.id] = c
            if c.primary_artist_id:
                collection_artist_ids.append(c.primary_artist_id)

    songs: dict[str, Song] = {}
    song_artist_map: dict[str, str] = {}  # song_id -> artist_id
    if song_ids:
        from trackforge.db.models import ArtistCredit
        s_result = await db.execute(select(Song).where(Song.id.in_(song_ids)))
        songs = {s.id: s for s in s_result.scalars().all()}
        # Load primary artist credits for songs
        credit_result = await db.execute(
            select(ArtistCredit).where(
                ArtistCredit.song_id.in_(song_ids),
                ArtistCredit.role == "primary",
            )
        )
        for credit in credit_result.scalars().all():
            song_artist_map[credit.song_id] = credit.artist_id
            collection_artist_ids.append(credit.artist_id)

    # Load any artists referenced by collections/songs that we don't already have
    missing = [aid for aid in collection_artist_ids if aid not in artists]
    if missing:
        m_result = await db.execute(select(Artist).where(Artist.id.in_(missing)))
        for a in m_result.scalars().all():
            artists[a.id] = a

    # Batch-load MusicBrainz IDs for cover art
    all_entity_ids = [r.target_id for r in requests]
    mbid_map: dict[str, str] = {}
    if all_entity_ids:
        ext_result = await db.execute(
            select(ExternalIdentifier).where(
                ExternalIdentifier.provider == "musicbrainz",
                ExternalIdentifier.entity_id.in_(all_entity_ids),
            )
        )
        for ext in ext_result.scalars().all():
            mbid_map[ext.entity_id] = ext.external_id

    entries = []
    for req in requests:
        name = ""
        subtitle = None
        year = None

        if req.target_type == "artist":
            artist = artists.get(req.target_id)
            if artist:
                name = artist.name
        elif req.target_type == "song":
            song = songs.get(req.target_id)
            if song:
                name = song.title
                artist_id = song_artist_map.get(song.id)
                if artist_id and artist_id in artists:
                    subtitle = artists[artist_id].name
        elif req.target_type == "collection":
            col = collections.get(req.target_id)
            if col:
                name = col.title
                parts = []
                if col.collection_type:
                    parts.append(col.collection_type.replace("_", " ").title())
                if col.primary_artist_id and col.primary_artist_id in artists:
                    parts.append(artists[col.primary_artist_id].name)
                subtitle = " · ".join(parts) if parts else None
                if col.release_date:
                    year = str(col.release_date.year)

        requester = users_map.get(req.user_id)
        entries.append(LibraryEntryResponse(
            id=req.id,
            target_type=req.target_type,
            target_id=req.target_id,
            status=req.status,
            user_notes=req.user_notes,
            created_at=req.created_at,
            name=name or req.target_id,
            subtitle=subtitle,
            year=year,
            requested_by=requester.username if requester else None,
            mbid=mbid_map.get(req.target_id),
            jellyfin_item_id=(req.search_params or {}).get("jellyfin_item_id"),
        ))

    db_settings = await get_db_settings(db)
    return LibraryResponse(
        entries=entries,
        jellyfin_url=db_settings.get("jellyfin_external_url") or None,
    )


@router.get("/{request_id}", response_model=RequestResponse)
async def get_request(
    request_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    request = await db.get(Request, request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")
    if user.role not in ("admin", "moderator") and request.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your request")
    return request


# ─────────────────────────────────────────────
# ADMIN ACTIONS
# ─────────────────────────────────────────────

@router.post("/{request_id}/approve", response_model=RequestResponse)
async def approve_request(
    request_id: str,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    request = await db.get(Request, request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")
    if request.status != "pending_approval":
        raise HTTPException(status_code=400, detail=f"Request is already {request.status}")

    request.status = "approved"
    request.approved_by = admin.id
    request.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(request)
    await notify_request_status(db, request)
    return request


class RejectBody(BaseModel):
    admin_notes: str | None = None


@router.post("/{request_id}/reject", response_model=RequestResponse)
async def reject_request(
    request_id: str,
    body: RejectBody = RejectBody(),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    request = await db.get(Request, request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")
    if request.status != "pending_approval":
        raise HTTPException(status_code=400, detail=f"Request is already {request.status}")

    request.status = "rejected"
    request.admin_notes = body.admin_notes
    request.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(request)
    await notify_request_status(db, request)
    return request


@router.post("/{request_id}/retry", response_model=RequestResponse)
async def retry_request(
    request_id: str,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    request = await db.get(Request, request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")
    if request.status != "failed":
        raise HTTPException(status_code=400, detail=f"Only failed requests can be retried (current: {request.status})")

    # Cancel all existing failed/queued jobs so the worker creates a fresh one
    jobs_result = await db.execute(
        select(AcquisitionJob).where(
            AcquisitionJob.request_id == request_id,
            AcquisitionJob.status.in_(["failed", "queued", "submitted"]),
        )
    )
    for job in jobs_result.scalars().all():
        job.status = "cancelled"
        job.updated_at = datetime.now(timezone.utc)

    request.status = "approved"
    request.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(request)
    return request


class CandidateResponse(BaseModel):
    title: str
    download_url: str
    indexer: str
    size: int
    age_days: float
    grabs: int
    format_score: int
    score: float
    already_tried: bool


@router.get("/{request_id}/candidates", response_model=list[CandidateResponse])
async def list_candidates(
    request_id: str,
    artist_override: str | None = None,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Search Prowlarr for available NZBs and return scored results. Admin only."""
    from trackforge.config import get_settings
    from trackforge.adapters.acquisition.prowlarr import ProwlarrClient
    from trackforge.domain.services.acquisition_service import _resolve_name, _build_query

    settings = get_settings()
    request = await db.get(Request, request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")

    if not settings.prowlarr_url or not settings.prowlarr_api_key:
        raise HTTPException(status_code=400, detail="Prowlarr not configured")

    prowlarr = ProwlarrClient(settings.prowlarr_url, settings.prowlarr_api_key)
    name, artist_name = await _resolve_name(db, request)
    if artist_override:
        artist_name = artist_override
    query = _build_query(request.target_type, name, artist_name)

    results = await prowlarr.search(query)

    # Find previously tried URLs
    tried_result = await db.execute(
        select(AcquisitionJob.source_url).where(
            AcquisitionJob.request_id == request_id,
            AcquisitionJob.source_url.isnot(None),
            AcquisitionJob.status.in_(["failed", "cancelled"]),
        )
    )
    tried_urls = {row[0] for row in tried_result.all()}

    return [
        CandidateResponse(
            title=r.title,
            download_url=r.download_url,
            indexer=r.indexer,
            size=r.size,
            age_days=round(r.age_days, 1),
            grabs=r.grabs,
            format_score=r.format_score,
            score=round(r.score, 2),
            already_tried=r.download_url in tried_urls,
        )
        for r in results
    ]


class SelectCandidateBody(BaseModel):
    download_url: str
    title: str


@router.post("/{request_id}/select-candidate", response_model=RequestResponse)
async def select_candidate(
    request_id: str,
    body: SelectCandidateBody,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Admin selects a specific NZB to download. Creates a new job with the chosen URL."""
    import uuid as _uuid
    from datetime import timezone
    from trackforge.config import get_settings
    from trackforge.adapters.acquisition.nzbget import NZBGetClient

    settings = get_settings()
    request = await db.get(Request, request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")
    if request.status not in ("failed", "approved", "searching"):
        raise HTTPException(status_code=400, detail=f"Cannot select candidate for {request.status} request")

    if not settings.nzbget_url:
        raise HTTPException(status_code=400, detail="NZBGet not configured")

    # Cancel any existing live jobs
    live_result = await db.execute(
        select(AcquisitionJob).where(
            AcquisitionJob.request_id == request_id,
            AcquisitionJob.status.in_(["queued", "submitted", "downloading"]),
        )
    )
    for old_job in live_result.scalars().all():
        old_job.status = "cancelled"
        old_job.updated_at = datetime.now(timezone.utc)

    # Submit the chosen NZB to NZBGet
    nzbget = NZBGetClient(settings.nzbget_url, settings.nzbget_username, settings.nzbget_password)
    nzbid = await nzbget.append(body.title, body.download_url, settings.nzbget_category)

    # Create the new job
    job = AcquisitionJob(
        id=str(_uuid.uuid4()),
        request_id=request_id,
        adapter="nzbget",
        status="downloading",
        external_id=str(nzbid),
        source_url=body.download_url,
        source_query=body.title,
        started_at=datetime.now(timezone.utc),
    )
    db.add(job)

    request.status = "downloading"
    request.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(request)
    return request


@router.post("/{request_id}/cancel", response_model=RequestResponse)
async def cancel_request(
    request_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    request = await db.get(Request, request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")
    if user.role not in ("admin", "moderator") and request.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your request")
    if request.status in ("available", "cancelled"):
        raise HTTPException(status_code=400, detail=f"Cannot cancel a {request.status} request")

    request.status = "cancelled"
    request.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(request)
    return request
