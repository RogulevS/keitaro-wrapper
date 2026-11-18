from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class TrackerSettings(Base):
    __tablename__ = "tracker_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    base_url: Mapped[str] = mapped_column(String(300), default="")
    api_key: Mapped[str] = mapped_column(String(300), default="")
    domain_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    group_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class LocalCampaign(Base):
    __tablename__ = "local_campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    keitaro_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    alias: Mapped[str] = mapped_column(String(80), default="")
    country_codes: Mapped[str] = mapped_column(String(80), default="")
    domain_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    group_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    streams: Mapped[list[LocalStream]] = relationship(
        back_populates="campaign",
        cascade="all, delete-orphan",
        order_by="LocalStream.position",
    )


class LocalStream(Base):
    __tablename__ = "local_streams"
    __table_args__ = (UniqueConstraint("campaign_id", "keitaro_id", name="uq_stream_remote"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("local_campaigns.id", ondelete="CASCADE"))
    keitaro_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    stream_type: Mapped[str] = mapped_column(String(32), default="")
    schema_name: Mapped[str] = mapped_column(String(32), default="")
    position: Mapped[int] = mapped_column(Integer, default=0)
    tracks_offers: Mapped[bool] = mapped_column(Boolean, default=False)
    is_dirty: Mapped[bool] = mapped_column(Boolean, default=False)

    campaign: Mapped[LocalCampaign] = relationship(back_populates="streams")
    offers: Mapped[list[StreamOffer]] = relationship(
        back_populates="stream",
        cascade="all, delete-orphan",
        order_by="StreamOffer.sort_order",
    )


class StreamOffer(Base):
    __tablename__ = "stream_offers"
    __table_args__ = (UniqueConstraint("stream_id", "keitaro_offer_id", name="uq_stream_offer"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stream_id: Mapped[int] = mapped_column(ForeignKey("local_streams.id", ondelete="CASCADE"))
    keitaro_offer_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(300), default="")
    share: Mapped[int] = mapped_column(Integer, default=0)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16), default="active")
    draft_only: Mapped[bool] = mapped_column(Boolean, default=False)
    published_share: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    published_status: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    published_pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    stream: Mapped[LocalStream] = relationship(back_populates="offers")
