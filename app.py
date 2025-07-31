import os
import tempfile
import subprocess
# import whisper
import json
import pandas as pd
import threading
import time
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string
import requests
from rag_logic import RAG_retriever, Chat_history

app = Flask(__name__)

# === Configuration ===
FAQ_FILE_PATH = "dataset/ETSN_FAQ2.xlsx"
BOT_TOKEN = '8028991963:AAF-so-hrXy9ZFCDBreGDA1jp7Zix72tyBQ'
TELEGRAM_API_URL = f'https://api.telegram.org/bot{BOT_TOKEN}'
CHAT_HISTORY_DIR = "chat_histories"
EXCEL_PATH = "chat_histories/chat_history.xlsx"

# === Load Core Systems ===
chat_manager = Chat_history()
rag_system = RAG_retriever(excel_path=FAQ_FILE_PATH)
# whisper_model = whisper.load_model("large")
# print("✅ Whisper model loaded.")

# === Telegram Integration ===
def telegram_send_category_buttons(chat_id):
    categories = rag_system.get_all_categories()
    keyboard = [[{"text": cat, "callback_data": f"cat_{cat}"}] for cat in categories]
    payload = {
        "chat_id": chat_id,
        "text": "Zəhmət olmasa kateqoriya seçin:",
        "reply_markup": {"inline_keyboard": keyboard}
    }
    requests.post(f"{TELEGRAM_API_URL}/sendMessage", json=payload)

def telegram_send_message(chat_id, text):
    url = f'{TELEGRAM_API_URL}/sendMessage'
    payload = {'chat_id': chat_id, 'text': text}
    requests.post(url, json=payload)

def download_file(file_path, dest_path):
    file_url = f'https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}'
    r = requests.get(file_url)
    with open(dest_path, 'wb') as f:
        f.write(r.content)

# def convert_ogg_to_wav(input_path, output_path):
#     command = ['ffmpeg', '-y', '-i', input_path, '-ar', '16000', '-ac', '1', output_path]
#     subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

