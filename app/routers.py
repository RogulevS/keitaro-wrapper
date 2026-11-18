from __future__ import annotations

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_session
from app.keitaro import KeitaroClient, KeitaroError
from app.keitaro_payload import normalize_base_url
from app.services import WrapperService, get_settings_row
from app.weights import WeightError

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
router = APIRouter()


class SettingsIn(BaseModel):
    base_url: str = ""
    api_key: str = ""


class CampaignIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    geo: str
    offer_id: int
    domain_id: int
    group_id: int
    source_id: int


class OfferIn(BaseModel):
    offer_id: int


class PinIn(BaseModel):
    pinned: bool
    share: Optional[int] = None


def get_service(session: Session = Depends(get_session)) -> WrapperService:
    row = get_settings_row(session)
    try:
        client = KeitaroClient(row.base_url, row.api_key)
    except KeitaroError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    return WrapperService(session, client)


def _fail(exc: Exception) -> HTTPException:
    status = 400
    if isinstance(exc, KeitaroError) and exc.status in {401, 403}:
        status = 401
    return HTTPException(status_code=status, detail=str(exc))


@router.get("/", response_class=HTMLResponse)
def create_page(request: Request, session: Session = Depends(get_session)):
    row = get_settings_row(session)
    return templates.TemplateResponse(
        request,
        "create.html",
        {"configured": bool(row.base_url and row.api_key)},
    )


@router.get("/editor", response_class=HTMLResponse)
def editor_page(request: Request, session: Session = Depends(get_session)):
    row = get_settings_row(session)
    return templates.TemplateResponse(
        request,
        "editor.html",
        {"configured": bool(row.base_url and row.api_key)},
    )


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, session: Session = Depends(get_session)):
    row = get_settings_row(session)
    return templates.TemplateResponse(
        request,
        "settings.html",
        {"base_url": row.base_url, "has_key": bool(row.api_key)},
    )


@router.post("/api/settings")
def save_settings(body: SettingsIn, session: Session = Depends(get_session)):
    row = get_settings_row(session)
    row.base_url = normalize_base_url(body.base_url)
    if body.api_key.strip():
        row.api_key = body.api_key.strip()
    from datetime import datetime

    row.updated_at = datetime.utcnow()
    session.commit()
    return {"ok": True, "base_url": row.base_url, "has_key": bool(row.api_key)}


@router.get("/api/meta")
def meta(service: WrapperService = Depends(get_service)):
    try:
        return service.directories(get_settings_row(service.session))
    except (KeitaroError, ValueError) as exc:
        raise _fail(exc) from exc


@router.get("/api/offers")
def offers(q: str = "", service: WrapperService = Depends(get_service)):
    try:
        return service.search_offers(q)
    except (KeitaroError, ValueError) as exc:
        raise _fail(exc) from exc


@router.post("/api/campaigns")
def create_campaign(body: CampaignIn, service: WrapperService = Depends(get_service)):
    try:
        return service.create_campaign(
            name=body.name,
            geo=body.geo,
            offer_id=body.offer_id,
            domain_id=body.domain_id,
            group_id=body.group_id,
            source_id=body.source_id,
            settings=get_settings_row(service.session),
        )
    except (KeitaroError, ValueError, WeightError) as exc:
        raise _fail(exc) from exc


@router.get("/api/remote-campaigns")
def remote_campaigns(service: WrapperService = Depends(get_service)):
    try:
        return service.list_remote_campaigns()
    except (KeitaroError, ValueError) as exc:
        raise _fail(exc) from exc


@router.get("/api/campaigns/{campaign_id}")
def campaign_state(campaign_id: int, service: WrapperService = Depends(get_service)):
    state = service.editor_state(campaign_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Сначала нажмите Fetch streams")
    return state


@router.post("/api/campaigns/{campaign_id}/fetch")
def fetch_campaign(campaign_id: int, service: WrapperService = Depends(get_service)):
    try:
        return service.fetch(campaign_id)
    except (KeitaroError, ValueError, WeightError) as exc:
        raise _fail(exc) from exc


@router.post("/api/streams/{stream_id}/offers")
def add_offer(stream_id: int, body: OfferIn, service: WrapperService = Depends(get_service)):
    try:
        return service.add_offer(stream_id, body.offer_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (KeitaroError, ValueError, WeightError) as exc:
        raise _fail(exc) from exc


@router.post("/api/streams/{stream_id}/offers/{offer_row_id}/remove")
def remove_offer(stream_id: int, offer_row_id: int, service: WrapperService = Depends(get_service)):
    try:
        return service.remove_offer(stream_id, offer_row_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (KeitaroError, ValueError, WeightError) as exc:
        raise _fail(exc) from exc


@router.post("/api/streams/{stream_id}/offers/{offer_row_id}/restore")
def restore_offer(stream_id: int, offer_row_id: int, service: WrapperService = Depends(get_service)):
    try:
        return service.restore_offer(stream_id, offer_row_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (KeitaroError, ValueError, WeightError) as exc:
        raise _fail(exc) from exc


@router.post("/api/streams/{stream_id}/offers/{offer_row_id}/pin")
def pin_offer(
    stream_id: int,
    offer_row_id: int,
    body: PinIn,
    service: WrapperService = Depends(get_service),
):
    try:
        return service.pin_offer(stream_id, offer_row_id, body.pinned, body.share)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (KeitaroError, ValueError, WeightError) as exc:
        raise _fail(exc) from exc


@router.post("/api/streams/{stream_id}/cancel")
def cancel_stream(stream_id: int, service: WrapperService = Depends(get_service)):
    try:
        return service.cancel(stream_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (KeitaroError, ValueError, WeightError) as exc:
        raise _fail(exc) from exc


@router.post("/api/streams/{stream_id}/push")
def push_stream(stream_id: int, service: WrapperService = Depends(get_service)):
    try:
        return service.push(stream_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (KeitaroError, ValueError, WeightError) as exc:
        raise _fail(exc) from exc
