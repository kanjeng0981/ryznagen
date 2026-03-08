# 🤖 Telegram AI Agent — Panduan Lengkap untuk Pemula

Project ini adalah AI Agent berbasis Telegram yang bisa:
- 💬 **Chat natural** dengan memori percakapan
- 🔍 **Search internet** untuk info terkini
- 🧮 **Hitung matematika**
- 🕐 **Cek waktu** sekarang
- 🔧 **Function calling** — LLM otomatis pilih tool yang tepat

**Stack:** Python · python-telegram-bot · Groq API (gratis) · Tavily Search (gratis) · Deploy di Railway

---

## 📋 Langkah 1 — Siapkan API Keys (semua gratis!)

### A. Telegram Bot Token
1. Buka Telegram, cari **@BotFather**
2. Ketik `/newbot`
3. Ikuti instruksi → beri nama bot kamu
4. Copy **token** yang diberikan (format: `123456:ABC-DEF...`)

### B. Groq API Key (LLM gratis)
1. Daftar di [console.groq.com](https://console.groq.com)
2. Masuk → klik **API Keys** di sidebar
3. Klik **Create API Key**
4. Copy key-nya (format: `gsk_...`)

### C. Tavily API Key (Search Internet — opsional)
1. Daftar di [app.tavily.com](https://app.tavily.com)
2. Copy API key dari dashboard
3. Gratis 1000 pencarian/bulan

---

## 💻 Langkah 2 — Jalankan di Komputer Lokal (untuk testing)

### Install Python
- Download Python 3.10+ dari [python.org](https://python.org)
- Pastikan centang "Add to PATH" saat install

### Setup Project
Buka terminal/command prompt, lalu:

```bash
# 1. Masuk ke folder project
cd telegram-ai-agent

# 2. Buat virtual environment (agar library tidak campur aduk)
python -m venv venv

# 3. Aktifkan virtual environment
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. Buat file .env dari template
copy .env.example .env        # Windows
cp .env.example .env           # Mac/Linux
```

### Isi file .env
Buka file `.env` dengan text editor, isi dengan API keys kamu:
```
TELEGRAM_TOKEN=123456:ABC-DEF-kamu
GROQ_API_KEY=gsk_kamu
TAVILY_API_KEY=tvly-kamu
```

### Jalankan Bot
```bash
python bot.py
```

Kalau berhasil akan muncul: `🤖 Bot berjalan...`

Buka Telegram, cari nama bot kamu → ketik `/start` → test!

---

## 🚀 Langkah 3 — Deploy ke Railway (gratis, online 24/7)

### Persiapan: Upload ke GitHub
1. Buat akun [github.com](https://github.com) kalau belum punya
2. Buat repository baru (klik tombol **+** → **New repository**)
3. Upload semua file project (drag & drop di browser)
   - `bot.py`
   - `requirements.txt`
   - `Procfile`
   - `.gitignore`
   - ⚠️ **JANGAN upload file `.env`** (berisi secret!)

### Deploy di Railway
1. Daftar di [railway.app](https://railway.app) (bisa login pakai GitHub)
2. Klik **New Project** → **Deploy from GitHub repo**
3. Pilih repository bot kamu
4. Railway akan otomatis detect Python dan install dependencies

### Set Environment Variables di Railway
1. Di dashboard Railway, klik project kamu
2. Klik tab **Variables**
3. Tambahkan satu per satu:
   - `TELEGRAM_TOKEN` = token bot kamu
   - `GROQ_API_KEY` = key Groq kamu
   - `TAVILY_API_KEY` = key Tavily kamu
4. Railway otomatis restart bot setelah variables diset

### Verifikasi
Buka tab **Logs** di Railway → pastikan muncul `🤖 Bot berjalan...`

Bot kamu sekarang online 24/7! 🎉

---

## 🧪 Cara Test Bot

Setelah bot berjalan, coba kirim pesan ini di Telegram:

| Pesan | Yang Terjadi |
|-------|-------------|
| `/start` | Bot perkenalan diri |
| `Berita AI terbaru?` | Bot search internet |
| `Hitung 1337 * 42` | Bot kalkulasi |
| `Jam berapa sekarang?` | Bot cek waktu |
| `Tadi kamu bilang apa?` | Bot ingat history |
| `/clear` | Hapus memory |

---

## 🔧 Kustomisasi

### Ganti Kepribadian Bot
Edit bagian `SYSTEM_PROMPT` di `bot.py`:
```python
SYSTEM_PROMPT = """Kamu adalah ... (tulis karakter bot kamu di sini)"""
```

### Ganti Model LLM
Edit `GROQ_MODEL` di `bot.py`. Model Groq yang tersedia (gratis):
- `llama3-8b-8192` — cepat, ringan ✅ (default)
- `llama3-70b-8192` — lebih pintar, agak lambat
- `mixtral-8x7b-32768` — context window besar

### Tambah Tool Baru
Contoh menambah tool "cek cuaca":
```python
def get_weather(city: str) -> str:
    # tambahkan logika di sini
    return f"Cuaca di {city}: ..."

# Tambahkan ke TOOLS_MAP:
TOOLS_MAP["get_weather"] = get_weather

# Tambahkan ke TOOLS_DEFINITION:
# (ikuti format yang sudah ada)
```

---

## ❓ Troubleshooting

**Bot tidak merespons?**
- Pastikan `.env` sudah diisi dengan benar
- Cek apakah `python bot.py` berjalan tanpa error

**Error "Unauthorized"?**
- Token Telegram salah → cek lagi di @BotFather

**Error dari Groq?**
- GROQ_API_KEY salah → buat key baru di console.groq.com
- Mungkin sudah mencapai rate limit → tunggu beberapa menit

**Search internet tidak berfungsi?**
- TAVILY_API_KEY belum diset → isi di `.env`
- Bot tetap bisa chat meski tanpa Tavily

---

## 📚 Belajar Lebih Lanjut

Setelah project ini berhasil, langkah selanjutnya:
- **LangChain** — framework untuk AI agents yang lebih kompleks
- **LlamaIndex** — untuk RAG (bot yang bisa baca dokumen PDF)
- **Supabase** — untuk menyimpan memory ke database permanen
- **Webhook** — pengganti polling, lebih efisien untuk production

Selamat belajar! 🚀
