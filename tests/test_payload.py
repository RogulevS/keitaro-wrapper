import pytest

from app.keitaro_payload import (
    campaign_body,
    geo_stream_body,
    offer_stream_body,
    parse_countries,
    pick_country_filter,
    pick_redirect_action,
    prefer_item,
)


def test_countries_accept_several_separators():
    assert parse_countries(" mx, au ;ro ") == ["MX", "AU", "RO"]


def test_countries_reject_garbage():
    with pytest.raises(ValueError):
        parse_countries("Australia")


def test_filter_and_action_pickers():
    assert pick_country_filter([{"value": "ip"}, {"value": "country"}]) == "country"
    assert pick_country_filter([]) == "country"
    assert pick_redirect_action([{"key": "curl"}, {"key": "http"}]) == "http"


def test_prefer_fortests_when_nothing_is_saved():
    chosen = prefer_item([{"id": 1, "name": "Other"}, {"id": 2, "name": "FORTESTS"}], None)
    assert chosen["id"] == 2


def test_campaign_and_streams_match_the_brief():
    campaign = campaign_body(name="AU test", alias="au-test", domain_id=1, group_id=2, source_id=3)
    assert campaign["type"] == "position"
    assert campaign["cost_type"] == "CPC"
    assert campaign["cost_auto"] is True
    assert campaign["domain_id"] == 1
    assert campaign["group_id"] == 2
    assert campaign["traffic_source_id"] == 3

    geo = geo_stream_body(campaign_id=9, countries=["AU"], filter_name="country", action_type="http")
    assert geo["type"] == "regular"
    assert geo["schema"] == "redirect"
    assert geo["action_payload"] == "https://google.com"
    assert geo["filters"] == [{"name": "country", "mode": "accept", "payload": ["AU"]}]

    offers = offer_stream_body(campaign_id=9, offer_id=3749, action_type="http")
    assert offers["type"] == "default"
    assert offers["offers"] == [{"offer_id": 3749, "share": 100, "state": "active"}]
