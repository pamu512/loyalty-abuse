from loyalty_abuse.schema import (
    SCHEMA_VERSION,
    POLICY_VERSION,
    Decision,
    EventEnvelope,
    EventType,
    FrictionAction,
    TypologyResult,
)

__all__ = [
    "SCHEMA_VERSION",
    "POLICY_VERSION",
    "Decision",
    "EventEnvelope",
    "EventType",
    "FrictionAction",
    "TypologyResult",
    "evaluate",
]

def __getattr__(name: str):
    if name == "evaluate":
        from loyalty_abuse.score import evaluate
        return evaluate
    raise AttributeError(name)
