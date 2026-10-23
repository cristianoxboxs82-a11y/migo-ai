import os, time, threading, asyncio
from collections import deque
from datetime import datetime
from flask import Flask, jsonify, render_template, request
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

EVENTS = deque(maxlen=250)
EVENT_ID = 0
LOCK = threading.Lock()
CLIENT_STATE = {"status": "Aguardando configuração", "username": "", "error": ""}
CLIENT = None
CLIENT_LOOP = None
STOP_EVENT = None
LAST_AI_REPLY = 0.0
AI_LOCK = threading.Lock()

def add_event(kind, user, message, extra=""):
    global EVENT_ID
    with LOCK:
        EVENT_ID += 1
        EVENTS.append({
            "id": EVENT_ID,
            "kind": kind,
            "user": str(user or "alguém")[:80],
            "message": str(message or "")[:350],
            "extra": str(extra or "")[:120],
            "time": datetime.now().strftime("%H:%M:%S")
        })

def ai_reply(comment, username):
    """Uses Gemini only on the server; falls back to a simple response without a key."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return f"Oi, {username}! 😎 Vi sua mensagem: {comment[:90]}"
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        prompt = (
            "Você é MIGO AI, uma IA divertida e educada em uma live brasileira de gameplay. "
            "Responda em português brasileiro, de forma curta (máximo 160 caracteres), "
            "leve e respeitosa. Não peça dados pessoais, não incentive compras ou presentes, "
            "não ofenda ninguém. Mensagem do espectador "
            f"@{username}: {comment}"
        )
        result = client.models.generate_content(model=model, contents=prompt)
        text = (getattr(result, "text", None) or "").strip()
        return text[:220] if text else f"Valeu pela mensagem, {username}! 😎"
    except Exception as exc:
        app.logger.warning("Gemini request failed: %s", exc)
        return f"Boa, {username}! 😎 Tô aqui com vocês!"

def maybe_reply_to_comment(comment, username):
    global LAST_AI_REPLY
    # Avoid replying to every message: only reply when viewer addresses MIGO/IA.
    if not any(word in comment.lower() for word in ("migo", "migo ai", "ia")):
        return
    now = time.time()
    with AI_LOCK:
        if now - LAST_AI_REPLY < 8:
            return
        LAST_AI_REPLY = now
    answer = ai_reply(comment, username)
    add_event("ai", "MIGO AI", answer, f"Resposta para @{username}")

def start_tiktok_listener(username):
    def runner():
        global CLIENT, CLIENT_LOOP, STOP_EVENT
        try:
            from TikTokLive import TikTokLiveClient
            from TikTokLive.events import ConnectEvent, DisconnectEvent, CommentEvent, GiftEvent
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            CLIENT_LOOP = loop
            STOP_EVENT = asyncio.Event()
            client = TikTokLiveClient(unique_id=username.lstrip("@"))
            CLIENT = client
            CLIENT_STATE.update(status="Conectando…", username=username.lstrip("@"), error="")

            @client.on(ConnectEvent)
            async def on_connect(event):
                CLIENT_STATE.update(status="Conectado à LIVE", error="")
                add_event("system", "MIGO AI", f"Conectado à @{username.lstrip('@')}!")

            @client.on(DisconnectEvent)
            async def on_disconnect(event):
                CLIENT_STATE.update(status="Desconectado")
                add_event("system", "MIGO AI", "A conexão com a LIVE foi encerrada.")

            @client.on(CommentEvent)
            async def on_comment(event):
                nick = getattr(getattr(event, "user", None), "nickname", "espectador")
                comment = getattr(event, "comment", "")
                add_event("comment", nick, comment)
                if comment:
                    # AI work is kept off the event callback so comments keep flowing.
                    threading.Thread(target=maybe_reply_to_comment, args=(comment, nick), daemon=True).start()

            @client.on(GiftEvent)
            async def on_gift(event):
                user_obj = getattr(event, "user", None)
                nick = getattr(user_obj, "nickname", "espectador")
                gift_obj = getattr(event, "gift", None)
                gift_name = getattr(gift_obj, "name", "presente") if gift_obj else "presente"
                repeat = getattr(event, "repeat_count", 1) or 1
                add_event("gift", nick, f"🎁 {gift_name}", f"x{repeat}")
                add_event("ai", "MIGO AI", f"Valeu pelo carinho, {nick}! 💜 Obrigado por estar na live!", f"Reação a presente: {gift_name}")

            await client.start()
            await STOP_EVENT.wait()
            await client.stop()
        except Exception as exc:
            CLIENT_STATE.update(status="Erro de conexão", error=str(exc)[:250])
            add_event("error", "MIGO AI", "Não consegui conectar à LIVE. Confira o @ e se a transmissão está ao vivo.", str(exc)[:160])
        finally:
            CLIENT_STATE.update(status="Desconectado")
    threading.Thread(target=runner, daemon=True).start()

@app.get("/")
def home():
    return render_template("index.html")

@app.get("/api/status")
def status():
    return jsonify(CLIENT_STATE)

@app.get("/api/events")
def events():
    try:
        after = int(request.args.get("after", "0"))
    except ValueError:
        after = 0
    with LOCK:
        items = [e for e in EVENTS if e["id"] > after]
    return jsonify(items)

@app.post("/api/connect")
def connect():
    username = (request.json or {}).get("username", "").strip().lstrip("@")
    if not username or len(username) > 50 or any(ch.isspace() for ch in username):
        return jsonify({"ok": False, "error": "Digite seu @ do TikTok sem espaços."}), 400
    if CLIENT_STATE.get("status") in ("Conectando…", "Conectado à LIVE"):
        return jsonify({"ok": False, "error": "Já existe uma tentativa de conexão. Desconecte ou aguarde."}), 409
    start_tiktok_listener(username)
    return jsonify({"ok": True, "message": "Tentando conectar. A LIVE precisa estar pública e ao vivo."})

@app.post("/api/disconnect")
def disconnect():
    global STOP_EVENT, CLIENT_LOOP
    if STOP_EVENT and CLIENT_LOOP and CLIENT_LOOP.is_running():
        def set_stop():
            STOP_EVENT.set()
        CLIENT_LOOP.call_soon_threadsafe(set_stop)
    CLIENT_STATE.update(status="Desconectando…")
    return jsonify({"ok": True})

if __name__ == "__main__":
    # Local development only. Production uses gunicorn.
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")), debug=False)
