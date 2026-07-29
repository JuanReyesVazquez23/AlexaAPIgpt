import os
import json
import logging
from flask import Flask, request, jsonify
from openai import OpenAI
from dotenv import load_dotenv

# ── Configuración ─────────────────────────────────────────────────────────────
load_dotenv()  # Carga variables desde .env en local. En Vercel no hace nada (no hay .env).

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Skill ID de Alexa (opcional pero recomendado por seguridad).
# Si se configura esta variable de entorno en Vercel, el servidor solo aceptará
# solicitudes que declaren exactamente este applicationId, evitando que cualquiera
# que descubra la URL pueda invocar tu API y consumir tu crédito de OpenAI.
# Se obtiene en developer.amazon.com/alexa/console/ask -> tu skill -> "View Skill ID".
EXPECTED_SKILL_ID = os.environ.get("ALEXA_SKILL_ID")

# Historial de conversación por sesión (en memoria)
# Para producción considera Redis o PostgreSQL


SYSTEM_PROMPT = """Eres un asistente inteligente conectado a un Amazon Echo Dot.
Responde siempre en español, de forma clara y precisa.
Tus respuestas deben responder a la pregunta de forma amplia pero sin extenderte tanto para que Alexa las lea cómodamente.
Sé amigable y directo."""

# ── Cliente de OpenAI (carga diferida) ────────────────────────────────────────
# Antes el cliente se creaba al importar el módulo. Si faltaba OPENAI_API_KEY,
# toda la función fallaba al arrancar (Alexa no recibía ninguna respuesta, ni
# siquiera para "abrir el skill"). Ahora se crea la primera vez que hace falta,
# y si falta la clave devolvemos un mensaje de voz claro en vez de tumbar la función.
_openai_client = None


def _get_openai_client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("La variable de entorno OPENAI_API_KEY no está configurada.")
        _openai_client = OpenAI(api_key=api_key)
    return _openai_client


# ── Rutas ─────────────────────────────────────────────────────────────────────
# Se registran para "/" y para "/<path>" a la vez. Así responde igual sin importar
# si en Alexa configuraste el endpoint como la raíz del dominio o como /api/alexa
# (que es la ruta que Vercel asigna automáticamente a este archivo).

# ── Health check ──────────────────────────────────────────────────────────────
@app.route("/", defaults={"path": ""}, methods=["GET"])
@app.route("/<path:path>", methods=["GET"])
def health(path=""):
    return jsonify({"status": "online", "service": "Alexa-GPT Bridge"})


# ── Endpoint principal que Alexa llama ────────────────────────────────────────
@app.route("/", defaults={"path": ""}, methods=["POST"])
@app.route("/<path:path>", methods=["POST"])
def alexa_webhook(path=""):
    try:
        body = request.get_json(silent=True)

        if not body:
            return _alexa_error("No recibí ningún dato.")

        # Verificación opcional del Skill ID (ver EXPECTED_SKILL_ID más arriba)
        if EXPECTED_SKILL_ID:
            incoming_app_id = (
                body.get("session", {}).get("application", {}).get("applicationId")
                or body.get("context", {}).get("System", {}).get("application", {}).get("applicationId")
            )
            if incoming_app_id != EXPECTED_SKILL_ID:
                logger.warning("Solicitud rechazada: applicationId no coincide con ALEXA_SKILL_ID.")
                return _alexa_error("Solicitud no autorizada.")

        request_type = body.get("request", {}).get("type", "")
        session_id = body.get("session", {}).get("sessionId", "default")

        logger.info(f"Request type: {request_type} | Session: {session_id}")

        # ── LaunchRequest: usuario abre el skill ──────────────────────────────
        if request_type == "LaunchRequest":
            # nueva sesión limpia
            return _alexa_response(
                speech="Hola, soy tu asistente con Chat GPT. ¿En qué te puedo ayudar?",
                reprompt="Puedes preguntarme lo que quieras.",
                should_end=False
            )

        # ── IntentRequest ─────────────────────────────────────────────────────
        elif request_type == "IntentRequest":
            intent_name = body.get("request", {}).get("intent", {}).get("name", "")

            # Intent de pregunta libre
            if intent_name == "PreguntarIntent":
                slots = body.get("request", {}).get("intent", {}).get("slots", {})
                user_query = slots.get("pregunta", {}).get("value", "")

                if not user_query:
                    return _alexa_response(
                        speech="No entendí tu pregunta. ¿Puedes repetirla?",
                        reprompt="¿Qué quieres saber?",
                        should_end=False
                    )

                gpt_reply = _ask_gpt(user_query)
                return _alexa_response(
                    speech=gpt_reply,
                    reprompt="¿Tienes alguna otra pregunta?",
                    should_end=False
                )

            # Intents estándar de Alexa
            elif intent_name in ("AMAZON.CancelIntent", "AMAZON.StopIntent"):
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
                # Incluye AMAZON.FallbackIntent y cualquier intent no reconocido
                return _alexa_response(
                    speech="No entendí ese comando. Intenta preguntarme algo.",
                    reprompt="¿Qué quieres saber?",
                    should_end=False
                )

        # ── SessionEndedRequest ───────────────────────────────────────────────
        elif request_type == "SessionEndedRequest":
            return jsonify({})  # Alexa no espera respuesta aquí

        return _alexa_error("Tipo de solicitud no reconocido.")

    except Exception as e:
        # Cualquier solicitud malformada o error inesperado responde de forma
        # controlada (formato válido para Alexa) en vez de tumbar la función con un 500.
        logger.error(f"Error inesperado procesando la solicitud: {e}")
        return _alexa_error("Ocurrió un error inesperado en el servidor.")


# ── Helpers ───────────────────────────────────────────────────────────────────
def _ask_gpt(user_message: str) -> str:
    """Envía un mensaje a ChatGPT sin guardar historial."""

    try:
        client = _get_openai_client()
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT
                },
                {
                    "role": "user",
                    "content": user_message
                }
            ],
            max_tokens=200,
            temperature=0.7
        )

        reply = response.choices[0].message.content.strip()
        logger.info(f"GPT reply: {reply}")
        return reply

    except RuntimeError as e:
        logger.error(f"Configuración incompleta: {e}")
        return "Falta configurar la clave de OpenAI en el servidor. Avisa al administrador."

    except Exception as e:
        logger.error(f"Error OpenAI: {e}")
        return "Lo siento, hubo un problema al consultar a ChatGPT. Inténtalo nuevamente."


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


# ── Manejador de rutas no encontradas ─────────────────────────────────────────
# Si algo llega a 404 igual devolvemos JSON en vez de la página HTML por
# defecto de Flask, para que sea fácil detectar el problema al probar la URL.
@app.errorhandler(404)
def not_found(_e):
    return jsonify({
        "error": "not_found",
        "message": "Ruta no encontrada. Usa la raíz del dominio para el healthcheck "
                    "o configúrala como endpoint del skill en Alexa Developer Console."
    }), 404


# ── Entrypoint ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
