import os
import io
import asyncio
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from PIL import Image, ImageDraw, ImageFont

# =====================================================================
# 1. ЗАГЛУШКА ВЕБ-СЕРВЕРА ДЛЯ RENDER (HEALTH CHECK)
# =====================================================================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"Bot is running 24/7 on Render!")

    def log_message(self, format, *args):
        return  # Отключаем лишний спам в консоли Render

def run_web_server():
    # Render автоматически передает нужный порт в переменную PORT
    port = int(os.getenv("PORT", "10000"))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    print(f"Web server started on port {port} for Render health checks.")
    server.serve_forever()

# =====================================================================
# 2. НАСТРОЙКИ И ИНИЦИАЛИЗАЦИЯ ТЕЛЕГРАМ БОТА
# =====================================================================
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
FONTS_DIR = "fonts"

os.makedirs(FONTS_DIR, exist_ok=True)

bot = Bot(token=TOKEN)
dp = Dispatcher()
user_fonts = {}

# =====================================================================
# 3. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ГЕНЕРАЦИИ КАРТИНКИ
# =====================================================================
def get_available_fonts():
    """Сканирует папку fonts на наличие .ttf файлов"""
    if not os.path.exists(FONTS_DIR):
        return []
    return [f for f in os.listdir(FONTS_DIR) if f.endswith('.ttf')]

def create_text_image(text: str, font_name: str) -> io.BytesIO:
    """Генерация PNG картинки с правильным расчетом размеров текста"""
    font_path = os.path.join(FONTS_DIR, font_name) if font_name else None
    try:
        if font_path and os.path.exists(font_path):
            font = ImageFont.truetype(font_path, 40)
        else:
            font = ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()

    # Временная картинка для точного расчета размеров текста
    dummy_img = Image.new("RGB", (1, 1))
    draw = ImageDraw.Draw(dummy_img)
    
    # multiline_textbbox возвращает кортеж координат (x0, y0, x1, y1)
    bbox = draw.multiline_textbbox((0, 0), text, font=font, spacing=10)
    text_width = bbox[2] - bbox[0]   # ширина = x1 - x0
    text_height = bbox[3] - bbox[1]  # высота = y1 - y0

    padding = 40
    img_width = max(text_width + (padding * 2), 150)
    img_height = max(text_height + (padding * 2), 100)

    # Создаем финальное изображение (Темно-серый фон, белый текст)
    image = Image.new("RGB", (img_width, img_height), (33, 33, 33))
    draw = ImageDraw.Draw(image)
    draw.multiline_text((padding, padding), text, font=font, fill=(255, 255, 255), spacing=10)

    image_buffer = io.BytesIO()
    image.save(image_buffer, format="PNG")
    image_buffer.seek(0)
    return image_buffer

# =====================================================================
# 4. ОБРАБОТЧИКИ КОМАНД И ТЕКСТА
# =====================================================================

@dp.message(F.text == "/start")
async def send_welcome(message: Message):
    """Приветственное сообщение с кнопкой перехода к шрифтам"""
    welcome_text = (
        "👋 **Привет!** Я бот, который превращает твой текст в картинку с красивым шрифтом.\n\n"
        "🔧 **Как мной пользоваться:**\n"
        "1. Нажми на кнопку ниже или введи команду /fonts, чтобы выбрать шрифт.\n"
        "2. Отправь мне любой текст (можно в несколько строк).\n"
        "3. Я пришлю тебе PNG-картинку с этим текстом!"
    )
    
    fonts = get_available_fonts()
    if fonts:
        keyboard = [[InlineKeyboardButton(text="🔤 Открыть меню шрифтов", callback_data="show_fonts")]]
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await message.answer(welcome_text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await message.answer(welcome_text + "\n\n⚠️ _В папке fonts пока нет .ttf шрифтов, добавьте их в свой репозиторий GitHub!_", parse_mode="Markdown")

@dp.message(F.text == "/fonts")
@dp.callback_query(F.data == "show_fonts")
async def list_fonts(message_or_call):
    """Выводит список доступных шрифтов из папки fonts"""
    is_callback = isinstance(message_or_call, CallbackQuery)
    message = message_or_call.message if is_callback else message_or_call
    user_id = message_or_call.from_user.id

    fonts = get_available_fonts()
    if not fonts:
        text = "В папке fonts пока нет .ttf шрифтов. Загрузите файлы в папку fonts на GitHub."
        if is_callback:
            await message_or_call.answer(text, show_alert=True)
        else:
            await message.answer(text)
        return

    keyboard = [[InlineKeyboardButton(text=f, callback_data=f"set_font:{f}")] for f in fonts]
    current = user_fonts.get(user_id, "По умолчанию")
    
    text = f"Ваш текущий шрифт: *{current}*\n\nВыберите новый шрифт из списка ниже:"
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    if is_callback:
        await message.edit_text(text, reply_markup=reply_markup, parse_mode="Markdown")
        await message_or_call.answer()
    else:
        await message.answer(text, reply_markup=reply_markup, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("set_font:"))
async def change_font(callback: CallbackQuery):
    """Сохраняет выбранный шрифт для конкретного пользователя"""
    font_name = callback.data.split(":")[1]
    user_fonts[callback.from_user.id] = font_name
    await callback.answer(f"Выбран шрифт: {font_name}")
    await callback.message.edit_text(f"✅ Активный шрифт изменен на: *{font_name}*\n\nТеперь просто отправьте мне текст.", parse_mode="Markdown")

@dp.message(F.text)
async def handle_text(message: Message):
    """Обрабатывает любой входящий текст и отправляет картинку обратно"""
    if message.text.startswith('/'): 
        return
        
    await bot.send_chat_action(chat_id=message.chat.id, action="upload_photo")
    
    selected_font = user_fonts.get(message.from_user.id)
    if not selected_font:
        available = get_available_fonts()
        selected_font = available[0] if available else None

    # Генерация и отправка фото
    image_data = create_text_image(message.text, selected_font)
    input_file = BufferedInputFile(image_data.read(), filename="text.png")
    await message.answer_photo(photo=input_file)

# =====================================================================
# 5. ЗАПУСК БОТА И СЕРВЕРА
# =====================================================================
async def main():
    # Запуск параллельного потока с веб-сервером для Render
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()

    print("Бот успешно запущен и ожидает сообщений...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    
