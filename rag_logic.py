# -*- coding: utf-8 -*-
import pandas as pd
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import os
import json
import datetime
from typing import Union

# ==============================================================================
#  RAG Retriever Class
# ==============================================================================
class RAG_retriever:
    """
    Manages loading FAQ data, creating embeddings, and retrieving answers.
    """
    def __init__(self, excel_path: str, model_name: str = 'BAAI/bge-m3'):
        """
        Initializes the RAG system by loading the model and embedding the FAQ data.
        """
        if not os.path.exists(excel_path):
            raise FileNotFoundError(f"Critical Error: FAQ file not found at {excel_path}")

        print(f"Loading embedding model: {model_name}")
        self.model = SentenceTransformer(model_name)

        print("Reading FAQ file and preparing embeddings...")
        self.faq_data, self.question_embeddings = self._load_and_embed_faq(excel_path)
        self.categories = self.faq_data['Category'].unique()
        print("✅ RAG system is ready. Available categories:", self.categories)

    def _load_and_embed_faq(self, excel_path: str):
        """
        Loads data from an Excel file and creates embeddings for questions only.
        """
        df = pd.read_excel(excel_path)
        if 'Sual' not in df.columns or 'Cavab' not in df.columns or 'Category' not in df.columns:
            raise ValueError("Excel file must contain 'Sual', 'Cavab', and 'Category' columns.")

        df['Category'].fillna('Ümumi', inplace=True)

        print("Creating embeddings based on questions only...")
        question_embeddings = self.model.encode(
            df['Sual'].tolist(),
            convert_to_tensor=False,
            normalize_embeddings=True
        )
        return df, question_embeddings
    
    def get_all_categories(self):
        return list(self.categories)

    def get_answer(self, user_query: str, similarity_threshold: float = 0.57,
                   active_category: str = None, boost_factor: float = 0.07):
        """
        Находит наиболее релевантный ответ, отдавая "мягкий" приоритет
        активной категории с помощью бустинга. Эта версия заменяет старую логику.
        Args:
            user_query: Запрос пользователя.
            similarity_threshold: Минимальное "реальное" сходство для выдачи ответа.
            active_category: Активная категория для поиска.
            boost_factor: "Бонус", который добавляется к баллам из активной категории.
                          Помогает оставаться в контексте, но позволяет переключиться,
                          если есть гораздо более релевантный ответ в другой категории.
        """
        if len(user_query.split()) < 3:
            return {
                "Sual": "Qısa sorğu",
                "Cavab": "Zəhmət olmasa, sorğunuzu daha ətraflı formada yazın.",
                "Category": "Sistem Mesajı",
                "Similarity": 0.0
            }
        if user_query == 'Çox saq ol' or user_query == 'Teşekkür ederim':
            return print('Bizdə sizə təşəkkur edirik')
        # 1. Создаем эмбеддинг для запроса пользователя
        query_embedding = self.model.encode(
            user_query,
            convert_to_tensor=False,
            normalize_embeddings=True
        ).reshape(1, -1)

        # 2. Вычисляем сходство со ВСЕМИ вопросами в базе данных
        all_similarities = cosine_similarity(query_embedding, self.question_embeddings)[0]

        # 3. Применяем "бонус" (boost) к вопросам из активной категории
        boosted_similarities = all_similarities.copy()
        if active_category and active_category in self.categories:
            print(f"ℹ️ Применяется бонус (+{boost_factor}) для категории: '{active_category}'")
            category_mask = self.faq_data['Category'] == active_category
            boosted_similarities[category_mask] += boost_factor

        # 4. Находим лучший результат в массиве с учетом бонуса
        best_match_idx = np.argmax(boosted_similarities)

        # 5. Получаем реальный (без бонуса) балл сходства для лучшего найденного ответа
        real_similarity_score = all_similarities[best_match_idx]
        best_match_data = self.faq_data.iloc[best_match_idx]

        # Отладочная информация
        print(f"🔍 Best Candidate: '{best_match_data['Sual'][:60]}...'")
        print(f"   - Category: '{best_match_data['Category']}'")
        print(f"   - Similarity Score: {real_similarity_score:.4f}")
        if active_category and best_match_data['Category'] == active_category:
            print(f"   - With boosted bonus: {boosted_similarities[best_match_idx]:.4f}")


        # 6. Возвращаем ответ, только если его РЕАЛЬНОЕ сходство выше порога
        if real_similarity_score >= similarity_threshold:
            print(f"✅ Ответ найден. Финальная категория: '{best_match_data['Category']}'")
            return {
                "Sual": best_match_data['Sual'],
                "Cavab": best_match_data['Cavab'],
                "Category": best_match_data['Category'],
                "Similarity": float(real_similarity_score)
            }
        else:
            print(f"❌ Подходящий ответ не найден. Лучший результат ({real_similarity_score:.4f}) ниже порога ({similarity_threshold}).")
            return {
                "Sual": "Uyğun sual tapılmadı",
                "Cavab": "Təəssüf ki, sorğunuza uyğun cavab tapa bilmədim. Zəhmət olmasa, sualınızı fərqli şəkildə ifadə edin.",
                "Category": "Kateqoriya tapılmadı",
                "Similarity": float(real_similarity_score)
            }

