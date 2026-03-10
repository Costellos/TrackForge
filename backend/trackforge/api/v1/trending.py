"""
Trending endpoints — powered by ListenBrainz sitewide stats.
"""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from trackforge.adapters.metadata.listenbrainz import (
    get_trending_artists,
    get_trending_release_groups,
)
from trackforge.api.deps import get_current_user
from trackforge.db.models import User

router = APIRouter(prefix="/trending", tags=["trending"])


class TrendingReleaseGroup(BaseModel):
    release_group_mbid: str | None
    title: str | None
    artist_name: str | None
    artist_mbids: list[str]
    listen_count: int | None
    caa_id: int | None
    caa_release_mbid: str | None


class TrendingArtist(BaseModel):
    artist_mbid: str | None
    artist_name: str | None
    listen_count: int | None


@router.get("/release-groups", response_model=list[TrendingReleaseGroup])
async def trending_release_groups(
    range: str = Query("week", regex="^(week|month|quarter|half_yearly|year|all_time)$"),
    count: int = Query(20, ge=1, le=100),
    _user: User = Depends(get_current_user),
):
    return await get_trending_release_groups(count=count, range_=range)


@router.get("/artists", response_model=list[TrendingArtist])
async def trending_artists(
    range: str = Query("week", regex="^(week|month|quarter|half_yearly|year|all_time)$"),
    count: int = Query(20, ge=1, le=100),
    _user: User = Depends(get_current_user),
):
    return await get_trending_artists(count=count, range_=range)
