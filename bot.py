import os
import json
import logging
import requests
import time

TELEGRAM_TOKEN     = os.environ["TELEGRAM_TOKEN"]
OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
TAVILY_API_KEY     = os.environ.get("TAVILY_API_KEY", "")
MODEL              = "qwen/qwen3-next-80b-a3b-instruct:free"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
log = logging.getLogger(__name__)

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

memory: dict = {}
MAX_HISTORY = 10

SYSTEM_PROMPT = """Kamu adalah asisten AI yang cerdas, ramah, dan helpful.
Jawab dalam bahasa yang sama dengan user (Indonesia atau Inggris).
Jika ada hasil pencarian internet, gunakan untuk menjawab dengan akurat.
Jika tidak tahu sesuatu, katakan jujur."""

# ── Tools ──────────────────────────────────────

def search_internet(query: str) -> str:
    if not TAVILY_API_KEY:
        return "Search tidak tersedia."
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
        return "\n".join([f"- {r['title']}: {r['content'][:300]}" for r in results])
    except Exception as e:
        return f"Error: {e}"

def calculate(expression: str) -> str:
    try:
        allowed = set("0123456789+-*/()., ")
        if all(c in allowed for c in expression):
            return f"{expression} = {eval(expression)}"
        return "Ekspresi tidak valid."
    except Exception as e:
        return f"Error: {e}"

TOOLS_MAP = {"search_internet": search_internet, "calculate": calculate}

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

# ── LLM ────────────────────────────────────────

def call_llm(messages: list) -> dict:
    r = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/kanjeng0981/ryznagen",
        },
        json={
            "model": MODEL,
            "messages": messages,
            "tools": TOOLS_DEF,
            "tool_choice": "auto",
            "max_tokens": 1024,
        },
        timeout=60,
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
        resp = call_llm(messages)
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

# ── Telegram ────────────────────────────────────

def send_message(chat_id: int, text: str):
    requests.post(f"{TELEGRAM_API}/sendMessage", json={"chat_id": chat_id, "text": text}, timeout=10)

def send_typing(chat_id: int):
    requests.post(f"{TELEGRAM_API}/sendChatAction", json={"chat_id": chat_id, "action": "typing"}, timeout=5)

def get_updates(offset: int = 0) -> list:
    r = requests.get(f"{TELEGRAM_API}/getUpdates", params={"offset": offset, "timeout": 30}, timeout=35)
    return r.json().get("result", [])

def flush_updates():
    r = requests.get(f"{TELEGRAM_API}/getUpdates", params={"offset": -1, "timeout": 0}, timeout=10)
    updates = r.json().get("result", [])
    if updates:
        last_id = updates[-1]["update_id"] + 1
        requests.get(f"{TELEGRAM_API}/getUpdates", params={"offset": last_id}, timeout=10)
        log.info(f"Flushed {len(updates)} pesan lama")

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
            "/clear - hapus history\n"
            "/model - info model"
        )
        return
    if text == "/clear":
        memory[user_id] = []
        send_message(chat_id, "🗑️ History dihapus!")
        return
    if text == "/model":
        send_message(chat_id, f"🤖 Model: {MODEL}")
        return
    send_typing(chat_id)
    try:
        reply = run_agent(user_id, text)
    except Exception as e:
        log.error(f"Error: {e}")
        reply = f"❌ Error: {e}"
    send_message(chat_id, reply)

# ── Main ────────────────────────────────────────

def main():
    log.info(f"✅ Model: {MODEL}")
    log.info("🤖 Bot berjalan...")
    flush_updates()  # buang semua pesan lama
    offset = 0
    while True:
        try:
            updates = get_updates(offset)
            for update in updates:
                handle_update(update)
                offset = update["update_id"] + 1
        except Exception as e:
            log.error(f"Error: {e}")
            time.sleep(3)

if __name__ == "__main__":
    main()
