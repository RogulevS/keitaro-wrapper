from app.weights import WeightError, WeightOffer, distribute
import pytest


def offer(key, status="active", share=0, pinned=False, order=0):
    return WeightOffer(key, status, share, pinned, order)


def test_one_offer_takes_everything():
    rows = [offer("a")]
    distribute(rows)
    assert rows[0].share == 100


def test_three_offers_sum_to_100():
    rows = [offer("a", order=0), offer("b", order=1), offer("c", order=2)]
    distribute(rows)
    assert [row.share for row in rows] == [34, 33, 33]
    assert sum(row.share for row in rows) == 100


def test_four_offers_are_equal():
    rows = [offer(str(index), order=index) for index in range(4)]
    distribute(rows)
    assert [row.share for row in rows] == [25, 25, 25, 25]


def test_removed_offer_is_zero_and_ignored():
    rows = [offer("a"), offer("b", status="removed", share=40), offer("c")]
    distribute(rows)
    assert rows[1].share == 0
    assert rows[0].share + rows[2].share == 100


def test_pin_stays_while_the_rest_split():
    rows = [
        offer("pinned", share=25, pinned=True, order=0),
        offer("b", order=1),
        offer("c", order=2),
    ]
    distribute(rows)
    assert [row.share for row in rows] == [25, 38, 37]


def test_pin_over_100_is_rejected():
    rows = [offer("a", share=60, pinned=True), offer("b", share=50, pinned=True)]
    with pytest.raises(WeightError):
        distribute(rows)


def test_every_count_sums_to_100():
    for count in range(1, 15):
        rows = [offer(str(index), order=index) for index in range(count)]
        distribute(rows)
        assert sum(row.share for row in rows) == 100
