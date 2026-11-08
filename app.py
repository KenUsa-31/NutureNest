"""Flask app for the NurtureNest maternity companion."""

import json
import os

try:
    from dotenv import load_dotenv
except ImportError:  # dotenv is optional on Vercel
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv()

from flask import Flask, Response, current_app, jsonify, render_template, request, stream_with_context

from backend import CompanionBackend, KnowledgeBase, MEMORY_SIZE

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024
knowledge_base = KnowledgeBase()


def validate_history(value):
    if not isinstance(value, list) or len(value) > MEMORY_SIZE:
        raise ValueError("Conversation history is invalid. Start a new chat and try again.")

    history = []
    for message in value:
        if not isinstance(message, dict):
            raise ValueError("Conversation history is invalid. Start a new chat and try again.")
        role = message.get("role")
        content = message.get("content")
        if role not in {"user", "assistant"}:
            raise ValueError("Conversation history is invalid. Start a new chat and try again.")
        if not isinstance(content, str) or not content.strip() or len(content) > 2000:
            raise ValueError("Conversation history is invalid. Start a new chat and try again.")
        history.append({"role": role, "content": content.strip()})
    return history


@app.after_request
def add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; style-src 'self' https://fonts.googleapis.com; script-src 'self'; "
        "connect-src 'self'; img-src 'self' data:; font-src 'self' https://fonts.gstatic.com; "
        "base-uri 'self'; form-action 'self'; frame-ancestors 'none'",
    )
    return response


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/chat")
def chat():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="Send a message as JSON."), 400

    message = payload.get("message")
    if not isinstance(message, str) or not message.strip():
        return jsonify(error="Type a message first."), 400
    message = message.strip()
    if len(message) > 2000:
        return jsonify(error="Messages can be up to 2,000 characters."), 400

    try:
        history = validate_history(payload.get("history", []))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400

    companion = CompanionBackend(knowledge_base=knowledge_base, history=history)

    def event(data):
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

    def generate():
        try:
            with companion.lock:
                for piece in companion.stream_response(message):
                    yield event({"token": piece})
                metadata = companion.last_metadata
            yield event({
                "done": True,
                "topics": metadata.get("topics", []),
                "sources": metadata.get("sources", []),
                "emergency": metadata.get("emergency", False),
            })
        except GeneratorExit:
            raise
        except Exception:
            current_app.logger.exception("NurtureNest response failed")
            yield event({"error": "I couldn't finish that reply. Please try again."})

    response = Response(stream_with_context(generate()), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    return response


@app.post("/api/clear")
def clear_chat():
    return jsonify(ok=True)


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=int(os.environ.get("PORT", "5000")),
        debug=False,
        threaded=True,
    )
