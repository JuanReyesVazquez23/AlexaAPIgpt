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
Máximo 2 oraciones cortas. Sin listas. Solo texto hablado natural.
Si no sabes algo reciente, dilo en una frase."""

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

    if request_type == "LaunchRequest":
        sessions[session_id] = []
        return jsonify(_build_response(
            speech="¿En qué te puedo ayudar?",
            reprompt="Pregúntame lo que quieras.",
            should_end=False
        ))

    elif request_type == "IntentRequest":
        intent_name = body["request"]["intent"]["name"]

        if intent_name == "PreguntarIntent":
            slots = body["request"]["intent"].get("slots", {})
            user_query = slots.get("pregunta", {}).get("value", "")

            if not user_query:
                return jsonify(_build_response(
                    speech="No entendí. ¿Puedes repetir?",
                    reprompt="¿Qué quieres saber?",
                    should_end=False
                ))

            logger.info(f"Query: {user_query}")
            gpt_reply = _ask_gpt(session_id, user_query)
            logger.info(f"Reply: {gpt_reply}")
            return jsonify(_build_response(
                speech=gpt_reply,
                reprompt="¿Algo más?",
                should_end=False
            ))

        elif intent_name in ("AMAZON.CancelIntent", "AMAZON.StopIntent"):
            sessions.pop(session_id, None)
            return jsonify(_build_response("¡Hasta luego!", should_end=True))

        elif intent_name == "AMAZON.HelpIntent":
            return jsonify(_build_response(
                speech="Pregúntame lo que quieras.",
                reprompt="¿Qué quieres saber?",
                should_end=False
            ))

        else:
            return jsonify(_build_response(
                speech="No entendí. Intenta de nuevo.",
                reprompt="¿Qué quieres saber?",
                should_end=False
            ))

    elif request_type == "SessionEndedRequest":
        sessions.pop(session_id, None)
        return jsonify({})

    return jsonify(_build_response("Solicitud no reconocida.", should_end=True))


def _ask_gpt(session_id: str, user_message: str) -> str:
    if session_id not in sessions:
        sessions[session_id] = []

    sessions[session_id].append({"role": "user", "content": user_message})
    history = sessions[session_id][-4:]

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                *history
            ],
            max_tokens=100,
            temperature=0.5
        )
        reply = response.choices[0].message.content.strip()
        sessions[session_id].append({"role": "assistant", "content": reply})
        return reply

    except Exception as e:
        logger.error(f"Error OpenAI: {e}")
        return "Hubo un error. Intenta de nuevo."


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


