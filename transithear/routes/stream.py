"""SSE stream blueprint."""
from __future__ import annotations

from flask import Blueprint, Response, request

from ..events import subscribe

bp = Blueprint("stream", __name__)


@bp.route("/api/stream", methods=["GET"])
def sse_stream():
    device_id = request.args.get("device_id", "").strip()
    if not device_id:
        return Response("device_id required", status=400)

    def generate():
        yield "data: {\"event\":\"connected\"}\n\n"
        yield from subscribe(device_id)

    resp = Response(generate(), mimetype="text/event-stream")
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["X-Accel-Buffering"] = "no"
    resp.headers["Connection"] = "keep-alive"
    return resp
