import os
import json
import logging
import requests
from datetime import datetime
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from dotenv import load_dotenv

load_dotenv()

# ──────────────────────────────────────────────
# KONFIGURASI
# ──────────────────────────────────────────────
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY   = os.getenv("GROQ_API_KEY")
GROQ_MODEL     = "llama3-8b-8192"          # model gratis dari Groq
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")  # untuk search internet (gratis)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# MEMORY: simpan history per user (in-memory)
# ──────────────────────────────────────────────
# Format: { user_id: [ {role, content}, ... ] }
conversation_memory: dict[int, list] = {}
MAX_HISTORY = 10  # simpan 10 pesan terakhir per user

SYSTEM_PROMPT = """Kamu adalah asisten AI yang cerdas, ramah, dan helpful.
Kamu bisa menjawab pertanyaan, menganalisis informasi, dan membantu berbagai tugas.
Jika ada hasil pencarian internet, gunakan informasi itu untuk menjawab dengan akurat.
Jawab dalam bahasa yang sama dengan user (Indonesia atau Inggris).
Jika tidak tahu sesuatu, katakan jujur dan tawarkan untuk mencarinya."""


# ──────────────────────────────────────────────
# TOOLS
# ──────────────────────────────────────────────

def search_internet(query: str) -> str:
    """Cari informasi di internet menggunakan Tavily API (gratis 1000 req/bulan)."""
    if not TAVILY_API_KEY:
        return "⚠️ Search tidak tersedia (TAVILY_API_KEY belum diset)."
    try:
        response = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": TAVILY_API_KEY,
                "query": query,
                "search_depth": "basic",
                "max_results": 3,
            },
            timeout=10,
        )
        data = response.json()
        results = data.get("results", [])
        if not results:
            return "Tidak ada hasil pencarian ditemukan."

        formatted = []
        for r in results:
            formatted.append(f"📌 {r.get('title', '')}\n{r.get('content', '')[:300]}...\nSumber: {r.get('url', '')}")
        return "\n\n".join(formatted)
    except Exception as e:
        return f"Error saat search: {str(e)}"


def get_current_time() -> str:
    """Ambil waktu dan tanggal sekarang."""
    now = datetime.now()
    return now.strftime("Sekarang: %A, %d %B %Y pukul %H:%M:%S WIB")


def calculate(expression: str) -> str:
    """Hitung ekspresi matematika sederhana."""
    try:
        # aman: hanya izinkan karakter angka dan operator dasar
        allowed = set("0123456789+-*/()., ")
        if all(c in allowed for c in expression):
            result = eval(expression)  # noqa: S307
            return f"Hasil: {expression} = {result}"
        return "Ekspresi tidak valid."
    except Exception as e:
        return f"Error kalkulasi: {str(e)}"


# Daftar tools yang tersedia untuk LLM
TOOLS_DEFINITION = [
    {
        "type": "function",
        "function": {
            "name": "search_internet",
            "description": "Cari informasi terbaru di internet. Gunakan ini untuk berita terkini, fakta yang perlu diverifikasi, atau info yang mungkin belum kamu tahu.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Query pencarian dalam bahasa Indonesia atau Inggris",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Ambil waktu dan tanggal saat ini.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "Hitung ekspresi matematika. Contoh: '25 * 4 + 10'",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Ekspresi matematika yang ingin dihitung",
                    }
                },
                "required": ["expression"],
            },
        },
    },
]

TOOLS_MAP = {
    "search_internet": search_internet,
    "get_current_time": lambda: get_current_time(),
    "calculate": calculate,
}


# ──────────────────────────────────────────────
# GROQ API (LLM gratis)
# ──────────────────────────────────────────────

