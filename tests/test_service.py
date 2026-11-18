import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import TrackerSettings
from app.services import WrapperService


class FakeKeitaro:
    def __init__(self):
        self.created_campaign = None
        self.created_streams = []
        self.puts = []
        self.streams = {}
        self.catalog = [
            {"id": 10, "name": "Offer Ten", "state": "active", "country": ["AU"]},
            {"id": 11, "name": "Offer Eleven", "state": "active", "country": []},
            {"id": 12, "name": "Offer Twelve", "state": "active", "country": []},
            {"id": 13, "name": "Offer Thirteen", "state": "active", "country": []},
        ]

    def domains(self):
        return [{"id": 1, "name": "https://in.posdk.xyz"}]

    def groups(self):
        return [{"id": 3, "name": "Other"}, {"id": 2, "name": "FORTESTS"}]

    def traffic_sources(self):
        return [{"id": 4, "name": "FORTESTS"}]

    def offers(self):
        return self.catalog

    def stream_filters(self):
        return [{"value": "country"}]

    def stream_actions(self):
        return [{"key": "http"}]

    def create_campaign(self, body):
        self.created_campaign = body
        return {"id": 77, "name": body["name"], "alias": body["alias"]}

    def create_stream(self, body):
        stream = {"id": 500 + len(self.created_streams), **body}
        self.created_streams.append(stream)
        return stream

    def campaign(self, campaign_id):
        return {"id": campaign_id, "name": "Remote", "alias": "remote"}

    def campaign_streams(self, campaign_id):
        return self.streams.get(campaign_id, [])

    def update_stream_offers(self, stream_id, offers):
        self.puts.append((stream_id, offers))
        return {"id": stream_id, "offers": offers}


@pytest.fixture()
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = factory()
    try:
        yield db
    finally:
        db.close()


def test_create_campaign_builds_two_streams(session):
    fake = FakeKeitaro()
    service = WrapperService(session, fake)
    settings = TrackerSettings(base_url="https://tracker.example", api_key="key")
    session.add(settings)
    session.commit()
    result = service.create_campaign(
        name="Австралия",
        geo="au",
        offer_id=10,
        domain_id=1,
        group_id=2,
        source_id=4,
        settings=settings,
    )
    assert fake.created_campaign["type"] == "position"
    assert fake.created_campaign["domain_id"] == 1
    assert fake.created_campaign["cost_auto"] is True
    assert fake.created_streams[0]["filters"][0]["payload"] == ["AU"]
    assert fake.created_streams[0]["action_payload"] == "https://google.com"
    assert fake.created_streams[1]["type"] == "default"
    assert fake.created_streams[1]["offers"][0]["share"] == 100
    offer_stream = next(stream for stream in result["streams"] if stream["tracks_offers"])
    plain_stream = next(stream for stream in result["streams"] if not stream["tracks_offers"])
    assert plain_stream["offers"] == []
    assert offer_stream["offers"][0]["share"] == 100
    assert offer_stream["is_dirty"] is False


def test_editor_weights_cancel_pin_and_push(session):
    fake = FakeKeitaro()
    fake.streams[5] = [
        {
            "id": 1,
            "name": "Geo AU",
            "type": "regular",
            "schema": "redirect",
            "position": 1,
            "offers": [],
        },
        {
            "id": 2,
            "name": "Offers",
            "type": "default",
            "schema": "landings",
            "position": 2,
            "offers": [
                {"offer_id": 10, "share": 50, "state": "active"},
                {"offer_id": 11, "share": 50, "state": "active"},
            ],
        },
    ]
    service = WrapperService(session, fake)
    state = service.fetch(5)
    plain = next(stream for stream in state["streams"] if stream["name"] == "Geo AU")
    offers = next(stream for stream in state["streams"] if stream["tracks_offers"])
    with pytest.raises(ValueError):
        service.add_offer(plain["id"], 12)

    state = service.add_offer(offers["id"], 12)
    offers = next(stream for stream in state["streams"] if stream["tracks_offers"])
    assert offers["is_dirty"] is True
    assert [item["share"] for item in offers["offers"]] == [34, 33, 33]
    assert sum(item["share"] for item in offers["offers"]) == 100

    state = service.cancel(offers["id"])
    offers = next(stream for stream in state["streams"] if stream["tracks_offers"])
    assert offers["is_dirty"] is False
    assert [item["keitaro_offer_id"] for item in offers["offers"]] == [10, 11]
    assert [item["share"] for item in offers["offers"]] == [50, 50]

    state = service.add_offer(offers["id"], 12)
    offers = next(stream for stream in state["streams"] if stream["tracks_offers"])
    pinned = offers["offers"][0]
    state = service.pin_offer(offers["id"], pinned["id"], True, pinned["share"])
    offers = next(stream for stream in state["streams"] if stream["tracks_offers"])
    state = service.add_offer(offers["id"], 13)
    offers = next(stream for stream in state["streams"] if stream["tracks_offers"])
    by_id = {item["keitaro_offer_id"]: item for item in offers["offers"]}
    assert by_id[10]["share"] == 34
    assert by_id[10]["pinned"] is True
    assert by_id[11]["share"] == by_id[12]["share"] == by_id[13]["share"] == 22
    assert sum(item["share"] for item in offers["offers"]) == 100

    removed = by_id[11]
    state = service.remove_offer(offers["id"], removed["id"])
    offers = next(stream for stream in state["streams"] if stream["tracks_offers"])
    removed = next(item for item in offers["offers"] if item["keitaro_offer_id"] == 11)
    assert removed["status"] == "removed"
    assert removed["share"] == 0
    active = [item for item in offers["offers"] if item["status"] == "active"]
    assert sum(item["share"] for item in active) == 100
    assert next(item["share"] for item in active if item["keitaro_offer_id"] == 10) == 34

    state = service.push(offers["id"])
    offers = next(stream for stream in state["streams"] if stream["tracks_offers"])
    assert offers["is_dirty"] is False
    sent_ids = [item["offer_id"] for item in fake.puts[-1][1]]
    assert 11 not in sent_ids
    assert sum(item["share"] for item in fake.puts[-1][1]) == 100

    state = service.restore_offer(offers["id"], removed["id"])
    offers = next(stream for stream in state["streams"] if stream["tracks_offers"])
    assert offers["is_dirty"] is True
    restored = next(item for item in offers["offers"] if item["keitaro_offer_id"] == 11)
    assert restored["status"] == "active"
    assert sum(item["share"] for item in offers["offers"] if item["status"] == "active") == 100


def test_fetch_marks_missing_offers_removed(session):
    fake = FakeKeitaro()
    fake.streams[5] = [
        {
            "id": 2,
            "name": "Offers",
            "type": "default",
            "schema": "landings",
            "position": 1,
            "offers": [
                {"offer_id": 10, "share": 50, "state": "active"},
                {"offer_id": 11, "share": 50, "state": "active"},
            ],
        }
    ]
    service = WrapperService(session, fake)
    service.fetch(5)
    fake.streams[5][0]["offers"] = [{"offer_id": 10, "share": 100, "state": "active"}]
    state = service.fetch(5)
    offers = state["streams"][0]["offers"]
    removed = next(item for item in offers if item["keitaro_offer_id"] == 11)
    assert removed["status"] == "removed"
    assert removed["share"] == 0
    assert state["streams"][0]["is_dirty"] is False
    kept = next(item for item in offers if item["keitaro_offer_id"] == 10)
    assert kept["share"] == 100
