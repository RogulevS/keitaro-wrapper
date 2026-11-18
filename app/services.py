from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.keitaro import KeitaroError
from app.keitaro_payload import (
    campaign_body,
    geo_stream_body,
    make_alias,
    offer_stream_body,
    parse_countries,
    pick_country_filter,
    pick_redirect_action,
    prefer_item,
)
from app.models import LocalCampaign, LocalStream, StreamOffer, TrackerSettings
from app.weights import WeightError, WeightOffer, distribute


def get_settings_row(session: Session) -> TrackerSettings:
    row = session.scalar(select(TrackerSettings).limit(1))
    if row is None:
        row = TrackerSettings(base_url="", api_key="")
        session.add(row)
        session.commit()
        session.refresh(row)
    return row


def seed_settings_from_env(session: Session, base_url: str, api_key: str) -> None:
    if not base_url or not api_key:
        return
    row = session.scalar(select(TrackerSettings).limit(1))
    if row is None:
        session.add(TrackerSettings(base_url=base_url, api_key=api_key))
        session.commit()
    elif not row.base_url and not row.api_key:
        row.base_url = base_url
        row.api_key = api_key
        row.updated_at = datetime.utcnow()
        session.commit()


def _offer_views(offers: list[StreamOffer]) -> list[WeightOffer]:
    return [
        WeightOffer(
            key=str(offer.id or offer.keitaro_offer_id),
            status=offer.status,
            share=int(offer.share or 0),
            pinned=bool(offer.pinned),
            sort_order=offer.sort_order,
        )
        for offer in offers
    ]


def _apply_weights(offers: list[StreamOffer]) -> None:
    views = _offer_views(offers)
    try:
        distribute(views)
    except WeightError:
        raise
    by_key = {view.key: view for view in views}
    for offer in offers:
        view = by_key[str(offer.id or offer.keitaro_offer_id)]
        offer.share = view.share


def _refresh_dirty(stream: LocalStream) -> None:
    stream.is_dirty = any(
        offer.draft_only
        or offer.status != (offer.published_status or "")
        or int(offer.share or 0) != int(offer.published_share or 0)
        for offer in stream.offers
    )


def _active_total(stream: LocalStream) -> int:
    return sum(offer.share for offer in stream.offers if offer.status == "active")


def serialize_campaign(campaign: LocalCampaign) -> dict:
    streams = []
    for stream in sorted(campaign.streams, key=lambda item: (item.position, item.id or 0)):
        offers = []
        for offer in sorted(stream.offers, key=lambda item: (item.sort_order, item.id or 0)):
            offers.append(
                {
                    "id": offer.id,
                    "keitaro_offer_id": offer.keitaro_offer_id,
                    "name": offer.name,
                    "share": offer.share,
                    "pinned": offer.pinned,
                    "status": offer.status,
                }
            )
        streams.append(
            {
                "id": stream.id,
                "keitaro_id": stream.keitaro_id,
                "name": stream.name,
                "stream_type": stream.stream_type,
                "position": stream.position,
                "tracks_offers": stream.tracks_offers,
                "is_dirty": stream.is_dirty,
                "active_share_total": _active_total(stream) if stream.tracks_offers else None,
                "offers": offers,
            }
        )
    return {
        "id": campaign.id,
        "keitaro_id": campaign.keitaro_id,
        "name": campaign.name,
        "alias": campaign.alias,
        "streams": streams,
    }


def _load_campaign(session: Session, keitaro_id: int) -> LocalCampaign | None:
    return session.scalar(
        select(LocalCampaign)
        .where(LocalCampaign.keitaro_id == keitaro_id)
        .options(selectinload(LocalCampaign.streams).selectinload(LocalStream.offers))
    )


def _load_stream(session: Session, stream_id: int) -> LocalStream:
    stream = session.scalar(
        select(LocalStream)
        .where(LocalStream.id == stream_id)
        .options(selectinload(LocalStream.offers), selectinload(LocalStream.campaign))
    )
    if stream is None:
        raise LookupError("Поток не найден. Сначала нажмите Fetch streams.")
    return stream