def call_groq(messages: list, use_tools: bool = True) -> dict:
    """Kirim request ke Groq API."""
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": GROQ_MODEL,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 1024,
    }
    if use_tools:
        payload["tools"] = TOOLS_DEFINITION
        payload["tool_choice"] = "auto"

    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def run_agent(user_id: int, user_message: str) -> str:
    """
    Jalankan AI agent dengan loop tool-calling:
    1. Kirim pesan ke LLM
    2. Jika LLM minta pakai tool → jalankan tool → kirim hasilnya kembali
    3. Ulangi sampai LLM beri jawaban final
    """
    # Ambil atau buat history user
    if user_id not in conversation_memory:
        conversation_memory[user_id] = []

    history = conversation_memory[user_id]

    # Bangun messages lengkap
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history + [
        {"role": "user", "content": user_message}
    ]

    # Loop agent (max 5 iterasi agar tidak infinite loop)
    for _ in range(5):
        response = call_groq(messages)
        choice = response["choices"][0]
        message = choice["message"]

        # Tambah response LLM ke messages
        messages.append(message)

        # Cek apakah LLM selesai atau minta pakai tool
        if choice["finish_reason"] == "tool_calls":
            # Jalankan setiap tool yang diminta
            tool_calls = message.get("tool_calls", [])
            for tc in tool_calls:
                fn_name = tc["function"]["name"]
                fn_args = json.loads(tc["function"].get("arguments", "{}"))
                logger.info(f"🔧 Menjalankan tool: {fn_name}({fn_args})")

                fn_result = TOOLS_MAP[fn_name](**fn_args)

                # Masukkan hasil tool ke messages
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": str(fn_result),
                })
        else:
            # LLM sudah selesai → ambil jawaban final
            final_answer = message.get("content", "Maaf, tidak ada jawaban.")

            # Simpan ke memory (user + assistant)
            history.append({"role": "user", "content": user_message})
            history.append({"role": "assistant", "content": final_answer})

            # Batasi history agar tidak terlalu panjang
            if len(history) > MAX_HISTORY * 2:
                conversation_memory[user_id] = history[-(MAX_HISTORY * 2):]

            return final_answer

    return "Maaf, agen tidak bisa menyelesaikan permintaan ini."


# ──────────────────────────────────────────────
# TELEGRAM HANDLERS
# ──────────────────────────────────────────────

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"👋 Halo {user.first_name}!\n\n"
        "Saya adalah AI Agent yang bisa:\n"
        "🔍 Mencari informasi di internet\n"
        "💬 Mengingat percakapan kita\n"
        "🧮 Menghitung matematika\n"
        "🕐 Memberitahu waktu sekarang\n\n"
        "Cukup ketik pertanyaan atau permintaanmu!\n\n"
        "Perintah tersedia:\n"
        "/start - Tampilkan pesan ini\n"
        "/clear - Hapus history percakapan\n"
        "/help  - Bantuan"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💡 *Cara Pakai:*\n\n"
        "Ketik saja pertanyaanmu secara natural!\n\n"
        "*Contoh:*\n"
        "• Berita terbaru tentang teknologi AI?\n"
        "• Hitung 1234 * 5678\n"
        "• Jam berapa sekarang?\n"
        "• Jelaskan apa itu machine learning\n"
        "• Lanjutkan percakapan sebelumnya...\n\n"
        "Agent akan otomatis memilih tool yang tepat! 🤖",
        parse_mode="Markdown",
    )


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conversation_memory[user_id] = []
    await update.message.reply_text("🗑️ History percakapan kamu sudah dihapus!")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id  = update.effective_user.id
    user_msg = update.message.text

    # Kirim "typing..." indicator
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action="typing"
    )

    try:
        reply = run_agent(user_id, user_msg)
    except Exception as e:
        logger.error(f"Error: {e}")
        reply = f"❌ Terjadi error: {str(e)}\nCoba lagi atau ketik /clear untuk reset."

    await update.message.reply_text(reply)


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────

def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_TOKEN belum diset di .env!")
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY belum diset di .env!")

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help",  help_command))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("🤖 Bot berjalan...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
