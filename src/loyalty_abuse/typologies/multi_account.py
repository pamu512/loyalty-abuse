from __future__ import annotations

from typing import Any

from loyalty_abuse.calibration import load_calibration, sat_params
from loyalty_abuse.mathutil import sat, soft_or
from loyalty_abuse.schema import TypologyResult
from loyalty_abuse.typologies._contrib import result


def score(snapshot: dict[str, Any]) -> TypologyResult:
    cal = load_calibration()
    # Correlated windows on the same account set → max (not soft_or).
    c_dev = max(
        sat(float(snapshot.get("accounts_on_device_1h") or 0), *sat_params("accounts_on_device_1h")),
        sat(float(snapshot.get("accounts_on_device_24h") or 0), *sat_params("accounts_on_device_24h")),
        sat(float(snapshot.get("accounts_on_device_7d") or 0), *sat_params("accounts_on_device_7d")),
    )
    c_ip = max(
        sat(float(snapshot.get("accounts_on_ip_1h") or 0), *sat_params("accounts_on_ip_1h")),
        sat(float(snapshot.get("accounts_on_ip_24h") or 0), *sat_params("accounts_on_ip_24h")),
        sat(float(snapshot.get("accounts_on_ip_7d") or 0), *sat_params("accounts_on_ip_7d")),
    )
    c_email = (
        float(cal.get("email_burst_confidence") or 0.75) if snapshot.get("email_alias_burst") else 0.0
    )
    c_graph_size = sat(
        float(snapshot.get("graph_cluster_size") or 0), *sat_params("graph_cluster_size")
    )
    c_graph_hop = sat(
        float(snapshot.get("graph_multi_hop_accounts") or 0),
        *sat_params("graph_cluster_size"),
    )
    rarity = float(snapshot.get("graph_shared_attr_rarity") or 0.0)
    # Rarity in [0,1]: high rarity (rare shared attr) strengthens graph channel.
    c_graph_rare = max(0.0, min(1.0, rarity)) if rarity > 0 else 0.0
    cluster_n = float(snapshot.get("graph_cluster_size") or 0)
    # Similarity/density are syndicate signals — do not fire on small household clusters.
    if cluster_n >= 5:
        c_sim = sat(
            float(snapshot.get("graph_cluster_similarity") or 0),
            *sat_params("graph_cluster_similarity"),
        )
        c_density = max(0.0, min(1.0, float(snapshot.get("graph_ring_density") or 0.0)))
    else:
        c_sim = 0.0
        c_density = 0.0
    c_graph = soft_or([c_graph_size, c_graph_hop * 0.85, c_graph_rare * 0.6, c_sim, c_density * 0.5])
    # Independent evidence families may soft_or.
    young = float(cal.get("young_account_minutes") or 60)
    young_hit = float(snapshot.get("account_age_minutes") or 0) < young and int(
        snapshot.get("accounts_on_device_24h") or 0
    ) >= 2
    # Apply young mult per-channel before outer combine (not after saturation).
    mult = float(cal.get("young_multi_mult") or 1.1) if young_hit else 1.0
    c_dev = min(1.0, c_dev * mult)
    c_ip = min(1.0, c_ip * mult)
    c = soft_or([c_dev, c_ip, c_email, c_graph])
    reasons: list[str] = []
    if c_dev > 0:
        reasons.append("multi_acct.shared_device_cluster")
    if c_ip > 0 and c_ip >= c_dev:
        reasons.append("multi_acct.shared_ip_cluster")
    if c_email > 0:
        reasons.append("multi_acct.email_alias_burst")
    if c_graph > 0:
        reasons.append("multi_acct.graph_cluster")
    return result("multi_account", c, reasons)
