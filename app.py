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

sessions: dict[str, list] = {}

SYSTEM_PROMPT = """Eres un asistente inteligente conectado a un Amazon Echo Dot.
Responde siempre en español, de forma clara y concisa.
Tus respuestas deben ser cortas (máximo 3 oraciones) para que Alexa las lea cómodamente.
Si te preguntan sobre eventos actuales, noticias, partidos o clima, busca en internet.
Sé amigable y directo."""

# ── Health check ───────────────────────────────────────────────────────────────
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

    if request_type == "LaunchRequest":
        sessions[session_id] = []
        return _alexa_response(
            speech="Hola, soy tu asistente con Chat GPT. ¿En qué te puedo ayudar?",
            reprompt="Puedes preguntarme lo que quieras.",
            should_end=False
        )

    elif request_type == "IntentRequest":
        intent_name = body["request"]["intent"]["name"]

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

        elif intent_name in ("AMAZON.CancelIntent", "AMAZON.StopIntent"):
            sessions.pop(session_id, None)
            return _alexa_response(
                speech="¡Hasta luego! Fue un placer ayudarte.",
                should_end=True
            )

        elif intent_name == "AMAZON.HelpIntent":
            return _alexa_response(
                speech="Puedes preguntarme cualquier cosa, incluso noticias o partidos de hoy. Di por ejemplo: dime qué partidos hay hoy.",
                reprompt="¿Qué quieres saber?",
                should_end=False
            )

        else:
            return _alexa_response(
                speech="No entendí ese comando. Intenta preguntarme algo.",
                reprompt="¿Qué quieres saber?",
                should_end=False
            )

    elif request_type == "SessionEndedRequest":
        sessions.pop(session_id, None)
        return jsonify({})

    return _alexa_error("Tipo de solicitud no reconocido.")


# ── Helpers ───────────────────────────────────────────────────────────────────
def _ask_gpt(session_id: str, user_message: str) -> str:
    if session_id not in sessions:
        sessions[session_id] = []

    sessions[session_id].append({"role": "user", "content": user_message})
    history = sessions[session_id][-10:]

    try:
        # Intentar con web search (gpt-4o con búsqueda en tiempo real)
        response = client.responses.create(
            model="gpt-4o",
            tools=[{"type": "web_search_preview"}],
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                *history
            ]
        )
        reply = response.output_text.strip()

    except Exception as e:
        logger.warning(f"Web search falló, usando chat normal: {e}")
        try:
            # Fallback: gpt-4o sin web search
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    *history
                ],
                max_tokens=300,
                temperature=0.7
            )
            reply = response.choices[0].message.content.strip()
        except Exception as e2:
            logger.error(f"Error OpenAI: {e2}")
            return "Lo siento, hubo un problema al consultar a Chat GPT. Por favor intenta de nuevo."

    sessions[session_id].append({"role": "assistant", "content": reply})
    logger.info(f"GPT reply: {reply}")
    return reply


def _alexa_response(speech: str, reprompt: str = None, should_end: bool = True):
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

