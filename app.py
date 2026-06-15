import os
import logging
from flask import Flask, request, jsonify
from openai import OpenAI

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

sessions: dict[str, list] = {}

SYSTEM_PROMPT = """Eres un asistente inteligente integrado en un Amazon Echo Dot, similar a como funciona ChatGPT.
Responde SIEMPRE en español, de forma natural y conversacional, como si estuvieras hablando.
Máximo 3 oraciones. Sin listas, sin bullets, sin markdown. Solo texto hablado fluido.
Si no tienes información reciente sobre algo, dilo brevemente y ofrece lo que sabes."""

@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "online", "service": "Alexa-GPT Bridge"})

@app.route("/ping", methods=["GET"])
def ping():
    return "pong", 200

@app.route("/alexa", methods=["POST"])
def alexa_webhook():
    body = request.get_json(silent=True, force=True)
    if not body:
        return jsonify(_build_response("No recibí datos.", should_end=True))

    request_type = body.get("request", {}).get("type", "")
    session_id   = body.get("session", {}).get("sessionId", "default")

    logger.info(f"Type: {request_type} | Session: {session_id}")

    # ── Apertura del skill ────────────────────────────────────────────────────
    if request_type == "LaunchRequest":
        sessions[session_id] = []
        return jsonify(_build_response(
            speech="Listo, ¿en qué te puedo ayudar?",
            reprompt="Pregúntame lo que quieras.",
            should_end=False
        ))

    # ── Intents ───────────────────────────────────────────────────────────────
    elif request_type == "IntentRequest":
        intent_name = body["request"]["intent"]["name"]
        logger.info(f"Intent: {intent_name}")

        # Pregunta con palabra clave
        if intent_name == "PreguntarIntent":
            slots = body["request"]["intent"].get("slots", {})
            user_query = slots.get("pregunta", {}).get("value", "")
            if not user_query:
                return jsonify(_build_response(
                    speech="No te escuché bien. ¿Puedes repetir?",
                    reprompt="¿Qué quieres saber?",
                    should_end=False
                ))
            return _responder_con_gpt(session_id, user_query)

        # FallbackIntent: captura TODO lo que Alexa no reconoce
        # Aquí es donde llegan las preguntas libres sin palabra clave
        elif intent_name == "AMAZON.FallbackIntent":
            # Intentar extraer el texto de la utterance original
            user_query = (
                body.get("request", {})
                    .get("intent", {})
                    .get("slots", {})
                    .get("pregunta", {})
                    .get("value")
                or body.get("request", {}).get("intent", {}).get("name", "")
            )

            # Si Alexa no nos da el texto, pedimos que repita
            if not user_query or user_query == "AMAZON.FallbackIntent":
                return jsonify(_build_response(
                    speech="No te escuché bien. ¿Puedes repetirlo?",
                    reprompt="¿Qué quieres preguntarme?",
                    should_end=False
                ))

            return _responder_con_gpt(session_id, user_query)

        elif intent_name in ("AMAZON.CancelIntent", "AMAZON.StopIntent"):
            sessions.pop(session_id, None)
            return jsonify(_build_response("¡Hasta luego!", should_end=True))

        elif intent_name == "AMAZON.HelpIntent":
            return jsonify(_build_response(
                speech="Puedes hablarme directamente. Por ejemplo pregúntame: quién ganó la final de la NBA, o cómo se hace una pizza.",
                reprompt="¿Qué quieres saber?",
                should_end=False
            ))

        else:
            return jsonify(_build_response(
                speech="No entendí. Intenta de nuevo.",
                reprompt="¿Qué quieres saber?",
                should_end=False
            ))

    # ── Fin de sesión ─────────────────────────────────────────────────────────
    elif request_type == "SessionEndedRequest":
        sessions.pop(session_id, None)
        return jsonify({})

    return jsonify(_build_response("Solicitud no reconocida.", should_end=True))


# ── GPT ───────────────────────────────────────────────────────────────────────
def _responder_con_gpt(session_id: str, user_query: str):
    logger.info(f"Query: {user_query}")
    reply = _ask_gpt(session_id, user_query)
    logger.info(f"Reply: {reply}")
    return jsonify(_build_response(
        speech=reply,
        reprompt="¿Tienes alguna otra pregunta?",
        should_end=False
    ))


def _ask_gpt(session_id: str, user_message: str) -> str:
    if session_id not in sessions:
        sessions[session_id] = []

    sessions[session_id].append({"role": "user", "content": user_message})
    history = sessions[session_id][-6:]

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                *history
            ],
            max_tokens=120,
            temperature=0.6
        )
        reply = response.choices[0].message.content.strip()
        sessions[session_id].append({"role": "assistant", "content": reply})
        return reply

    except Exception as e:
        logger.error(f"Error OpenAI: {e}")
        return "Hubo un problema al conectar con Chat GPT. Intenta de nuevo."


# ── Formato respuesta Alexa ───────────────────────────────────────────────────
def _build_response(speech: str, reprompt: str = None, should_end: bool = True) -> dict:
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
    return response


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
