import re

def normalize_model_name(name: str) -> str:
    name = name.lower().strip()
    name = re.sub(r'\s+', ' ', name)  # убрать лишние пробелы
    name = re.sub(r'[^\w\s]', '', name)  # убрать спецсимволы
    return name
