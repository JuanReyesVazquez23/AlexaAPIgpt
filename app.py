import os
import logging
from flask import Flask, request, jsonify
from openai import OpenAI

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

sessions: dict[str, list] = {}

SYSTEM_PROMPT = """Eres un asistente inteligente en un Amazon Echo Dot.
Responde SIEMPRE en español.
Máximo 1 oración corta. Sin listas. Sin bullets. Solo texto hablado natural.
Si no sabes algo reciente, dilo en una frase."""

@app.route("/", methods=["GET"])
def health():
    # Este endpoint también sirve para keep-alive
    return "OK", 200

@app.route("/ping", methods=["GET"])
def ping():
    return "pong", 200

@app.route("/alexa", methods=["POST"])
def alexa_webhook():
    body = request.get_json(silent=True)
    if not body:
        return _alexa_error("Sin datos.")

    request_type = body.get("request", {}).get("type", "")
    session_id   = body.get("session", {}).get("sessionId", "default")

    logger.info(f"Type: {request_type} | Session: {session_id}")

    if request_type == "LaunchRequest":
        sessions[session_id] = []
        return _alexa_response(
            speech="¿En qué te puedo ayudar?",
            reprompt="Pregúntame lo que quieras.",
            should_end=False
        )

    elif request_type == "IntentRequest":
        intent_name = body["request"]["intent"]["name"]

        if intent_name == "PreguntarIntent":
            slots = body["request"]["intent"].get("slots", {})
            user_query = slots.get("pregunta", {}).get("value", "")

            if not user_query:
                return _alexa_response(
                    speech="No entendí. ¿Puedes repetir?",
                    reprompt="¿Qué quieres saber?",
                    should_end=False
                )

            logger.info(f"Query: {user_query}")
            gpt_reply = _ask_gpt(session_id, user_query)
            return _alexa_response(
                speech=gpt_reply,
                reprompt="¿Algo más?",
                should_end=False
            )

        elif intent_name in ("AMAZON.CancelIntent", "AMAZON.StopIntent"):
            sessions.pop(session_id, None)
            return _alexa_response(speech="¡Hasta luego!", should_end=True)

        elif intent_name == "AMAZON.HelpIntent":
            return _alexa_response(
                speech="Pregúntame lo que quieras, por ejemplo: quién es Einstein.",
                reprompt="¿Qué quieres saber?",
                should_end=False
            )

        else:
            return _alexa_response(
                speech="No entendí. Intenta de nuevo.",
                reprompt="¿Qué quieres saber?",
                should_end=False
            )

    elif request_type == "SessionEndedRequest":
        sessions.pop(session_id, None)
        return "", 200

    return _alexa_error("Solicitud no reconocida.")


def _ask_gpt(session_id: str, user_message: str) -> str:
    if session_id not in sessions:
        sessions[session_id] = []

    sessions[session_id].append({"role": "user", "content": user_message})
    history = sessions[session_id][-4:]  # solo últimas 4 = más rápido

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",   # el más rápido disponible
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                *history
            ],
            max_tokens=80,           # respuesta muy corta = más rápido
            temperature=0.5
        )
        reply = response.choices[0].message.content.strip()
        sessions[session_id].append({"role": "assistant", "content": reply})
        logger.info(f"Reply: {reply}")
        return reply

    except Exception as e:
        logger.error(f"Error: {e}")
        return "Hubo un error. Intenta de nuevo."


def _alexa_response(speech: str, reprompt: str = None, should_end: bool = True):
    response = {
        "version": "1.0",
        "response": {
            "outputSpeech": {"type": "PlainText", "text": speech},
            "shouldEndSession": should_end
        }
    }
    if reprompt and not should_end:
        response["response"]["reprompt"] = {
            "outputSpeech": {"type": "PlainText", "text": reprompt}
        }
    return response, 200, {"Content-Type": "application/json"}


def _alexa_error(msg: str):
    return _alexa_response(f"Error: {msg}", should_end=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

