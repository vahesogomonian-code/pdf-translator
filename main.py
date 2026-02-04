import os
import threading
import requests
import fitz  # PyMuPDF
from kivy.storage.jsonstore import JsonStore
from kivy.lang import Builder
from kivymd.app import MDApp
from kivymd.uix.filemanager import MDFileManager
from kivymd.uix.screen import MDScreen
from kivy.clock import Clock
from kivy.utils import platform

# Хранилище для сохранения ключа на телефоне
store = JsonStore('gemini_config.json')

KV = '''
MDScreenManager:
    MainScreen:

<MainScreen>:
    name: "main"
    MDBoxLayout:
        orientation: "vertical"
        padding: "20dp"
        spacing: "15dp"

        MDLabel:
            text: "Gemini PDF Translator"
            halign: "center"
            font_style: "H5"
            theme_text_color: "Primary"

        MDTextField:
            id: api_key
            hint_text: "Введите ваш Gemini API Key"
            helper_text: "Ключ сохранится в приложении"
            helper_text_mode: "on_focus"
            mode: "rectangle"
            text: app.get_saved_key()

        MDRaisedButton:
            text: "📁 ВЫБРАТЬ PDF ФАЙЛ"
            pos_hint: {"center_x": .5}
            on_release: app.open_file_manager()

        MDLabel:
            id: status
            text: "Файл не выбран"
            halign: "center"
            italic: True

        MDProgressBar:
            id: progress
            value: 0
            max: 100

        MDRectangleFlatIconButton:
            id: start_btn
            icon: "translate"
            text: "НАЧАТЬ ПЕРЕВОД"
            disabled: True
            pos_hint: {"center_x": .5}
            on_release: app.start_processing()
'''

class MainScreen(MDScreen):
    pass

class App(MDApp):
    def build(self):
        self.theme_cls.primary_palette = "DeepPurple"
        self.pdf_path = None
        self.file_manager = MDFileManager(
            exit_manager=self.close_manager,
            select_path=self.select_path
        )
        return Builder.load_string(KV)

    def get_saved_key(self):
        if store.exists('credentials'):
            return store.get('credentials')['key']
        return ""

    def open_file_manager(self):
        # Находим путь к документам
        path = "/sdcard" if platform == "android" else os.path.expanduser("~")
        self.file_manager.show(path)

    def close_manager(self, *args):
        self.file_manager.close()

    def select_path(self, path):
        if path.lower().endswith(".pdf"):
            self.pdf_path = path
            self.root.get_screen("main").ids.status.text = f"Выбран: {os.path.basename(path)}"
            self.root.get_screen("main").ids.start_btn.disabled = False
        self.close_manager()

    def update_ui(self, text=None, progress=None):
        def _update(dt):
            screen = self.root.get_screen("main")
            if text is not None: screen.ids.status.text = text
            if progress is not None: screen.ids.progress.value = progress
        Clock.schedule_once(_update)

    def call_gemini(self, api_key, text):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent?key={api_key}"
        prompt = f"Translate the following text to Russian. Keep the style. ONLY translation:\n{text}"
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        
        try:
            r = requests.post(url, json=payload, timeout=30)
            if r.status_code != 200:
                return f"[Ошибка API: {r.status_code}]"
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        except:
            return None

    def start_processing(self):
        key = self.root.get_screen("main").ids.api_key.text.strip()
        if not key:
            self.update_ui(text="⚠️ Вставьте API Key!")
            return
        
        # Сохраняем ключ
        store.put('credentials', key=key)
        self.root.get_screen("main").ids.start_btn.disabled = True
        threading.Thread(target=self.process_pdf, args=(key,), daemon=True).start()

    def process_pdf(self, api_key):
        try:
            doc = fitz.open(self.pdf_path)
            total = len(doc)
            font_path = "font.ttf" # Твой шрифт Roboto
            has_font = os.path.exists(font_path)

            for i, page in enumerate(doc):
                self.update_ui(text=f"Перевод страницы {i+1} из {total}...", progress=(i/total)*100)
                
                blocks = page.get_text("blocks")
                for b in blocks:
                    original_text = b[4].strip()
                    if len(original_text) < 2: continue

                    translated = self.call_gemini(api_key, original_text)
                    if not translated or "[" in translated: continue

                    rect = fitz.Rect(b[:4])
                    page.draw_rect(rect, color=(1,1,1), fill=(1,1,1))
                    
                    try:
                        if has_font:
                            page.insert_textbox(rect, translated, fontname="f1", fontfile=font_path, fontsize=9)
                        else:
                            page.insert_textbox(rect, translated, fontsize=9)
                    except:
                        pass

            output_path = self.pdf_path.replace(".pdf", "_RUSSIAN.pdf")
            doc.save(output_path)
            self.update_ui(text=f"✅ Готово! Файл сохранен рядом.", progress=100)
        
        except Exception as e:
            self.update_ui(text=f"❌ Ошибка: {str(e)}")
        finally:
            Clock.schedule_once(lambda dt: setattr(self.root.get_screen("main").ids.start_btn, 'disabled', False))

if __name__ == "__main__":
    App().run()
