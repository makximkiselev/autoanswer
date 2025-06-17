import re
import emoji
import unicodedata

def normalize_model_name(name: str) -> str:
    name = name.strip()
    name = emoji.replace_emoji(name, replace='')  # удалить все emoji
    name = re.sub(r"^\s*[\U0001F1E6-\U0001F1FF]{2,}", "", name)  # удалить флаги в начале
    name = re.sub(r"^\s*\b[a-zA-Z]{2,3}\b[\s\-:]*", "", name)  # удалить региональный префикс (например, "US-", "TH ", "CH:")
    name = re.sub(r'\s+', ' ', name)  # убрать лишние пробелы
    name = re.sub(r'[^\w\s]', '', name)  # убрать спецсимволы (оставить только буквы/цифры)
    name = name.lower()
    name = unicodedata.normalize("NFKC", name)
    return name