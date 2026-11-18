"""Пересчёт долей офферов.

Активные офферы всегда дают в сумме 100. Закреплённая доля не меняется.
Остаток делится поровну между незакреплёнными. Остаток от деления
получают первые по порядку, чтобы сумма была ровно 100, а не 99.
"""

from __future__ import annotations

from dataclasses import dataclass


class WeightError(ValueError):
    pass


@dataclass
class WeightOffer:
    key: str
    status: str
    share: int
    pinned: bool
    sort_order: int


def distribute(offers: list[WeightOffer]) -> None:
    removed = [offer for offer in offers if offer.status != "active"]
    active = [offer for offer in offers if offer.status == "active"]
    active.sort(key=lambda offer: (offer.sort_order, offer.key))
    for offer in removed:
        offer.share = 0
    if not active:
        return

    pinned = [offer for offer in active if offer.pinned]
    unpinned = [offer for offer in active if not offer.pinned]
    pinned_sum = sum(offer.share for offer in pinned)
    if pinned_sum > 100:
        raise WeightError("Сумма закреплённых весов больше 100")
    leftover = 100 - pinned_sum
    if not unpinned:
        if leftover != 0:
            raise WeightError(
                "Закреплённые веса не складываются в 100%, а свободных офферов нет"
            )
        return
    base, remainder = divmod(leftover, len(unpinned))
    for index, offer in enumerate(unpinned):
        offer.share = base + (1 if index < remainder else 0)
