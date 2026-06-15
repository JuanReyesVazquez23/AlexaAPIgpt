import os
import json
import logging
from flask import Flask, request, jsonify
from openai import OpenAI

# ── Configuración ─────────────────────────────────────────────────────────────
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# Historial de conversación por sesión (en memoria)
# Para producción considera Redis o PostgreSQL
sessions: dict[str, list] = {}

SYSTEM_PROMPT = """Eres un asistente inteligente conectado a un Amazon Echo Dot.
Responde siempre en español, de forma clara y precisa.
Tus respuestas deben responder a la pregunta de forma amplia pero sin extenderte tanto para que Alexa las lea cómodamente.
Sé amigable y directo."""

# ── Health check ──────────────────────────────────────────────────────────────
@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "online", "service": "Alexa-GPT Bridge"})

# ── Endpoint principal que Alexa llama ────────────────────────────────────────
@app.route("/alexa", methods=["POST"])
def alexa_webhook():
    body = request.get_json(silent=True)

    if not body:
        return _alexa_error("No recibí ningún dato.")

    request_type = body.get("request", {}).get("type", "")
    session_id   = body.get("session", {}).get("sessionId", "default")

    logger.info(f"Request type: {request_type} | Session: {session_id}")

    # ── LaunchRequest: usuario abre el skill ──────────────────────────────────
    if request_type == "LaunchRequest":
        sessions[session_id] = []   # nueva sesión limpia
        return _alexa_response(
            speech="Hola, soy Chat GPT. ¿En qué te puedo ayudar?",
            reprompt="Puedes preguntarme lo que quieras.",
            should_end=False
        )

    # ── IntentRequest ─────────────────────────────────────────────────────────
    elif request_type == "IntentRequest":
        intent_name = body["request"]["intent"]["name"]

        # Intent de pregunta libre
        if intent_name == "PreguntarIntent":
            slots = body["request"]["intent"].get("slots", {})
            user_query = slots.get("pregunta", {}).get("value", "")

            if not user_query:
                return _alexa_response(
                    speech="No entendí tu pregunta. ¿Puedes repetirla?",
                    reprompt="¿Qué quieres saber?",
                    should_end=False
                )

            gpt_reply = _ask_gpt(session_id, user_query)
            return _alexa_response(
                speech=gpt_reply,
                reprompt="¿Tienes alguna otra pregunta?",
                should_end=False
            )

        # Intents estándar de Alexa
        elif intent_name in ("AMAZON.CancelIntent", "AMAZON.StopIntent"):
            sessions.pop(session_id, None)
            return _alexa_response(
                speech="¡Hasta luego! Fue un placer ayudarte.",
                should_end=True
            )

        elif intent_name == "AMAZON.HelpIntent":
            return _alexa_response(
                speech="Puedes preguntarme cualquier cosa. Por ejemplo: pregunta ¿cuál es la capital de Francia?",
                reprompt="¿Qué quieres saber?",
                should_end=False
            )

        else:
            return _alexa_response(
                speech="No entendí ese comando. Intenta preguntarme algo.",
                reprompt="¿Qué quieres saber?",
                should_end=False
            )

    # ── SessionEndedRequest ───────────────────────────────────────────────────
    elif request_type == "SessionEndedRequest":
        sessions.pop(session_id, None)
        return jsonify({})  # Alexa no espera respuesta aquí

    return _alexa_error("Tipo de solicitud no reconocido.")


# ── Helpers ───────────────────────────────────────────────────────────────────
def _ask_gpt(session_id: str, user_message: str) -> str:
    """Envía el mensaje a GPT manteniendo historial de la sesión."""
    if session_id not in sessions:
        sessions[session_id] = []

    # Agregar mensaje del usuario al historial
    sessions[session_id].append({"role": "user", "content": user_message})

    # Limitar historial a las últimas 10 interacciones para no exceder tokens
    history = sessions[session_id][-10:]

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",   # económico y rápido; cambia a gpt-4o si prefieres
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                *history
            ],
            max_tokens=200,
            temperature=0.7
        )
        reply = response.choices[0].message.content.strip()

        # Guardar respuesta en historial
        sessions[session_id].append({"role": "assistant", "content": reply})
        logger.info(f"GPT reply: {reply}")
        return reply

    except Exception as e:
        logger.error(f"Error OpenAI: {e}")
        return "Lo siento, hubo un problema al consultar a Chat GPT. Por favor intenta de nuevo."


def _alexa_response(speech: str, reprompt: str = None, should_end: bool = True) -> dict:
    """Construye la respuesta en formato que Alexa entiende."""
    response = {
        "version": "1.0",
        "response": {
            "outputSpeech": {
                "type": "PlainText",
                "text": speech
            },
            "shouldEndSession": should_end
        }
    }

    if reprompt and not should_end:
        response["response"]["reprompt"] = {
            "outputSpeech": {
                "type": "PlainText",
                "text": reprompt
            }
        }

    return jsonify(response)


def _alexa_error(message: str):
    return _alexa_response(f"Error: {message}", should_end=True)


# ── Entrypoint ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
