"""Communication blueprint."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..extract_gemini import translate_phrases

bp = Blueprint("comm", __name__)

_DEFAULT_PHRASES = [
    {"category": "assistance", "text": "I am Deaf / Hard of Hearing. Please communicate by writing or pointing."},
    {"category": "transit", "text": "Which platform does my train arrive at?"},
    {"category": "transit", "text": "Has my train been delayed or cancelled?"},
    {"category": "emergency", "text": "I need step-free access assistance to the exit."},
    {"category": "tickets", "text": "Can you check my digital ticket QR code?"},
    {"category": "assistance", "text": "Please write it down for me."},
    {"category": "transit", "text": "Where is the next train to Pune?"},
    {"category": "safety", "text": "Where is the emergency exit?"},
]


@bp.route("/api/communication/phrases", methods=["GET"])
def get_phrases():
    lang = request.args.get("lang", "en-IN")
    phrases = _DEFAULT_PHRASES

    if lang and lang != "en-IN":
        texts = [p["text"] for p in phrases]
        translated = translate_phrases(texts, lang)
        phrases = [
            {**p, "text": t, "original": p["text"]}
            for p, t in zip(phrases, translated)
        ]

    return jsonify({"phrases": phrases, "lang": lang})


@bp.route("/api/communication/translate", methods=["POST"])
def translate():
    data = request.get_json(silent=True) or {}
    text = data.get("text", "").strip()
    target_lang = data.get("target_lang", "hi-IN").strip()
    if not text:
        return jsonify({"error": "text is required"}), 400

    translated = translate_phrases([text], target_lang)
    return jsonify({
        "original": text,
        "translated": translated[0] if translated else text,
        "target_lang": target_lang,
        "degraded": translated[0] == text,
    })
