from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

SCHEMA_VERSION = 1
POLICY_VERSION = "friction_v1_2"


class FrictionAction(str, Enum):
    allow = "allow"
    throttle = "throttle"
    soft_challenge = "soft_challenge"
    hard_challenge = "hard_challenge"
    block = "block"


class EventType(str, Enum):
    signup = "signup"
    login = "login"
    profile_update = "profile_update"
    referral = "referral"
    offer_enroll = "offer_enroll"
    redeem = "redeem"
    checkout = "checkout"


class EventEnvelope(BaseModel):
    event_id: str
    tenant_id: str
    ts: str
    type: EventType
    account_id: str
    session_id: str
    device_id: str
    ip: str
    email: str | None = None
    phone: str | None = None
    payment_instrument_hash: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class TypologyResult(BaseModel):
    id: str
    points: int
    confidence: float = 0.0
    reasons: list[str] = Field(default_factory=list)


class Decision(BaseModel):
    decision_id: str
    event_id: str
    score: int
    friction: FrictionAction
    reasons: list[str]
    typology_breakdown: list[TypologyResult]
    features_snapshot: dict[str, Any]
    policy_version: str = POLICY_VERSION
    schema_version: int = SCHEMA_VERSION
