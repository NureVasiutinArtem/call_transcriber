import os
import io
import gc
import time
import re
import math
from pydub import AudioSegment
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
import whisper
from rapidfuzz import fuzz

# ---------------- Google Drive Authentication ----------------
SCOPES = ['https://www.googleapis.com/auth/drive']

top100 = [
    "інший варіант", "комплексне ТО", "Компʼютерна діагностика", "Заміна Оливи ДВЗ",
    "Заміна повітряного фільтра ДВЗ", "Заміна сайлентблоків", "слюсарні роботи",
    "Комплексна діагностика", "Заміна фільтру салону", "Заміна масла в АКПП",
    "Заміна амортизатора переднього", "Ендоскопія двигуна", "Заміна свічок запалення",
    "Заміна гальмівних дисків та колодок", "Заміна оливи в передньому | задньому редукторі",
    "Заміна гальмівної рідини з прокачкою", "Заміна лампочки", "Заміна паливного фільтра дизель",
    "Зняття / встановлення важіля прд.", "Замір комрессії", "Замні та замовлення гальмівних колодок",
    "Заміна охолоджуючої рідини", "Заміна стійки стаблізатора переднього", "Заміна амортизатора зд.",
    "Заміна плаваючого сайлентблока.", "Заміна гальмівних дисків та колодок зд.",
    "Заміна фільтра салону в моторному відділенні", "Зняття/встановлення паливних форсунок",
    "Заміна пильовика амортизатора", "Арматурні работи", "Заміна свічок накалу", "Заміна ланцюгів ГРМ",
    "Зняття / встановлення впускного коллектора", "Димогенератор", "пошук підсосів/витоку",
    "Реєстрація заміни АКБку", "Заміна АКБ", "Заміна свічок запалення N55", "Заміна еластичної муфти",
    "Ремонт електропроводки", "Заміна ланцюга ГРМ та масляного насосу N20", "Заміна ремкомплекту рейки",
    "Заміна подушки ДВЗ", "Знаття / встановлення піввісі", "Заміна подушки АКПП",
    "Зняття / встановлення теплообміника", "Знаття / встановлення маслостакана", "Заміна пружини",
    "Зняття / встановлення дверної карти", "Мийка / чистка деталі", "Зняття",
    "встановлення Турбокомпресора", "Заміна Помпи", "Заміна З-х сайлентблоків редуктора",
    "Заміна термостату", "Зняття / встановлення захисту двигуна", "Заміна прокладки маслостакана",
    "Заміна патрубка ОР", "Заміна приводного ремня", "Діагностика ДВЗ", "Зняття / встановлення кардану",
    "Заміна прокладки картера (піддону)", "Заміна КВКГ", "Заміна втулки стабілізатора прд.",
    "Заміна бачка ох. рідини", "Промивка системи охолодження", "Тестер витоку охолоджуючої рідини",
    "Зняття / встановлення вихлопної труби", "Заміна пильовика ШРУСа", "Діагностика течії",
    "Зняття / встановлення переднього бампера", "Заміна датчика", "Заміна переднього сальника колінвалу",
    "Заміна рульвої тяги", "Зняття / встановлення деталі", "Заміна котушки запалювання",
    "Заміна підшипника маточини", "Заміна кульової опори", "Зняття / встановлення інтеркулера",
    "Розборка / зборка гальмівного супорта", "Заміна рульової тяги з наконечником",
    "Зняття / встановлення впускного колектора M57", "Зняття / встановлення дверної ручки",
    "Зняття / встановлення повітряного патрубка", "Заміна клапана Vanos", "Заміна радіатору охолодження",
    "Заміна заднього сальника колінвалу та ремкомплект 8HP", "Заміна датчика кислороду (Лямбда)",
    "Заміна фланця роздавальної коробки", "Протікання води в салон через гідроізоляцію дверних карт",
]

options = [
    "Запис", "Повторно консультація", "Передано іншому філіалу", "Передзвонити", "Інше"
]

# ---------------- Authentication ----------------
def authenticate():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials2.json', SCOPES)
            creds = flow.run_local_server(port=0)

        with open('token.json', 'w') as token_file:
            token_file.write(creds.to_json())

    return creds

# ---------------- Audio Splitting ----------------
def split_audio(file_path, chunk_length_ms=60000):
    audio = AudioSegment.from_file(file_path)
    chunks = []
    num_chunks = math.ceil(len(audio) / chunk_length_ms)

    for i in range(num_chunks):
        start = i * chunk_length_ms
        end = start + chunk_length_ms
        chunk = audio[start:end]
        chunk_name = f"{file_path}_part{i}.wav"
        chunk.export(chunk_name, format="wav")
        chunks.append(chunk_name)

    return chunks