# === Telegram Webhook ===
@app.route('/telegram_webhook', methods=['POST'])
def telegram_webhook():
    update = request.get_json()
    print("Received update:", update)

    if 'callback_query' in update:
        callback = update['callback_query']
        chat_id = callback['message']['chat']['id']
        data = callback['data']

        if data.startswith("cat_"):
            selected_category = data.replace("cat_", "")
            session_id = str(chat_id)
            current_history = chat_manager.get_history(session_id)
            current_history.append({"role": "system", "selected_category": selected_category})
            chat_manager.save_history(session_id, current_history)
            telegram_send_message(chat_id, f"Seçdiyiniz kateqoriya: {selected_category}")
            return 'ok'
        
        return 'ok'

    if 'message' in update:
        message = update['message']
        chat_id = message['chat']['id']
        user_firstname = message['from']['first_name']

        if 'text' in message:
            user_text = message['text']

            if user_text == '/start':
                telegram_send_message(chat_id, "🟢 Xoş gəlmisiniz, müvafiq kateqoriyanı seçib sualınızı ünvanlayın.")
                telegram_send_category_buttons(chat_id)
                return jsonify({"ok": True})

            session_id = str(chat_id)
            current_history = chat_manager.get_history(session_id)
            selected_category = chat_manager.get_last_category(current_history)
            answer_data = rag_system.get_answer(user_text, active_category=selected_category)

            current_history.append({"role": "user", "user": user_firstname, "sual": user_text, "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
            current_history.append({"role": "assistant", "cavab": answer_data['Cavab'], "category": answer_data['Category'], "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
            chat_manager.save_history(session_id, current_history)

            response_text = f"Cavab:\n{answer_data['Cavab']}\n\nKategoriya: {answer_data['Category']}"
            telegram_send_message(chat_id, response_text)
            return 'ok'

        elif 'voice' in message:

            response_text = f"Səsli mesaj yollamaq funksiyası aktiv deyil."

            telegram_send_message(chat_id, response_text)
            # file_id = message['voice']['file_id']
            # file_info = requests.get(f'{TELEGRAM_API_URL}/getFile?file_id={file_id}').json()

            # if not file_info['ok']:
            #     telegram_send_message(chat_id, "Xəta: səs faylı yüklənə bilmədi.")
            #     return 'ok'

            # file_path = file_info['result']['file_path']
            # with tempfile.TemporaryDirectory() as tmpdir:
            #     ogg_path = os.path.join(tmpdir, 'voice.oga')
            #     wav_path = os.path.join(tmpdir, 'voice.wav')
            #     download_file(file_path, ogg_path)
            #     convert_ogg_to_wav(ogg_path, wav_path)
            #     transcript = whisper_model.transcribe(wav_path, language='az')['text'].strip()

            #     session_id = str(chat_id)
            #     current_history = chat_manager.get_history(session_id)
            #     selected_category = chat_manager.get_last_category(current_history)

            #     answer_data = rag_system.get_answer(transcript, active_category=selected_category)
            #     current_history.append({"role": "user", "user": user_firstname, "sual": transcript, "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
            #     current_history.append({"role": "assistant", "cavab": answer_data['Cavab'], "category": answer_data['Category'], "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
            #     chat_manager.save_history(session_id, current_history)

            #     reply_text = f"Cavab:\n{answer_data['Cavab']}\n\nKategoriya: {answer_data['Category']}"
            #     telegram_send_message(chat_id, reply_text)
            return 'ok'

    return 'ok'

# === Background Sync: JSON to Excel ===
def json_to_excel():
    all_records = []

    for filename in os.listdir(CHAT_HISTORY_DIR):
        if filename.startswith("all_histories") and filename.endswith(".json"):
            session_path = os.path.join(CHAT_HISTORY_DIR, filename)
            with open(session_path, "r", encoding="utf-8") as f:
                all_sessions = json.load(f)

            for session_id, messages in all_sessions.items():
                current_category = None
                i = 0
                while i < len(messages):
                    msg = messages[i]

                    if msg.get("role") == "system" and "selected_category" in msg:
                        current_category = msg["selected_category"]
                        i += 1

                    elif msg.get("role") == "user":
                        record = {
                            "session_id": session_id,
                            "user": msg.get("user"),
                            "user_sual": msg.get("sual"),
                            "time": msg.get("time"),
                            "selected_category": current_category,
                            "assistant_cavab": None,
                            "cavab_category": None
                        }

                        # Match with next assistant message if present
                        if i + 1 < len(messages):
                            next_msg = messages[i + 1]
                            if next_msg.get("role") == "assistant":
                                record["assistant_cavab"] = next_msg.get("cavab")
                                record["cavab_category"] = next_msg.get("category")

                        all_records.append(record)
                        i += 2  # Move past assistant

                    else:
                        i += 1  # Skip any unrelated messages

    df = pd.DataFrame(all_records)
    df.to_excel(EXCEL_PATH, index=False)
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Exported all sessions to {EXCEL_PATH}")

def set_telegram_webhook(public_url):
    webhook_url = f"{public_url}/telegram_webhook"
    response = requests.post(f"{TELEGRAM_API_URL}/setWebhook", data={"url": webhook_url})
    if response.ok:
        print(f"✅ Webhook set to: {webhook_url}")
    else:
        print(f"❌ Failed to set webhook: {response.text}")

def background_sync(interval=300):
    while True:
        try:
            json_to_excel()
        except Exception as e:
            print("Error syncing JSON to Excel:", e)
        time.sleep(interval)

@app.route("/chat_history")
def chat_history_view():
    json_to_excel()  
    df = pd.read_excel(EXCEL_PATH)
    table_html = df.to_html(classes="data", index=False)
    return render_template_string(f"""
    <html><head><title>Chat History</title><style>
    table {{ width: 80%; margin: auto; border-collapse: collapse; }}
    th, td {{ border: 1px solid #ccc; padding: 8px; }}
    </style></head><body>
    <h2 style='text-align:center;'>Chat History</h2>
    {table_html}</body></html>
    """)


if __name__ == '__main__':

    sync_thread = threading.Thread(target=background_sync, daemon=True)
    sync_thread.start()

    ngrok_url = "https://etsn-telegrambot.onrender.com"

    set_telegram_webhook(ngrok_url)

    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)