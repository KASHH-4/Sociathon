"""Audit log blueprint."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..db import get_repo

bp = Blueprint("audit", __name__)


@bp.route("/api/audit/log", methods=["GET"])
def audit_log():
    limit = min(int(request.args.get("limit", 50)), 200)
    repo = get_repo()
    rows = repo.list_audit_log(limit=limit)
    return jsonify({"log": rows, "count": len(rows)})


@bp.route("/api/audit/summary", methods=["GET"])
def audit_summary():
    repo = get_repo()
    rows = repo.list_audit_log(limit=500)

    if not rows:
        return jsonify({
            "total": 0,
            "by_decision": {},
            "mean_confidence": None,
            "pct_fuzzy_matched": None,
            "pct_deduped": None,
            "pct_degraded": None,
        })

    total = len(rows)
    by_decision: dict[str, int] = {}
    for row in rows:
        d = row.get("decision", "unknown")
        by_decision[d] = by_decision.get(d, 0) + 1

    # Pull matching announcements for richer stats
    ann_rows = []
    try:
        # MemoryRepo stores announcements internally; just iterate via audit link
        ann_ids = [r.get("announcement_id") for r in rows if r.get("announcement_id")]
        for ann_id in ann_ids:
            ann = repo.get_announcement(ann_id)
            if ann:
                ann_rows.append(ann)
    except Exception:
        pass

    confidences = [a.get("confidence_final") for a in ann_rows if a.get("confidence_final") is not None]
    mean_conf = round(sum(confidences) / len(confidences), 3) if confidences else None

    fuzzy_methods = {"fuzzy_corroborated", "fuzzy_uncorroborated", "ambiguous", "name_only"}
    fuzzy = sum(
        1 for a in ann_rows
        if isinstance(a.get("resolution"), dict)
        and a["resolution"].get("method") in fuzzy_methods
    )
    deduped = sum(1 for r in rows if "R6" in (r.get("rules_fired") or []))
    degraded = sum(
        1 for a in ann_rows
        if isinstance(a.get("extracted"), dict) and a["extracted"].get("degraded")
    )

    n = len(ann_rows) if ann_rows else total

    return jsonify({
        "total": total,
        "by_decision": by_decision,
        "mean_confidence": mean_conf,
        "pct_fuzzy_matched": round(100 * fuzzy / n, 1) if n else None,
        "pct_deduped": round(100 * deduped / total, 1) if total else None,
        "pct_degraded": round(100 * degraded / n, 1) if n else None,
    })