# ---------------- Text Cleaning ----------------
def clean_transcript(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^а-яa-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

# ---------------- Fuzzy Matching ----------------
def fuzzy_match_list(text, patterns, threshold=70):
    return [item for item in patterns if fuzz.partial_ratio(item.lower(), text.lower()) >= threshold]

# ---------------- Analyze Call ----------------
def analyze_call(text: str):
    text = clean_transcript(text)

    keywords = {
        "Вітання": ["доброго дня", "добрий день", "вітаю", "привіт", "здрастуйте", "день добрий", "слухаю вас"],
        "Прощання": ["до побачення", "дякую", "спасибо", "гарного дня", "гарного вечора"],
        "Дізнався_кузов": ["седан", "хетчбек", "універсал", "купе", "кросовер", "bmw", "мерседес", "audi", "фольксваген", "тойота", "мазда", "хонда"],
        "Дізнався_рік": ["рік", "року", "201", "202", "дві тисячі", "випуску", "модельний"],
        "Дізнався_пробіг": ["пробіг", "кілометрів", "тисяч км", "одометр", "накатано"],
        "Запропонував_діагностику": ["діагностика", "перевірка", "огляд", "комплексна", "подивимось", "подивитися"],
        "Дізнався_попередні_роботи": ["робили", "ремонт", "міняли", "заміна", "обслуговування", "замінили"]
    }

    result = {key: int(bool(fuzzy_match_list(text, val, threshold=70))) for key, val in keywords.items()}

    # top100 services
    result["top100"] = fuzzy_match_list(text, top100, threshold=65)

    # options
    result["Статус_дзвінка"] = fuzzy_match_list(text, options, threshold=80) or None

    return result

# ---------------- Whisper Transcription ----------------
model = whisper.load_model("base")

def transcribe_audio(file_path):
    chunks = split_audio(file_path)
    full_text = ""
    for chunk in chunks:
        result = model.transcribe(chunk, language="uk")
        full_text += " " + result['text']
        os.remove(chunk)
    return full_text.strip()

# ---------------- Google Drive ----------------
def download_and_upload_audio(service, source_folder_id, dest_folder_id):
    query = f"'{source_folder_id}' in parents"
    results = service.files().list(q=query, fields="files(id, name, mimeType)").execute()
    files = results.get('files', [])

    for file in files:
        if 'audio' in file['mimeType']:
            file_id = file['id']
            file_name = file['name']
            print(f"⬇️ Downloading: {file_name}")

            request = service.files().get_media(fileId=file_id)
            fh = io.FileIO(file_name, 'wb')
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
            fh.close()

            print(f"📝 Transcribing: {file_name}")
            transcript = transcribe_audio(file_name)
            analysis = analyze_call(transcript)

            print(f"📄 Transcript:\n{transcript}")
            print(f"🔎 Analysis:\n{analysis}")

            print(f"⬆️ Uploading: {file_name}")
            file_metadata = {'name': file_name, 'parents': [dest_folder_id]}
            media = MediaFileUpload(file_name, mimetype=file['mimeType'], resumable=True)
            service.files().create(body=file_metadata, media_body=media, fields='id').execute()

            del media
            gc.collect()
            time.sleep(1)
            os.remove(file_name)
            print(f"✅ Completed processing: {file_name}\n")

# ---------------- Main ----------------
def main():
    creds = authenticate()
    service = build('drive', 'v3', credentials=creds)

    SOURCE_FOLDER_ID = '1dpKG-eaFg2glOovkI4sYgLyPo3mW9Ilg'
    DEST_FOLDER_ID = '1Q1f3nBiMWGbS-qO8P7uAhfNHk4mOU4pT'

    download_and_upload_audio(service, SOURCE_FOLDER_ID, DEST_FOLDER_ID)

if __name__ == '__main__':
    main()










# import os
# import io
# import gc
# import time
# import re
# import math
# from pydub import AudioSegment
# from google.auth.transport.requests import Request
# from google.oauth2.credentials import Credentials
# from google_auth_oauthlib.flow import InstalledAppFlow
# from googleapiclient.discovery import build
# from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
# import whisper
# from rapidfuzz import fuzz

# # ---------------- Google Drive Authentication ----------------
# SCOPES = ['https://www.googleapis.com/auth/drive']

# top100 = [
#     "інший варіант", "комплексне ТО", "Компʼютерна діагностика", "Заміна Оливи ДВЗ",
#     "Заміна повітряного фільтра ДВЗ", "Заміна сайлентблоків", "слюсарні роботи",
#     "Комплексна діагностика", "Заміна фільтру салону", "Заміна масла в АКПП",
#     "Заміна амортизатора переднього", "Ендоскопія двигуна", "Заміна свічок запалення",
#     "Заміна гальмівних дисків та колодок", "Заміна оливи в передньому | задньому редукторі",
#     "Заміна гальмівної рідини з прокачкою", "Заміна лампочки", "Заміна паливного фільтра дизель",
#     "Зняття / встановлення важіля прд.", "Замір комрессії", "Замні та замовлення гальмівних колодок",
#     "Заміна охолоджуючої рідини", "Заміна стійки стаблізатора переднього", "Заміна амортизатора зд.",
#     "Заміна плаваючого сайлентблока.", "Заміна гальмівних дисків та колодок зд.",
#     "Заміна фільтра салону в моторному відділенні", "Зняття/встановлення паливних форсунок",
#     "Заміна пильовика амортизатора", "Арматурні работи", "Заміна свічок накалу", "Заміна ланцюгів ГРМ",
#     "Зняття / встановлення впускного коллектора", "Димогенератор", "пошук підсосів/витоку",
#     "Реєстрація заміни АКБку", "Заміна АКБ", "Заміна свічок запалення N55", "Заміна еластичної муфти",
#     "Ремонт електропроводки", "Заміна ланцюга ГРМ та масляного насосу N20", "Заміна ремкомплекту рейки",
#     "Заміна подушки ДВЗ", "Знаття / встановлення піввісі", "Заміна подушки АКПП",
#     "Зняття / встановлення теплообміника", "Знаття / встановлення маслостакана", "Заміна пружини",
#     "Зняття / встановлення дверної карти", "Мийка / чистка деталі", "Зняття",
#     "встановлення Турбокомпресора", "Заміна Помпи", "Заміна З-х сайлентблоків редуктора",
#     "Заміна термостату", "Зняття / встановлення захисту двигуна", "Заміна прокладки маслостакана",
#     "Заміна патрубка ОР", "Заміна приводного ремня", "Діагностика ДВЗ", "Зняття / встановлення кардану",
#     "Заміна прокладки картера (піддону)", "Заміна КВКГ", "Заміна втулки стабілізатора прд.",
#     "Заміна бачка ох. рідини", "Промивка системи охолодження", "Тестер витоку охолоджуючої рідини",
#     "Зняття / встановлення вихлопної труби", "Заміна пильовика ШРУСа", "Діагностика течії",
#     "Зняття / встановлення переднього бампера", "Заміна датчика", "Заміна переднього сальника колінвалу",
#     "Заміна рульвої тяги", "Зняття / встановлення деталі", "Заміна котушки запалювання",
#     "Заміна підшипника маточини", "Заміна кульової опори", "Зняття / встановлення інтеркулера",
#     "Розборка / зборка гальмівного супорта", "Заміна рульової тяги з наконечником",
#     "Зняття / встановлення впускного колектора M57", "Зняття / встановлення дверної ручки",
#     "Зняття / встановлення повітряного патрубка", "Заміна клапана Vanos", "Заміна радіатору охолодження",
#     "Заміна заднього сальника колінвалу та ремкомплект 8HP", "Заміна датчика кислороду (Лямбда)",
#     "Заміна фланця роздавальної коробки", "Протікання води в салон через гідроізоляцію дверних карт"
# ]

# options = [
#     "Запис", "Повторно консультація", "Передано іншому філіалу", "Передзвонити", "Інше"
# ]

# # ---------------- Authentication ----------------
# def authenticate():
#     creds = None
#     if os.path.exists('token.json'):
#         creds = Credentials.from_authorized_user_file('token.json', SCOPES)

#     if not creds or not creds.valid:
#         if creds and creds.expired and creds.refresh_token:
#             creds.refresh(Request())
#         else:
#             flow = InstalledAppFlow.from_client_secrets_file('credentials2.json', SCOPES)
#             creds = flow.run_local_server(port=0)

#         with open('token.json', 'w') as token_file:
#             token_file.write(creds.to_json())

#     return creds

# # ---------------- Audio Splitting ----------------
# def split_audio(file_path, chunk_length_ms=60000):
#     audio = AudioSegment.from_file(file_path)
#     chunks = []
#     num_chunks = math.ceil(len(audio) / chunk_length_ms)

#     for i in range(num_chunks):
#         start = i * chunk_length_ms
#         end = start + chunk_length_ms
#         chunk = audio[start:end]
#         chunk_name = f"{file_path}_part{i}.wav"
#         chunk.export(chunk_name, format="wav")
#         chunks.append(chunk_name)

#     return chunks

# # ---------------- Text Cleaning ----------------
# def clean_transcript(text: str) -> str:
#     text = text.lower()
#     text = re.sub(r"[^а-яa-z0-9\s]", " ", text)
#     text = re.sub(r"\s+", " ", text).strip()
#     return text

# # ---------------- Fuzzy Matching ----------------
# def fuzzy_match(text, patterns, threshold=70):
#     for pattern in patterns:
#         if fuzz.partial_ratio(pattern.lower(), text.lower()) >= threshold:
#             return True
#     return False

# # ---------------- Analyze Call ----------------
# def analyze_call(text: str):
#     text = clean_transcript(text)

#     keywords = {
#         "Вітання": ["доброго дня", "добрий день", "вітаю", "привіт", "здрастуйте", "день добрий","слухаю вас"],
#         "Прощання": ["до побачення", "дякую", "спасибо", "гарного дня", "гарного вечора"],
#         "Дізнався_кузов": ["седан", "хетчбек", "універсал", "купе", "кросовер", "bmw", "мерседес", "audi", "фольксваген", "тойота", "мазда", "хонда"],
#         "Дізнався_рік": ["рік", "року", "201", "202", "дві тисячі", "випуску", "модельний"],
#         "Дізнався_пробіг": ["пробіг", "кілометрів", "тисяч км", "одометр", "накатано"],
#         "Запропонував_діагностику": ["діагностика", "перевірка", "огляд", "комплексна", "подивимось", "подивитися"],
#         "Дізнався_попередні_роботи": ["робили", "ремонт", "міняли", "заміна", "обслуговування", "замінили"]
#     }

#     result = {key: int(fuzzy_match(text, val)) for key, val in keywords.items()}

#     # top100 services
#     result["top100"] = [item for item in top100 if fuzz.partial_ratio(item.lower(), text) >= 70]

#     # options
#     matched_options = [opt for opt in options if fuzz.partial_ratio(opt.lower(), text) >= 70]
#     result["Статус_дзвінка"] = matched_options if matched_options else None

#     return result

# # ---------------- Whisper Transcription ----------------
# model = whisper.load_model("base")

# def transcribe_audio(file_path):
#     chunks = split_audio(file_path)
#     full_text = ""
#     for chunk in chunks:
#         result = model.transcribe(chunk, language="uk")
#         full_text += " " + result['text']
#         os.remove(chunk)
#     return full_text.strip()

# # ---------------- Google Drive ----------------
# def download_and_upload_audio(service, source_folder_id, dest_folder_id):
#     query = f"'{source_folder_id}' in parents"
#     results = service.files().list(q=query, fields="files(id, name, mimeType)").execute()
#     files = results.get('files', [])

#     for file in files:
#         if 'audio' in file['mimeType']:
#             file_id = file['id']
#             file_name = file['name']
#             print(f"⬇️ Downloading: {file_name}")

#             # Download
#             request = service.files().get_media(fileId=file_id)
#             fh = io.FileIO(file_name, 'wb')
#             downloader = MediaIoBaseDownload(fh, request)
#             done = False
#             while not done:
#                 status, done = downloader.next_chunk()
#             fh.close()

#             # Transcribe & Analyze
#             print(f"📝 Transcribing: {file_name}")
#             transcript = transcribe_audio(file_name)
#             analysis = analyze_call(transcript)

#             print(f"📄 Transcript:\n{transcript}")
#             print(f"🔎 Analysis:\n{analysis}")

#             # Upload to destination
#             print(f"⬆️ Uploading: {file_name}")
#             file_metadata = {'name': file_name, 'parents': [dest_folder_id]}
#             media = MediaFileUpload(file_name, mimetype=file['mimeType'], resumable=True)
#             service.files().create(body=file_metadata, media_body=media, fields='id').execute()

#             # Cleanup
#             del media
#             gc.collect()
#             time.sleep(1)
#             os.remove(file_name)
#             print(f"✅ Completed processing: {file_name}\n")

# # ---------------- Main ----------------
# def main():
#     creds = authenticate()
#     service = build('drive', 'v3', credentials=creds)

#     SOURCE_FOLDER_ID = '1dpKG-eaFg2glOovkI4sYgLyPo3mW9Ilg'
#     DEST_FOLDER_ID = '1Q1f3nBiMWGbS-qO8P7uAhfNHk4mOU4pT'

#     download_and_upload_audio(service, SOURCE_FOLDER_ID, DEST_FOLDER_ID)

# if __name__ == '__main__':
#     main()


























# import os
# import io
# import gc
# import time
# import re
# import math
# from pydub import AudioSegment
# from google.auth.transport.requests import Request
# from google.oauth2.credentials import Credentials
# from google_auth_oauthlib.flow import InstalledAppFlow
# from googleapiclient.discovery import build
# from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
# import whisper
# from rapidfuzz import fuzz

# # ---------------- Google Drive Authentication ----------------
# SCOPES = ['https://www.googleapis.com/auth/drive']

# top100 = [
#   "інший варіант",
#   "комплексне ТО",
#   "Компʼютерна діагностика",
#   "Заміна Оливи ДВЗ",
#   "Заміна повітряного фільтра ДВЗ",
#   "Заміна сайлентблоків",
#   "слюсарні роботи",
#   "Комплексна діагностика",
#   "Заміна фільтру салону",
#   "Заміна масла в АКПП",
#   "Заміна амортизатора переднього",
#   "Ендоскопія двигуна",
#   "Заміна свічок запалення",
#   "Заміна гальмівних дисків та колодок",
#   "Заміна оливи в передньому | задньому редукторі",
#   "Заміна гальмівної рідини з прокачкою",
#   "Заміна лампочки",
#   "Заміна паливного фільтра дизель",
#   "Зняття / встановлення важіля прд.",
#   "Замір комрессії",
#   "Замні та замовлення гальмівних колодок",
#   "Заміна охолоджуючої рідини",
#   "Заміна стійки стаблізатора переднього",
#   "Заміна амортизатора зд.",
#   "Заміна плаваючого сайлентблока.",
#   "Заміна гальмівних дисків та колодок зд.",
#   "Заміна фільтра салону в моторному відділенні",
#   "Зняття/встановлення паливних форсунок",
#   "Заміна пильовика амортизатора",
#   "Арматурні работи",
#   "Заміна свічок накалу",
#   "Заміна ланцюгів ГРМ",
#   "Зняття / встановлення впускного коллектора",
#   "Димогенератор",
#   "пошук підсосів/витоку",
#   "Реєстрація заміни АКБку",
#   "Заміна АКБ",
#   "Заміна свічок запалення N55",
#   "Заміна еластичної муфти",
#   "Ремонт електропроводки",
#   "Заміна ланцюга ГРМ та масляного насосу N20",
#   "Заміна ремкомплекту рейки",
#   "Заміна подушки ДВЗ",
#   "Знаття / встановлення піввісі",
#   "Заміна подушки АКПП",
#   "Зняття / встановлення теплообміника",
#   "Знаття / встановлення маслостакана",
#   "Заміна пружини",
#   "Зняття / встановлення дверної карти",
#   "Мийка / чистка деталі",
#   "Зняття",
#   "встановлення Турбокомпресора",
#   "Заміна помпи",
#   "Заміна З-х сайлентблоків редуктора",
#   "Заміна термостату",
#   "Зняття / встановлення захисту двигуна",
#   "Заміна прокладки маслостакана",
#   "Заміна патрубка ОР",
#   "Заміна приводного ремня",
#   "Діагностика ДВЗ",
#   "Зняття / встановлення кардану",
#   "Заміна прокладки картера (піддону)",
#   "Заміна КВКГ",
#   "Заміна втулки стабілізатора прд.",
#   "Заміна бачка ох. рідини",
#   "Промивка системи охолодження",
#   "Тестер витоку охолоджуючої рідини",
#   "Зняття / встановлення вихлопної труби",
#   "Заміна пильовика ШРУСа",
#   "Діагностика течії",
#   "Зняття / встановлення переднього бампера",
#   "Заміна датчика",
#   "Заміна переднього сальника колінвалу",
#   "Заміна рульвої тяги",
#   "Зняття / встановлення деталі",
#   "Заміна котушки запалювання",
#   "Заміна підшипника маточини",
#   "Заміна кульової опори",
#   "Зняття / встановлення інтеркулера",
#   "Розборка / зборка гальмівного супорта",
#   "Заміна рульової тяги з наконечником",
#   "Зняття / встановлення впускного колектора M57",
#   "Зняття / встановлення дверної ручки",
#   "Зняття / встановлення повітряного патрубка",
#   "Заміна клапана Vanos",
#   "Заміна радіатору охолодження",
#   "Заміна заднього сальника колінвалу та ремкомплект 8HP",
#   "Заміна датчика кислороду (Лямбда)",
#   "Заміна фланця роздавальної коробки",
#   "Протікання води в салон через гідроізоляцію дверних карт"
# ]
# options = [
#     "Запис",
#     "Повторно консультація",
#     "Передано іншому філіалу",
#     "Передзвонити",
#     "Інше"
# ]
# def authenticate():
#     creds = None
#     if os.path.exists('token.json'):
#         creds = Credentials.from_authorized_user_file('token.json', SCOPES)

#     if not creds or not creds.valid:
#         if creds and creds.expired and creds.refresh_token:
#             creds.refresh(Request())
#         else:
#             flow = InstalledAppFlow.from_client_secrets_file('credentials2.json', SCOPES)
#             creds = flow.run_local_server(port=0)

#         with open('token.json', 'w') as token_file:
#             token_file.write(creds.to_json())

#     return creds


# # ---------------- Audio Splitting ----------------
# def split_audio(file_path, chunk_length_ms=60000):  # 60 секунд = 1 хвилина
#     audio = AudioSegment.from_file(file_path)
#     chunks = []
#     num_chunks = math.ceil(len(audio) / chunk_length_ms)

#     for i in range(num_chunks):
#         start = i * chunk_length_ms
#         end = start + chunk_length_ms
#         chunk = audio[start:end]
#         chunk_name = f"{file_path}_part{i}.wav"
#         chunk.export(chunk_name, format="wav")
#         chunks.append(chunk_name)

#     return chunks


# # ---------------- Audio Transcription ----------------
# model = whisper.load_model("base")  # base модель для скорости и стабильности

# def transcribe_audio(file_path):
#     chunks = split_audio(file_path)
#     full_text = ""

#     for chunk in chunks:
#         result = model.transcribe(chunk, language="uk")
#         full_text += " " + result['text']
#         os.remove(chunk)  # удаляем временные файлы

#     return full_text.strip()


# # ---------------- Text Cleaning ----------------
# def clean_transcript(text: str) -> str:
#     text = text.lower()
#     text = re.sub(r"[^а-яa-z0-9\s]", " ", text)
#     text = re.sub(r"\s+", " ", text).strip()
#     return text


# # ---------------- Fuzzy Analysis ----------------
# def fuzzy_match(text, patterns, threshold=70):
#     for pattern in patterns:
#         if fuzz.partial_ratio(pattern, text) >= threshold:
#             return True
#     return False

# def analyze_call(text: str):
#     text = clean_transcript(text)

#     keywords = {
#         "Вітання": ["доброго дня", "добрий день", "вітаю", "привіт", "здрастуйте", "день добрий","день добрий","слухаю вас"],
#         "Прощання": ["до побачення", "дякую", "спасибо", "гарного дня", "гарного вечора"],
#         "Дізнався_кузов": [
#             "седан", "хетчбек", "універсал", "купе", "кросовер", 
#             "bmw", "мерседес", "audi", "фольксваген", "тойота", "мазда", "хонда"
#         ],
#         "Дізнався_рік": ["рік", "року", "201", "202", "дві тисячі", "випуску", "модельний"],
#         "Дізнався_пробіг": ["пробіг", "кілометрів", "тисяч км", "одометр", "накатано"],
#         "Запропонував_діагностику": ["діагностика", "перевірка", "огляд", "комплексна", "подивимось", "подивитися"],
#         "Дізнався_попередні_роботи": ["робили", "ремонт", "міняли", "заміна", "обслуговування", "замінили"]
#     }

#     return {key: int(fuzzy_match(text, val)) for key, val in keywords.items()}


# # ---------------- Drive Download & Upload ----------------
# def download_and_upload_audio(service, source_folder_id, dest_folder_id):
#     query = f"'{source_folder_id}' in parents"
#     results = service.files().list(q=query, fields="files(id, name, mimeType)").execute()
#     files = results.get('files', [])

#     for file in files:
#         if 'audio' in file['mimeType']:
#             file_id = file['id']
#             file_name = file['name']
#             print(f"⬇️ Downloading: {file_name}")

#             # Download file
#             request = service.files().get_media(fileId=file_id)
#             fh = io.FileIO(file_name, 'wb')
#             downloader = MediaIoBaseDownload(fh, request)
#             done = False
#             while not done:
#                 status, done = downloader.next_chunk()
#             fh.close()

#             # Transcribe and analyze
#             print(f"📝 Transcribing: {file_name}")
#             transcript = transcribe_audio(file_name)
#             analysis = analyze_call(transcript)

#             print(f"📄 Transcript:\n{transcript}")
#             print(f"🔎 Analysis:\n{analysis}")

#             # Upload to destination folder
#             print(f"⬆️ Uploading to destination folder: {file_name}")
#             file_metadata = {'name': file_name, 'parents': [dest_folder_id]}
#             media = MediaFileUpload(file_name, mimetype=file['mimeType'], resumable=True)
#             service.files().create(body=file_metadata, media_body=media, fields='id').execute()

#             # Cleanup
#             del media
#             gc.collect()
#             time.sleep(1)
#             os.remove(file_name)
#             print(f"✅ Completed processing: {file_name}\n")


# # ---------------- Main ----------------
# def main():
#     creds = authenticate()
#     service = build('drive', 'v3', credentials=creds)

#     SOURCE_FOLDER_ID = '1dpKG-eaFg2glOovkI4sYgLyPo3mW9Ilg'  # исходная папка
#     DEST_FOLDER_ID = '1Q1f3nBiMWGbS-qO8P7uAhfNHk4mOU4pT'    # папка назначения

#     download_and_upload_audio(service, SOURCE_FOLDER_ID, DEST_FOLDER_ID)

# if __name__ == '__main__':
#     main()












# import os
# import io
# import gc
# import time
# import re
# from google.auth.transport.requests import Request
# from google.oauth2.credentials import Credentials
# from google_auth_oauthlib.flow import InstalledAppFlow
# from googleapiclient.discovery import build
# from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
# import whisper
# from rapidfuzz import fuzz

# # ---------------- Google Drive Authentication ----------------
# SCOPES = ['https://www.googleapis.com/auth/drive']

# def authenticate():
#     creds = None
#     if os.path.exists('token.json'):
#         creds = Credentials.from_authorized_user_file('token.json', SCOPES)

#     if not creds or not creds.valid:
#         if creds and creds.expired and creds.refresh_token:
#             creds.refresh(Request())
#         else:
#             flow = InstalledAppFlow.from_client_secrets_file('credentials2.json', SCOPES)
#             creds = flow.run_local_server(port=0)

#         with open('token.json', 'w') as token_file:
#             token_file.write(creds.to_json())

#     return creds

# # ---------------- Audio Transcription ----------------
# model = whisper.load_model("base")  # base модель для скорости

# def transcribe_audio(file_path):
#     result = model.transcribe(file_path, language="uk")
#     return result['text']

# # ---------------- Text Cleaning ----------------
# def clean_transcript(text: str) -> str:
#     """
#     Очистка и нормализация транскрипта:
#     - Lowercase
#     - Убираем спецсимволы и мусор
#     - Сжимаем пробелы
#     """
#     text = text.lower()
#     text = re.sub(r"[^а-яa-z0-9\s]", " ", text)
#     text = re.sub(r"\s+", " ", text).strip()
#     return text

# # ---------------- Fuzzy Analysis ----------------
# def fuzzy_match(text, patterns, threshold=70):
#     for pattern in patterns:
#         if fuzz.partial_ratio(pattern, text) >= threshold:
#             return True
#     return False

# def analyze_call(text: str):
#     text = clean_transcript(text)

#     keywords = {
#         "Вітання": ["доброго дня", "добрий день", "вітаю", "привіт", "здрастуйте", "день добрий"],
#         "Прощання": ["до побачення", "дякую", "спасибо","гарного дня","гарного вечора "],
#         "Дізнався_кузов": [
#             "седан", "хетчбек", "універсал", "купе", "кросовер", 
#             "bmw", "мерседес", "audi", "фольксваген", "тойота", "мазда", "хонда"
#         ],
#         "Дізнався_рік": ["рік", "року", "201", "202", "дві тисячі", "випуску", "модельний"],
#         "Дізнався_пробіг": ["пробіг", "кілометрів", "тисяч км", "одометр", "накатано"],
#         "Запропонував_діагностику": ["діагностика", "перевірка", "огляд", "комплексна", "подивимось", "подивитися"],
#         "Дізнався_попередні_роботи": ["робили", "ремонт", "міняли", "заміна", "обслуговування", "замінили"]
#     }

#     return {key: int(fuzzy_match(text, val)) for key, val in keywords.items()}

# # ---------------- Drive Download & Upload ----------------
# def download_and_upload_audio(service, source_folder_id, dest_folder_id):
#     query = f"'{source_folder_id}' in parents"
#     results = service.files().list(q=query, fields="files(id, name, mimeType)").execute()
#     files = results.get('files', [])

#     for file in files:
#         if 'audio' in file['mimeType']:
#             file_id = file['id']
#             file_name = file['name']
#             print(f"⬇️ Downloading: {file_name}")

#             # Download file
#             request = service.files().get_media(fileId=file_id)
#             fh = io.FileIO(file_name, 'wb')
#             downloader = MediaIoBaseDownload(fh, request)
#             done = False
#             while not done:
#                 status, done = downloader.next_chunk()
#             fh.close()

#             # Transcribe and analyze
#             print(f"📝 Transcribing: {file_name}")
#             transcript = transcribe_audio(file_name)
#             analysis = analyze_call(transcript)

#             print(f"📄 Transcript:\n{transcript}")
#             print(f"🔎 Analysis:\n{analysis}")

#             # Upload to destination folder
#             print(f"⬆️ Uploading to destination folder: {file_name}")
#             file_metadata = {'name': file_name, 'parents': [dest_folder_id]}
#             media = MediaFileUpload(file_name, mimetype=file['mimeType'], resumable=True)
#             service.files().create(body=file_metadata, media_body=media, fields='id').execute()

#             # Cleanup
#             del media
#             gc.collect()
#             time.sleep(1)
#             os.remove(file_name)
#             print(f"✅ Completed processing: {file_name}\n")

# # ---------------- Main ----------------
# def main():
#     creds = authenticate()
#     service = build('drive', 'v3', credentials=creds)

#     SOURCE_FOLDER_ID = '1dpKG-eaFg2glOovkI4sYgLyPo3mW9Ilg'  # исходная папка
#     DEST_FOLDER_ID = '1Q1f3nBiMWGbS-qO8P7uAhfNHk4mOU4pT'    # папка назначения

#     download_and_upload_audio(service, SOURCE_FOLDER_ID, DEST_FOLDER_ID)

# if __name__ == '__main__':
#     main()




























# import os
# import io
# import gc
# import time
# from google.auth.transport.requests import Request
# from google.oauth2.credentials import Credentials
# from google_auth_oauthlib.flow import InstalledAppFlow
# from googleapiclient.discovery import build
# from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
# import whisper
# from rapidfuzz import fuzz, process



# SCOPES = ['https://www.googleapis.com/auth/drive']

# def authenticate():
#     creds = None
#     if os.path.exists('token.json'):
#         creds = Credentials.from_authorized_user_file('token.json', SCOPES)

#     if not creds or not creds.valid:
#         if creds and creds.expired and creds.refresh_token:
#             creds.refresh(Request())
#         else:
#             flow = InstalledAppFlow.from_client_secrets_file('credentials2.json', SCOPES)
#             creds = flow.run_local_server(port=0)

#         with open('token.json', 'w') as token_file:
#             token_file.write(creds.to_json())

#     return creds

# # def analyze_call(text):
# #     data = {
# #         "Вітання": int(any(word in text.lower() for word in ["доброго дня", "доброго", "вітаю",])),
# #         "Дізнався_кузов": int(any(word in text.lower() for word in ["седан", "хетчбек", "універсал", "кузов"])),
# #         "Дізнався_рік": int(any(word in text.lower() for word in ["рік", "року", "дві тисячі"])),
# #         "Дізнався_пробіг": int(any(word in text.lower() for word in ["пробіг", "тисяч км", "кілометрів"])),
# #         "Запропонував_діагностику": int(any(word in text.lower() for word in ["діагностика", "перевірка", "огляд"])),
# #         "Дізнався_попередні_роботи": int(any(word in text.lower() for word in ["робили", "ремонт", "міняли", "заміна"])),
# #     }
# #     return data

# def analyze_call(text: str):
#     text = text.lower()

#     keywords = {
#         "Вітання": [
#             "доброго дня", "добрий день", "вітаю", "привіт", "здрастуйте", "доброго", "день добрий"
#         ],
#         "Дізнався_кузов": [
#             # кузова
#             "седан", "хетчбек", "універсал", "купе", "кабріолет", "родстер", 
#             "кросовер", "джип", "внедорожник", "пікап", "мінівен", "фургон", "лімузин",
#             # марки
#             "бмв", "bmw", "мерседес", "audi", "фольксваген", "тойота", "мазда", "хонда",
#             "лексус", "ніссан", "форд", "опель", "рено", "пежо", "кіа", "хюндай", "шкода",
#             # модели
#             "x1", "x3", "x5", "540", "520", "530", "e220", "e350", "camry", "rav4"
#         ],
#         "Дізнався_рік": [
#             "рік", "року", "випуску", "модельний", "дві тисячі", "200", "201", "202"
#         ],
#         "Дізнався_пробіг": [
#             "пробіг", "кілометрів", "тисяч км", "одометр", "накатано"
#         ],
#         "Запропонував_діагностику": [
#             "діагностика", "перевірка", "огляд", "подивимось", "подивитися", "комплексна"
#         ],
#         "Дізнався_попередні_роботи": [
#             "робили", "ремонт", "міняли", "заміна", "замінили", "робота", "обслуговування"
#         ]
#     }
#     def fuzzy_match(text, patterns, threshold=80):
#         for pattern in patterns:
#             if fuzz.partial_ratio(pattern, text) >= threshold:
#                 return True
#         return False

#     data = {key: int(fuzzy_match(text, val)) for key, val in keywords.items()}
#     return data



# model = whisper.load_model("base") 
# def transcribe_audio(file_path):
#     result = model.transcribe(file_path,language="uk")
#     return result['text']


# def download_and_upload_audio(service, source_folder_id, dest_folder_id):
#     query = f"'{source_folder_id}' in parents"
#     results = service.files().list(q=query, fields="files(id, name, mimeType)").execute()
#     files = results.get('files', [])

#     for file in files:
#         if 'audio' in file['mimeType']:
#             file_id = file['id']
#             file_name = file['name']
#             print(f"⬇️ Downloading: {file_name}")

#             request = service.files().get_media(fileId=file_id)
#             fh = io.FileIO(file_name, 'wb')
#             downloader = MediaIoBaseDownload(fh, request)

#             done = False
#             while not done:
#                 status, done = downloader.next_chunk()
#             fh.close()

#             print(f"⬆️ Uploading to destination folder: {file_name}")
#             file_metadata = {'name': file_name, 'parents': [dest_folder_id]}
#             media = MediaFileUpload(file_name, mimetype=file['mimeType'], resumable=True)
#             service.files().create(body=file_metadata, media_body=media, fields='id').execute()

#             print(f"📝 Transcribing: {file_name}")
#             transcript = transcribe_audio(file_name)
#             analize = analyze_call(transcript)
#             print(analize)

#             print(f"📄 Transcript:\n{transcript}") 

#             # Очистка, чтобы освободить файл перед удалением
#             del media
#             gc.collect()
#             time.sleep(1)

#             os.remove(file_name)
#             print(f"✅ Completed processing: {file_name}")

# def main():
#     creds = authenticate()
#     service = build('drive', 'v3', credentials=creds)

#     SOURCE_FOLDER_ID = '1dpKG-eaFg2glOovkI4sYgLyPo3mW9Ilg'  # Папка с исходными файлами
#     DEST_FOLDER_ID = '1Q1f3nBiMWGbS-qO8P7uAhfNHk4mOU4pT'    # Папка для загрузки

#     download_and_upload_audio(service, SOURCE_FOLDER_ID, DEST_FOLDER_ID)

# if __name__ == '__main__':
#     main()

