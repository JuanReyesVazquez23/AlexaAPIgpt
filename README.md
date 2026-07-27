# Alexa + ChatGPT Bridge

Conecta tu Amazon Echo Dot con ChatGPT usando Flask y Railway.

---

## Estructura del proyecto

```
alexa-gpt/
├── app.py                  # Servidor Flask principal
├── requirements.txt
├── Procfile                # Para Railway/Heroku
├── .env.example            # Variables de entorno de ejemplo
├── alexa_skill_model.json  # Modelo del Skill para Alexa Console
└── README.md
```

---

## Paso 1 — Subir a Railway

1. Sube el proyecto a un repo en GitHub
2. En [railway.app](https://railway.app) → New Project → Deploy from GitHub
3. En **Variables** agrega:
   ```
   OPENAI_API_KEY = sk-proj-tu-clave-aqui
   ```
4. Railway te dará una URL pública tipo:
   ```
   https://alexa-gpt-production.up.railway.app
   ```
5. Prueba que funciona:
   ```
   GET https://tu-url.railway.app/
   → {"status": "online", "service": "Alexa-GPT Bridge"}
   ```

---

## Paso 2 — Crear el Alexa Skill

1. Ve a [developer.amazon.com/alexa/console/ask](https://developer.amazon.com/alexa/console/ask)
2. Click **Create Skill**
3. Configura:
   - **Skill name:** Mi Asistente GPT (o el nombre que quieras)
   - **Default language:** Spanish (MX) o Spanish (US)
   - **Model:** Custom
   - **Hosting:** Provision your own
4. Click **Create Skill** → elige template **Start from Scratch**

---

## Paso 3 — Configurar el Interaction Model

1. En el menú izquierdo → **JSON Editor**
2. Borra todo el contenido y pega el contenido de `alexa_skill_model.json`
3. Click **Save Model** → **Build Model** (tarda ~1 min)

> **Invocation name:** `mi asistente`
> Usuario dirá: *"Alexa, abre mi asistente"*

---

## Paso 4 — Configurar el Endpoint

1. En el menú izquierdo → **Endpoint**
2. Selecciona **HTTPS**
3. En **Default Region** pega tu URL de Railway + `/alexa`:
   ```
   https://tu-url.railway.app/alexa
   ```
4. En el dropdown de SSL → **My development endpoint is a sub-domain of a domain that has a wildcard certificate from a certificate authority**
5. Click **Save Endpoints**

---

## Paso 5 — Probar

### En el simulador de Alexa:
1. Ve a **Test** → activa **Development**
2. Escribe o di: `abre mi asistente`
3. Luego pregunta lo que quieras

### En tu Echo Dot real:
1. Di: *"Alexa, abre mi asistente"*
2. Alexa responde: *"Hola, soy tu asistente con Chat GPT..."*
3. Pregunta: *"¿Cuál es la distancia de la Tierra al Sol?"*
4. Alexa habla la respuesta de GPT ✅

---

## Cómo funciona la conversación

```
Tú: "Alexa, abre mi asistente"
Alexa: "Hola, soy tu asistente con Chat GPT. ¿En qué te puedo ayudar?"

Tú: "¿Qué es la inteligencia artificial?"
Alexa: [respuesta de GPT en voz]

Tú: "Dame un ejemplo"
Alexa: [GPT recuerda el contexto y responde]

Tú: "Alexa, para"
Alexa: "¡Hasta luego!"
```

El historial de la sesión se mantiene activo mientras el skill está abierto.

---

## Personalización

En `app.py` puedes modificar:

- **`SYSTEM_PROMPT`** — cambia la personalidad o idioma de GPT
- **`model="gpt-4o-mini"`** — cámbialo a `gpt-4o` para respuestas más potentes
- **`max_tokens=200`** — ajusta el largo de las respuestas
- **`invocationName`** en el JSON — cambia cómo llamas al skill

---

## Comandos de voz disponibles

| Dices | Resultado |
|-------|-----------|
| *"Alexa, abre mi asistente"* | Inicia el skill |
| *"[cualquier pregunta]"* | GPT responde |
| *"Alexa, ayuda"* | Instrucciones |
| *"Alexa, para"* / *"Alexa, cancela"* | Cierra el skill |
