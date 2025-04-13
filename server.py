from flask import Flask, request, send_file, jsonify
import speech_recognition as sr
import requests
from datetime import datetime
import os
import logging
import pytz
from dotenv import load_dotenv
from gtts import gTTS
import tempfile
import time
import re

# инициализация Flask
app = Flask(__name__)

# логирование
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# загрузка переменных окружения
load_dotenv()
OWM_API_KEY = os.getenv("OWM_API_KEY")
EXCHANGE_API_KEY = os.getenv("EXCHANGE_API_KEY")

# настройки времени
TIMEZONE = pytz.timezone("Asia/Yekaterinburg")

# инициализация распознавания речи
recognizer = sr.Recognizer()

# русские названия месяцев и дней недели
months_ru = {
    1: "января", 2: "февраля", 3: "марта", 4: "апреля",
    5: "мая", 6: "июня", 7: "июля", 8: "августа",
    9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"
}

days_ru = {
    0: "понедельник", 1: "вторник", 2: "среда",
    3: "четверг", 4: "пятница", 5: "суббота", 6: "воскресенье"
}

def pcm_to_wav(pcm_data, sample_rate=8000, channels=1, bit_depth=16):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as wav_file:
        # Создание WAV-заголовка
        wav_file.write(b'RIFF')
        wav_file.write((36 + len(pcm_data)).to_bytes(4, byteorder='little'))
        wav_file.write(b'WAVEfmt ')
        wav_file.write((16).to_bytes(4, byteorder='little'))
        wav_file.write((1).to_bytes(2, byteorder='little'))
        wav_file.write((channels).to_bytes(2, byteorder='little'))
        wav_file.write((sample_rate).to_bytes(4, byteorder='little'))
        wav_file.write((sample_rate * channels * bit_depth // 8).to_bytes(4, byteorder='little'))
        wav_file.write((channels * bit_depth // 8).to_bytes(2, byteorder='little'))
        wav_file.write((bit_depth).to_bytes(2, byteorder='little'))
        wav_file.write(b'data')
        wav_file.write((len(pcm_data)).to_bytes(4, byteorder='little'))
        wav_file.write(pcm_data)
        
        return wav_file.name

# функция получения текущего времени
def get_local_time():
    return datetime.now(TIMEZONE)

# функция получения погоды
def get_weather(city="Каменск-Уральский"):
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={OWM_API_KEY}&units=metric&lang=ru"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        
        data = response.json()
        temp = round(data["main"]["temp"])
        weather_desc = data["weather"][0]["description"]
        return f"В городе {city} сейчас {temp} градусов, {weather_desc}."
    
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка запроса погоды: {e}")
        return "Не удалось получить данные о погоде."
    except KeyError as e:
        logger.error(f"Ошибка формата ответа погоды: {e}")
        return "Ошибка обработки данных о погоде."

# функция получения курса валют
def get_currency_rates():
    try:
        url = f"https://v6.exchangerate-api.com/v6/{EXCHANGE_API_KEY}/latest/USD"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        
        data = response.json()
        usd_to_rub = round(data["conversion_rates"]["RUB"], 2)
        usd_to_eur = round(data["conversion_rates"]["EUR"], 2)
        rub_per_eur = round(usd_to_rub / usd_to_eur, 2)
        return f"Курс валют: Доллар {usd_to_rub} рублей, евро {rub_per_eur} рублей."
    
    except Exception as e:
        logger.error(f"Ошибка получения курсов валют: {e}")
        return "Не удалось получить курсы валют."

# функция преобразования текста в речь (MP3)
def text_to_speech(texts):
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    
    # объединяем все ответы с небольшой паузой
    full_text = ". ".join(texts)
    
    tts = gTTS(full_text, lang="ru")
    tts.save(temp_file.name)
    return temp_file.name

# обработчик голосовых команд
@app.route("/voice", methods=["POST"])
def voice_command():
    try:
        # Получение сырых PCM данных
        pcm_data = request.get_data()
        
        print(f"Получено данных: {len(pcm_data)} байт")

        # Конвертация в WAV
        wav_path = pcm_to_wav(pcm_data)
        
        with sr.AudioFile(wav_path) as source:
            audio = recognizer.record(source)
        
        os.unlink(wav_path)
        
        command = recognizer.recognize_google(audio, language="ru-RU").lower()
        logger.info(f"Распознана команда: {command}")
        
        # разбиваем команду на несколько подкоманд
        subcommands = re.split(r'\s+(?:и|,|а также)\s+', command)
        subcommands = [s.strip() for s in subcommands if s.strip()]
        
        responses = []

        # обрабатываем каждую подкоманду
        for subcommand in subcommands:
            cleaned_cmd = re.sub(r'[^\w\s]', '', subcommand.lower())

            if re.search(r'\b(погод[ауы]|погоде)\b', cleaned_cmd):
                responses.append(get_weather())

            elif re.search(r'\b(врем[яи]|час[аы]?|времени)\b', cleaned_cmd):
                responses.append(f"Сейчас {get_local_time().strftime('%H:%M')}.")

            elif re.search(r'\b(дат[ауы]|числ[оа]|день|месяц|год)\b', cleaned_cmd):
                now = get_local_time()
                responses.append(now.strftime(f"Сегодня %d {months_ru[now.month]} %Y года, {days_ru[now.weekday()]}."))
            
            elif re.search(r'\b(курс[аы]? валют|доллар|евро|рубл)\b', cleaned_cmd):
                responses.append(get_currency_rates())

            else:
                responses.append(f"Нe")

        # генерация MP3-ответа
        
        if not responses:
            responses.append("Я не распознал команду.")

        # Генерация MP3
        response_audio_path = text_to_speech(responses)
        return send_file(response_audio_path, mimetype="audio/mpeg")

    except sr.UnknownValueError:
        error_response = ["Я не распознал команду."]
        error_audio = text_to_speech(error_response)
        return send_file(error_audio, mimetype="audio/mpeg")

    except Exception as e:
        logger.error(f"Ошибка: {e}")
        error_audio = text_to_speech("Ошибка сервера")
        return send_file(error_audio, mimetype="audio/mpeg")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)