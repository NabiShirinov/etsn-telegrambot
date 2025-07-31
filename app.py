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

def set_telegram_webhook(public_url):
    webhook_url = f"{public_url}/telegram_webhook"
    response = requests.post(f"{TELEGRAM_API_URL}/setWebhook", data={"url": webhook_url})
    if response.ok:
        print(f"✅ Webhook set to: {webhook_url}")
    else:
        print(f"❌ Failed to set webhook: {response.text}")

@app.route("/chat_history")
def chat_history_view():
    with open(CHAT_HISTORY_DIR +"/all_histories.json", "r", encoding="utf-8") as f:
        all_data = json.load(f)

    records = []

    for session_id, turns in all_data.items():
        for i in range(len(turns)):
            turn = turns[i]
            if turn["role"] == "user":
                question = turn.get("sual", "")
                user = turn.get("user", "")
                time = turn.get("time", "")
                # Look ahead for the assistant response
                answer = ""
                category = ""
                if i + 1 < len(turns) and turns[i+1]["role"] == "assistant":
                    answer = turns[i+1].get("cavab", "")
                    category = turns[i+1].get("category", "")
                records.append({
                    "Session ID": session_id,
                    "User": user,
                    "Time": time,
                    "Category": category,
                    "Question": question,
                    "Answer": answer
                })

    if not records:
        return "No chat history available."

    df = pd.DataFrame(records)
    table_html = df.to_html(classes="data", index=False)

    return render_template_string(f"""
    <html><head><title>Chat History</title><style>
    table {{ width: 95%; margin: auto; border-collapse: collapse; }}
    th, td {{ border: 1px solid #ccc; padding: 8px; text-align: left; }}
    </style></head><body>
    <h2 style='text-align:center;'>Chat History</h2>
    {table_html}
    </body></html>
    """)


if __name__ == '__main__':

    ngrok_url = "https://etsn-telegrambot.onrender.com"

    set_telegram_webhook(ngrok_url)

    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)