import os
import json
import logging
import requests
import time

# ── Langsung baca dari os.environ ──────────────
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
GROQ_API_KEY   = os.environ["GROQ_API_KEY"]
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")
GROQ_MODEL     = "llama3-groq-8b-8192-tool-use-preview"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
log = logging.getLogger(__name__)

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# ── Memory percakapan per user ──────────────────
memory: dict = {}
MAX_HISTORY = 10

SYSTEM_PROMPT = """Kamu adalah asisten AI yang cerdas dan ramah.
Jawab dalam bahasa yang sama dengan user (Indonesia atau Inggris).
Jika ada hasil pencarian, gunakan untuk menjawab dengan akurat."""


# ── Tools ───────────────────────────────────────

def search_internet(query: str) -> str:
    if not TAVILY_API_KEY:
        return "Search tidak tersedia (TAVILY_API_KEY belum diset)."
    try:
        r = requests.post("https://api.tavily.com/search", json={
            "api_key": TAVILY_API_KEY,
            "query": query,
            "search_depth": "basic",
            "max_results": 3,
        }, timeout=10)
        results = r.json().get("results", [])
        if not results:
            return "Tidak ada hasil."
        out = []
        for res in results:
            out.append(f"- {res['title']}: {res['content'][:300]}")
        return "\n".join(out)
    except Exception as e:
        return f"Error search: {e}"


def calculate(expression: str) -> str:
    try:
        allowed = set("0123456789+-*/()., ")
        if all(c in allowed for c in expression):
            return f"{expression} = {eval(expression)}"  # noqa: S307
        return "Ekspresi tidak valid."
    except Exception as e:
        return f"Error: {e}"


TOOLS_DEF = [
    {
        "type": "function",
        "function": {
            "name": "search_internet",
            "description": "Cari informasi terbaru di internet.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "Hitung ekspresi matematika.",
            "parameters": {
                "type": "object",
                "properties": {"expression": {"type": "string"}},
                "required": ["expression"],
            },
        },
    },
]

TOOLS_MAP = {"search_internet": search_internet, "calculate": calculate}


# ── Groq LLM ────────────────────────────────────

def call_groq(messages: list) -> dict:
    r = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json={"model": GROQ_MODEL, "messages": messages, "tools": TOOLS_DEF,
              "tool_choice": "auto", "max_tokens": 1024},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def run_agent(user_id: int, user_msg: str) -> str:
    if user_id not in memory:
        memory[user_id] = []

    history = memory[user_id]
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history + [
        {"role": "user", "content": user_msg}
    ]

    for _ in range(5):
        resp = call_groq(messages)
        choice = resp["choices"][0]
        msg = choice["message"]
        messages.append(msg)

        if choice["finish_reason"] == "tool_calls":
            for tc in msg.get("tool_calls", []):
                fn_name = tc["function"]["name"]
                fn_args = json.loads(tc["function"].get("arguments", "{}"))
                log.info(f"Tool: {fn_name}({fn_args})")
                result = TOOLS_MAP[fn_name](**fn_args)
                messages.append({"role": "tool", "tool_call_id": tc["id"], "content": str(result)})
        else:
            answer = msg.get("content", "Maaf, tidak ada jawaban.")
            history.append({"role": "user", "content": user_msg})
            history.append({"role": "assistant", "content": answer})
            if len(history) > MAX_HISTORY * 2:
                memory[user_id] = history[-(MAX_HISTORY * 2):]
            return answer

    return "Maaf, tidak bisa menyelesaikan permintaan."


# ── Telegram API helpers ─────────────────────────

def send_message(chat_id: int, text: str):
    requests.post(f"{TELEGRAM_API}/sendMessage", json={
        "chat_id": chat_id, "text": text
    }, timeout=10)


def send_typing(chat_id: int):
    requests.post(f"{TELEGRAM_API}/sendChatAction", json={
        "chat_id": chat_id, "action": "typing"
    }, timeout=5)


def get_updates(offset: int = 0) -> list:
    r = requests.get(f"{TELEGRAM_API}/getUpdates", params={
        "offset": offset, "timeout": 30
    }, timeout=35)
    return r.json().get("result", [])


# ── Handler pesan ────────────────────────────────

def handle_update(update: dict):
    msg = update.get("message", {})
    if not msg:
        return

    chat_id = msg["chat"]["id"]
    user_id = msg["from"]["id"]
    text    = msg.get("text", "")

    if not text:
        return

    if text == "/start":
        send_message(chat_id,
            "👋 Halo! Saya AI Agent yang bisa:\n"
            "🔍 Cari info di internet\n"
            "🧮 Hitung matematika\n"
            "💬 Ingat percakapan kita\n\n"
            "Ketik saja pertanyaanmu!\n"
            "/clear - hapus history"
        )
        return

    if text == "/clear":
        memory[user_id] = []
        send_message(chat_id, "🗑️ History dihapus!")
        return

    if text == "/help":
        send_message(chat_id,
            "💡 Contoh:\n"
            "• Berita AI terbaru?\n"
            "• Hitung 1234 * 5678\n"
            "• Jelaskan machine learning\n"
        )
        return

    send_typing(chat_id)
    try:
        reply = run_agent(user_id, text)
    except Exception as e:
        log.error(f"Error: {e}")
        reply = f"❌ Error: {e}"

    send_message(chat_id, reply)


# ── Main loop ────────────────────────────────────

def main():
    log.info("✅ ENV OK — Token ada, Groq key ada")
    log.info("🤖 Bot berjalan dengan long polling...")
    offset = 0
    while True:
        try:
            updates = get_updates(offset)
            for update in updates:
                handle_update(update)
                offset = update["update_id"] + 1
        except Exception as e:
            log.error(f"Error polling: {e}")
            time.sleep(3)


if __name__ == "__main__":
    main()