class WrapperService:
    def __init__(self, session: Session, keitaro):
        self.session = session
        self.keitaro = keitaro

    def directories(self, settings: TrackerSettings) -> dict:
        domains = self.keitaro.domains()
        groups = self.keitaro.groups()
        sources = self.keitaro.traffic_sources()
        return {
            "domains": [_public_ref(item) for item in domains],
            "groups": [_public_ref(item) for item in groups],
            "sources": [_public_ref(item) for item in sources],
            "selected": {
                "domain_id": _selected_id(domains, settings.domain_id),
                "group_id": _selected_id(groups, settings.group_id),
                "source_id": _selected_id(sources, settings.source_id),
            },
        }

    def search_offers(self, query: str) -> list[dict]:
        needle = query.strip().lower()
        found = []
        for offer in self.keitaro.offers():
            if str(offer.get("state") or "") == "deleted":
                continue
            offer_id = offer.get("id")
            name = str(offer.get("name") or "")
            if needle and needle not in name.lower() and needle not in str(offer_id):
                continue
            countries = offer.get("country") or []
            if not isinstance(countries, list):
                countries = []
            found.append(
                {
                    "id": offer_id,
                    "name": name,
                    "country": [str(code) for code in countries],
                }
            )
            if len(found) >= 30:
                break
        return found

    def create_campaign(
        self,
        *,
        name: str,
        geo: str,
        offer_id: int,
        domain_id: int,
        group_id: int,
        source_id: int,
        settings: TrackerSettings,
    ) -> dict:
        countries = parse_countries(geo)
        title = name.strip()
        if not title:
            raise ValueError("Укажите название кампании")
        if offer_id <= 0:
            raise ValueError("Выберите оффер")
        self._require_offer(offer_id)
        alias = make_alias(title)
        created = self.keitaro.create_campaign(
            campaign_body(
                name=title,
                alias=alias,
                domain_id=domain_id,
                group_id=group_id,
                source_id=source_id,
            )
        )
        campaign_id = int(created["id"])
        try:
            filter_name = pick_country_filter(self.keitaro.stream_filters())
            action_type = pick_redirect_action(self.keitaro.stream_actions())
            geo_stream = self.keitaro.create_stream(
                geo_stream_body(
                    campaign_id=campaign_id,
                    countries=countries,
                    filter_name=filter_name,
                    action_type=action_type,
                )
            )
            offer_stream = self.keitaro.create_stream(
                offer_stream_body(
                    campaign_id=campaign_id,
                    offer_id=offer_id,
                    action_type=action_type,
                )
            )
        except KeitaroError as exc:
            raise KeitaroError(
                f"Кампания {campaign_id} уже создана, но поток не собрался: {exc.message}. "
                "Не создавайте дубль, пока не проверите её в Keitaro."
            ) from exc
        settings.domain_id = domain_id
        settings.group_id = group_id
        settings.source_id = source_id
        settings.updated_at = datetime.utcnow()
        local = LocalCampaign(
            keitaro_id=campaign_id,
            name=str(created.get("name") or title),
            alias=str(created.get("alias") or alias),
            country_codes=",".join(countries),
            domain_id=domain_id,
            group_id=group_id,
            source_id=source_id,
        )
        self.session.add(local)
        self.session.flush()
        self._sync_campaign(local, [geo_stream, offer_stream])
        self.session.commit()
        self.session.refresh(local)
        return serialize_campaign(local)

    def list_remote_campaigns(self) -> list[dict]:
        rows = []
        for campaign in self.keitaro.campaigns():
            if str(campaign.get("state") or "") == "deleted":
                continue
            rows.append(
                {
                    "id": campaign.get("id"),
                    "name": campaign.get("name") or "",
                    "alias": campaign.get("alias") or "",
                    "state": campaign.get("state") or "",
                }
            )
        rows.sort(key=lambda item: str(item["name"]).lower())
        return rows

    def fetch(self, keitaro_campaign_id: int) -> dict:
        remote = self.keitaro.campaign(keitaro_campaign_id)
        streams = self.keitaro.campaign_streams(keitaro_campaign_id)
        local = _load_campaign(self.session, keitaro_campaign_id)
        if local is None:
            local = LocalCampaign(
                keitaro_id=keitaro_campaign_id,
                name=str(remote.get("name") or f"Campaign {keitaro_campaign_id}"),
                alias=str(remote.get("alias") or ""),
            )
            self.session.add(local)
            self.session.flush()
        else:
            local.name = str(remote.get("name") or local.name)
            local.alias = str(remote.get("alias") or local.alias)
        self._sync_campaign(local, streams)
        self.session.commit()
        self.session.refresh(local)
        return serialize_campaign(local)

    def editor_state(self, keitaro_campaign_id: int) -> dict | None:
        local = _load_campaign(self.session, keitaro_campaign_id)
        if local is None:
            return None
        return serialize_campaign(local)

    def add_offer(self, stream_id: int, offer_id: int) -> dict:
        stream = _load_stream(self.session, stream_id)
        if not stream.tracks_offers:
            raise ValueError("В этот поток офферы не добавляются")
        existing = next((offer for offer in stream.offers if offer.keitaro_offer_id == offer_id), None)
        if existing and existing.status == "active":
            raise ValueError("Этот оффер уже есть в потоке")
        if existing and existing.status == "removed":
            existing.status = "active"
            existing.pinned = False
        else:
            info = self._require_offer(offer_id)
            next_order = max((offer.sort_order for offer in stream.offers), default=-1) + 1
            stream.offers.append(
                StreamOffer(
                    keitaro_offer_id=offer_id,
                    name=str(info.get("name") or f"Offer {offer_id}"),
                    share=0,
                    pinned=False,
                    status="active",
                    draft_only=True,
                    published_share=None,
                    published_status=None,
                    published_pinned=False,
                    sort_order=next_order,
                )
            )
            self.session.flush()
        _apply_weights(stream.offers)
        _refresh_dirty(stream)
        self.session.commit()
        return serialize_campaign(stream.campaign)

    def remove_offer(self, stream_id: int, offer_row_id: int) -> dict:
        stream = _load_stream(self.session, stream_id)
        offer = self._offer_row(stream, offer_row_id)
        if offer.status != "active":
            raise ValueError("Оффер уже снят")
        offer.status = "removed"
        offer.share = 0
        offer.pinned = False
        _apply_weights(stream.offers)
        _refresh_dirty(stream)
        self.session.commit()
        return serialize_campaign(stream.campaign)

    def restore_offer(self, stream_id: int, offer_row_id: int) -> dict:
        stream = _load_stream(self.session, stream_id)
        offer = self._offer_row(stream, offer_row_id)
        if offer.status != "removed":
            raise ValueError("Оффер и так в потоке")
        offer.status = "active"
        offer.pinned = False
        _apply_weights(stream.offers)
        _refresh_dirty(stream)
        self.session.commit()
        return serialize_campaign(stream.campaign)

    def pin_offer(self, stream_id: int, offer_row_id: int, pinned: bool, share: int | None) -> dict:
        stream = _load_stream(self.session, stream_id)
        offer = self._offer_row(stream, offer_row_id)
        if offer.status != "active":
            raise ValueError("Снятый оффер нельзя закрепить")
        if pinned:
            if share is None:
                share = offer.share
            if share < 0 or share > 100:
                raise ValueError("Вес должен быть от 0 до 100")
            offer.pinned = True
            offer.share = share
        else:
            offer.pinned = False
        _apply_weights(stream.offers)
        _refresh_dirty(stream)
        self.session.commit()
        return serialize_campaign(stream.campaign)

    def cancel(self, stream_id: int) -> dict:
        stream = _load_stream(self.session, stream_id)
        for offer in list(stream.offers):
            if offer.draft_only or offer.published_status is None:
                stream.offers.remove(offer)
                self.session.delete(offer)
                continue
            offer.status = offer.published_status
            offer.share = int(offer.published_share or 0)
            offer.pinned = bool(offer.published_pinned)
            offer.draft_only = False
        self.session.flush()
        stream.is_dirty = False
        self.session.commit()
        return serialize_campaign(stream.campaign)

    def push(self, stream_id: int) -> dict:
        stream = _load_stream(self.session, stream_id)
        if not stream.tracks_offers:
            raise ValueError("У этого потока нечего публиковать")
        active = [offer for offer in stream.offers if offer.status == "active"]
        total = sum(offer.share for offer in active)
        if active and total != 100:
            raise ValueError(f"Сумма весов {total}, а должна быть 100")
        payload = [
            {"offer_id": offer.keitaro_offer_id, "share": offer.share, "state": "active"}
            for offer in sorted(active, key=lambda item: item.sort_order)
        ]
        self.keitaro.update_stream_offers(stream.keitaro_id, payload)
        for offer in stream.offers:
            offer.published_status = offer.status
            offer.published_share = offer.share
            offer.published_pinned = offer.pinned
            offer.draft_only = False
        stream.is_dirty = False
        self.session.commit()
        return serialize_campaign(stream.campaign)

    def _sync_campaign(self, local: LocalCampaign, remote_streams: list[dict]) -> None:
        names = self._offer_name_map()
        seen: set[int] = set()
        by_remote = {stream.keitaro_id: stream for stream in local.streams}
        for remote in remote_streams:
            remote_id = int(remote["id"])
            seen.add(remote_id)
            stream = by_remote.get(remote_id)
            if stream is None:
                stream = LocalStream(campaign_id=local.id, keitaro_id=remote_id)
                local.streams.append(stream)
                self.session.flush()
            stream.name = str(remote.get("name") or f"Flow {remote_id}")
            stream.stream_type = str(remote.get("type") or "")
            stream.schema_name = str(remote.get("schema") or "")
            stream.position = int(remote.get("position") or 0)
            remote_offers = remote.get("offers") or []
            if remote_offers:
                stream.tracks_offers = True
            if stream.tracks_offers:
                self._sync_offers(stream, remote_offers, names)
            stream.is_dirty = False
        for stream in list(local.streams):
            if stream.keitaro_id not in seen:
                self.session.delete(stream)

    def _sync_offers(self, stream: LocalStream, remote_offers: list[dict], names: dict[int, str]) -> None:
        present: set[int] = set()
        by_offer = {offer.keitaro_offer_id: offer for offer in stream.offers}
        for index, remote in enumerate(remote_offers):
            offer_id = int(remote["offer_id"])
            present.add(offer_id)
            state = str(remote.get("state") or "active")
            status = "active" if state == "active" else "removed"
            share = int(remote.get("share") or 0) if status == "active" else 0
            row = by_offer.get(offer_id)
            if row is None:
                row = StreamOffer(
                    stream_id=stream.id,
                    keitaro_offer_id=offer_id,
                    sort_order=index,
                )
                stream.offers.append(row)
            row.name = names.get(offer_id) or row.name or f"Offer {offer_id}"
            row.status = status
            row.share = share
            row.pinned = False
            row.draft_only = False
            row.published_status = status
            row.published_share = share
            row.published_pinned = False
            row.sort_order = index
        for row in stream.offers:
            if row.keitaro_offer_id in present:
                continue
            row.status = "removed"
            row.share = 0
            row.pinned = False
            row.draft_only = False
            row.published_status = "removed"
            row.published_share = 0
            row.published_pinned = False

    def _offer_name_map(self) -> dict[int, str]:
        names: dict[int, str] = {}
        try:
            catalog = self.keitaro.offers()
        except KeitaroError:
            return names
        for offer in catalog:
            if offer.get("id") is None:
                continue
            names[int(offer["id"])] = str(offer.get("name") or f"Offer {offer['id']}")
        return names

    def _require_offer(self, offer_id: int) -> dict:
        for offer in self.keitaro.offers():
            if int(offer.get("id") or 0) == offer_id:
                return offer
        raise ValueError(f"Оффер {offer_id} не найден в Keitaro")

    @staticmethod
    def _offer_row(stream: LocalStream, offer_row_id: int) -> StreamOffer:
        offer = next((item for item in stream.offers if item.id == offer_row_id), None)
        if offer is None:
            raise LookupError("Оффер не найден в этом потоке")
        return offer


def _public_ref(item: dict) -> dict:
    return {"id": item.get("id"), "name": item.get("name") or ""}


def _selected_id(items: list[dict], saved_id: int | None) -> int | None:
    chosen = prefer_item(items, saved_id)
    if chosen is None or chosen.get("id") is None:
        return None
    return int(chosen["id"])
