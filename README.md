# Alexa + ChatGPT Bridge

Conecta tu Amazon Echo Dot con ChatGPT usando Flask, desplegado como función serverless en Vercel.

---

## Estructura del proyecto

```
alexa-gpt/
├── api/
│   └── alexa.py             # Servidor Flask (función serverless)
├── requirements.txt
├── vercel.json               # Enruta todas las rutas hacia api/alexa.py
├── .env.example               # Variables de entorno de ejemplo (uso local)
├── alexa_skill_model.json    # Modelo del Skill para Alexa Console
└── README.md
```

---

## Paso 1 — Desplegar en Vercel

1. Sube el proyecto a un repo en GitHub.
2. En [vercel.com](https://vercel.com) → **Add New Project** → importa el repo.
3. En **Settings → Environment Variables** agrega (aplica a Production, Preview y Development):
   ```
   OPENAI_API_KEY = sk-proj-tu-clave-aqui
   ```
   > Importante: esto **no** se lee del archivo `.env` en producción. Vercel solo usa
   > las variables configuradas en el dashboard del proyecto.
4. Despliega. Vercel te dará una URL pública tipo:
   ```
   https://tu-proyecto.vercel.app
   ```
5. Prueba que funciona abriendo esa URL en el navegador:
   ```
   GET https://tu-proyecto.vercel.app/
   → {"status": "online", "service": "Alexa-GPT Bridge"}
   ```
   Si ves ese JSON, el despliegue está bien. Si ves "Not Found", revisa que
   `vercel.json` se haya subido y que la variable de entorno esté configurada.

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
3. En **Default Region** pega directamente la URL de Vercel (sin `/alexa` al final,
   ya que `vercel.json` enruta cualquier ruta hacia la función):
   ```
   https://tu-proyecto.vercel.app/
   ```
4. En el dropdown de SSL → **My development endpoint is a sub-domain of a domain
   that has a wildcard certificate from a certificate authority**
5. Click **Save Endpoints**

---

## Paso 5 — Probar

### En el simulador de Alexa:
1. Ve a **Test** → activa **Development**
2. Escribe o di: `abre mi asistente`
3. Luego pregunta lo que quieras, por ejemplo: `pregunta cuál es la capital de Francia`

### En tu Echo Dot real:
1. Di: *"Alexa, abre mi asistente"*
2. Alexa responde: *"Hola, soy tu asistente con Chat GPT..."*
3. Pregunta: *"Pregunta cuál es la distancia de la Tierra al Sol"*
4. Alexa habla la respuesta de GPT ✅

> Nota: por cómo funciona el slot `AMAZON.SearchQuery` de Alexa, la pregunta
> siempre debe ir acompañada de una palabra guía (`pregunta`, `dime`, `qué es`,
> `cómo funciona`, `cuéntame`, `explícame`, `ayúdame con`, `quiero saber`). Decir
> la pregunta sola, sin ninguna de esas palabras, no es válido para este tipo de slot.

---

## Cómo funciona la conversación

```
Tú: "Alexa, abre mi asistente"
Alexa: "Hola, soy tu asistente con Chat GPT. ¿En qué te puedo ayudar?"

Tú: "Qué es la inteligencia artificial"
Alexa: [respuesta de GPT en voz]

Tú: "Dime otro ejemplo"
Alexa: [GPT responde a la nueva pregunta]

Tú: "Alexa, para"
Alexa: "¡Hasta luego!"
```

Cada pregunta se envía a GPT de forma independiente (sin memoria entre preguntas
dentro de la misma sesión).

---

## Seguridad (opcional pero recomendado)

Cualquiera que descubra tu URL de Vercel puede enviarle solicitudes falsas y
consumir tu crédito de OpenAI, ya que por defecto el endpoint no verifica quién
lo llama. Para mitigar esto:

1. En Alexa Developer Console, copia el **Skill ID** (botón "View Skill ID",
   parece `amzn1.ask.skill.xxxxxxxx-xxxx-...`).
2. En Vercel, agrega la variable de entorno:
   ```
   ALEXA_SKILL_ID = amzn1.ask.skill.tu-id-aqui
   ```
3. Con esa variable configurada, el servidor rechaza cualquier solicitud que no
   declare ese mismo Skill ID.

Esto **no** reemplaza la verificación completa de firma que usa el SDK oficial
de Alexa (`ask-sdk`), pero bloquea el abuso más común (bots o curiosos que
encuentran la URL). Si necesitas verificación de firma criptográfica completa,
sería un cambio más grande, es un buen candidato para migrar a `ask-sdk-core`.

---

## Personalización

En `api/alexa.py` puedes modificar:

- **`SYSTEM_PROMPT`** — cambia la personalidad o idioma de GPT
- **`model="gpt-4o-mini"`** — cámbialo a `gpt-4o` para respuestas más potentes
- **`max_tokens=200`** — ajusta el largo de las respuestas
- **`invocationName`** en el JSON — cambia cómo llamas al skill

---

## Comandos de voz disponibles

| Dices | Resultado |
|-------|-----------|
| *"Alexa, abre mi asistente"* | Inicia el skill |
| *"pregunta [tu pregunta]"*, *"dime [tu pregunta]"*, etc. | GPT responde |
| *"Alexa, ayuda"* | Instrucciones |
| *"Alexa, para"* / *"Alexa, cancela"* | Cierra el skill |
