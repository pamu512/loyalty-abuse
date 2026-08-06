from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import datetime, timezone
from typing import Iterable

from loyalty_abuse.schema import EventEnvelope, EventType

# Weak attrs (email_domain, promo_code) only link when rare enough.
# Strong attrs (device, phone, pay) always link.
RARE_MAX = 5
_WEAK_ATTRS = frozenset({"email_domain", "promo_code"})


def _parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)


def _email_domain(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    return email.lower().rsplit("@", 1)[-1] or None


def _promo_codes(payload: dict) -> Iterable[str]:
    codes = payload.get("promo_codes") or []
    for c in codes:
        if c is not None and str(c) != "":
            yield str(c)
    single = payload.get("promo_code")
    if single is not None and str(single) != "":
        yield str(single)
    ref = payload.get("referral_code")
    if ref is not None and str(ref) != "":
        yield str(ref)


def _attr_keys(e: EventEnvelope) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    if e.device_id:
        out.append(("device", e.device_id))
    if e.phone:
        out.append(("phone", e.phone))
    if e.payment_instrument_hash:
        out.append(("pay", e.payment_instrument_hash))
    dom = _email_domain(e.email)
    if dom:
        out.append(("email_domain", dom))
    for code in _promo_codes(e.payload):
        out.append(("promo_code", code))
    return out


def cluster_features(
    events: list[EventEnvelope], account_id: str, now: datetime
) -> dict[str, float]:
    """Build tenant account graph from events ≤ now; return cluster snapshot keys."""
    now = now.astimezone(timezone.utc) if now.tzinfo else now.replace(tzinfo=timezone.utc)
    # attr → accounts; account first-seen / signup for ages
    attr_accounts: dict[tuple[str, str], set[str]] = defaultdict(set)
    first_seen: dict[str, datetime] = {}
    signup_ts: dict[str, datetime] = {}

    for e in events:
        et = _parse_ts(e.ts)
        if et > now:
            continue
        aid = e.account_id
        if aid not in first_seen or et < first_seen[aid]:
            first_seen[aid] = et
        if e.type == EventType.signup:
            if aid not in signup_ts or et < signup_ts[aid]:
                signup_ts[aid] = et
        for key in _attr_keys(e):
            attr_accounts[key].add(aid)

    if account_id not in first_seen:
        return {
            "graph_cluster_size": 0.0,
            "graph_multi_hop_accounts": 0.0,
            "graph_age_diversity_hours": 0.0,
            "graph_shared_attr_rarity": 0.0,
            "graph_cluster_similarity": 0.0,
            "graph_ring_density": 0.0,
        }

    # account–account adjacency via shared attrs (attrs with ≥2 accounts).
    # Weak attrs only link when accounts_sharing_attr <= RARE_MAX (1/n rarity gate).
    adj: dict[str, set[str]] = defaultdict(set)
    linking_attrs: list[tuple[str, str]] = []
    for key, accts in attr_accounts.items():
        n = len(accts)
        if n < 2:
            continue
        kind = key[0]
        if kind in _WEAK_ATTRS and n > RARE_MAX:
            continue
        linking_attrs.append(key)
        alist = list(accts)
        for i, a in enumerate(alist):
            for b in alist[i + 1 :]:
                adj[a].add(b)
                adj[b].add(a)

    # connected component (BFS)
    cluster: set[str] = {account_id}
    queue = [account_id]
    while queue:
        cur = queue.pop()
        for nb in adj.get(cur, ()):
            if nb not in cluster:
                cluster.add(nb)
                queue.append(nb)

    # accounts within 2 hops (include self)
    hop0 = {account_id}
    hop1 = set(adj.get(account_id, ()))
    hop2: set[str] = set()
    for a in hop1:
        hop2 |= adj.get(a, set())
    multi_hop = hop0 | hop1 | hop2

    # age diversity: stdev of account ages (hours) in cluster; 0 if size < 2
    ages: list[float] = []
    for a in cluster:
        birth = signup_ts.get(a) or first_seen.get(a)
        if birth is None:
            continue
        ages.append((now - birth).total_seconds() / 3600.0)
    if len(ages) < 2:
        age_div = 0.0
    else:
        age_div = float(statistics.pstdev(ages))

    # min rarity of linking attrs that touch the cluster: 1/n_accounts_sharing_attr
    rarities: list[float] = []
    for key in linking_attrs:
        accts = attr_accounts[key]
        if not (accts & cluster):
            continue
        n = len(accts)
        if n >= 2:
            rarities.append(1.0 / float(n))
    rarity = min(rarities) if rarities else 0.0

    # Jaccard-like similarity: shared strong attrs vs union of attrs touching cluster.
    strong_kinds = {"device", "phone", "pay"}
    acct_attrs: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for key, accts in attr_accounts.items():
        for a in accts:
            if a in cluster:
                acct_attrs[a].add(key)
    seed_attrs = acct_attrs.get(account_id, set())
    sim_scores: list[float] = []
    for a in cluster:
        if a == account_id:
            continue
        other = acct_attrs.get(a, set())
        if not seed_attrs and not other:
            continue
        inter = seed_attrs & other
        union = seed_attrs | other
        # Weight strong attr overlap higher.
        strong_inter = sum(1 for k in inter if k[0] in strong_kinds)
        j = len(inter) / max(len(union), 1)
        sim_scores.append(min(1.0, j + 0.15 * strong_inter))
    similarity = max(sim_scores) if sim_scores else 0.0

    # Ring density: edges / possible pairs in cluster.
    n = len(cluster)
    edge_count = sum(len(adj.get(a, ())) for a in cluster) // 2
    possible = n * (n - 1) / 2.0 if n >= 2 else 0.0
    density = (edge_count / possible) if possible else 0.0

    return {
        "graph_cluster_size": float(len(cluster)),
        "graph_multi_hop_accounts": float(len(multi_hop)),
        "graph_age_diversity_hours": age_div,
        "graph_shared_attr_rarity": rarity,
        "graph_cluster_similarity": float(similarity),
        "graph_ring_density": float(density),
    }
