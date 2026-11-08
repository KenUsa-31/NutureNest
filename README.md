# NurtureNest

A companion-first chatbot prototype for people seeking general information about pregnancy, prenatal care, birth preparation, and postnatal care. NurtureNest is a fictional educational project, not a real clinic or a substitute for professional care.

## Run locally

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python app.py
```

Open http://127.0.0.1:5000. A Gemini key is optional. Without one, the app returns relevant cited passages from its reviewed knowledge base. To enable generated replies, put a Gemini API key in `GEMINI_API_KEY` in your private `.env` file.

## Configuration

- `GEMINI_API_KEY`: optional Gemini API key
- `GEMINI_MODEL`: defaults to `gemini-3.8-flash`
- `GEMINI_BASE_URL`: defaults to Google's OpenAI-compatible Gemini endpoint

Never commit `.env` or share API keys. For Vercel, add `GEMINI_API_KEY` as a Secret environment variable and redeploy. Do not put credentials in the browser or source files.

## How it works

- Flask serves the web interface and a streaming chat endpoint.
- scikit-learn TF-IDF and cosine similarity retrieve relevant, cited passages from `knowledge_base.json`.
- When configured, Gemini generates a conversational reply grounded in retrieved passages.
- Without a key or if generation fails, the companion provides cited passages or a supportive no-match response.
- Conversation history is held in the browser tab; the app does not write chat messages to a server-side log.

## Safety and scope

NurtureNest is a supportive AI companion, not a person, clinic, midwife, nurse, doctor, or emergency service. It must not diagnose, assess an individual pregnancy, recommend medication, or create a personal care plan. It does not invent clinic-specific details. Emergency warning signs trigger an urgent-care message. Review the knowledge base and emergency instructions with a qualified local clinician before any real-world use.

See [references.md](references.md) for sources.