# ==============================================================================
#  Chat History Manager Class
# ==============================================================================

class Chat_history:
    def __init__(self, history_file: str = "chat_histories/all_histories.json"):
        self.history_file = history_file
        self.history_dir = os.path.dirname(self.history_file)
        if self.history_dir and not os.path.exists(self.history_dir):
            os.makedirs(self.history_dir)
        
        # Create file if it doesn't exist
        if not os.path.exists(self.history_file):
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump({}, f)

        print(f"Chat_history module is ready. All histories will be saved in '{self.history_file}'.")

    def _load_all_histories(self) -> dict:
        try:
            with open(self.history_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    def _save_all_histories(self, all_histories: dict):
        with open(self.history_file, 'w', encoding='utf-8') as f:
            json.dump(all_histories, f, ensure_ascii=False, indent=2)

    def get_history(self, session_id: str) -> list:
        all_histories = self._load_all_histories()
        return all_histories.get(session_id, [])

    def save_history(self, session_id: str, history: list):
        all_histories = self._load_all_histories()
        all_histories[session_id] = history
        self._save_all_histories(all_histories)

    def get_last_category(self, history: list) -> Union[str, None]:
        """Scans history backwards and finds the last selected category from system messages."""
        for msg in reversed(history):
            if msg.get('role') == 'system' and 'selected_category' in msg:
                return msg['selected_category']
        return None

def generate_session_id() -> str:
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

# ==============================================================================
#  Main execution block for testing
# ==============================================================================
if __name__ == "__main__":
    FAQ_FILE_PATH = "ETSN_FAQ2.xlsx" # Убедитесь, что файл существует
    try:
        rag_system = RAG_retriever(excel_path=FAQ_FILE_PATH)
        chat_manager = Chat_history()
        session_id = generate_session_id()

        print(f"\n✅ System is ready. New chat started. Session ID: {session_id}")
        print("--- Enter your question ---")
        print("💡Type 'exit' to stop, 'new' to start a new chat.")
        print("💡Type 'cat:CategoryName' to set active category.")

        active_category = None
        while True:
            user_input = input(f"\n[{session_id} | Cat: {active_category}] Your question: ")

            if user_input.lower().startswith("cat:"):
                new_cat = user_input.split(":", 1)[1].strip()
                if new_cat in rag_system.categories:
                    active_category = new_cat
                    print(f"✅ Новая активная категория: {active_category}")
                else:
                    print(f"❌ Категория '{new_cat}' не найдена. Доступные: {list(rag_system.categories)}")
                    # active_category остается прежним или None
                continue

            if user_input.lower() == 'exit':
                print("Program stopped.")
                break
            if user_input.lower() == 'new':
                session_id = generate_session_id()
                active_category = None
                print(f"\n🔄 New chat started. New Session ID: {session_id}")
                continue

            answer = rag_system.get_answer(user_input, active_category=active_category)
            print("\n--- СИСТЕМА ОТВЕТА ---")

            print(f"Category: {answer['Category']}")
            print(f"Most similar question (Similarity: {answer['Similarity']:.2f}): {answer['Sual']}")
            print(f"Answer: {answer['Cavab']}")
            print("----------------------")

    except FileNotFoundError as e:
        print(f"ERROR: {e}")
    except ValueError as e:
        print(f"ERROR: Excel file format is incorrect. {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")