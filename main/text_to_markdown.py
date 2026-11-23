import re

SKIP_PATTERNS = [
    r'^ИИ-иллюстрация',
    r'^Фото:',
    r'^Реклама',
    r'^Источник:',
    r'^\d+\s*(дн|ч|мин)',
    r'^\d+[\d\s,.]*\s*(тыс|млн)',
]


def clean_text(text: str) -> str:
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        s = line.strip()
        if not s:
            cleaned.append("")
            continue
        if any(re.match(p, s, re.IGNORECASE) for p in SKIP_PATTERNS):
            continue
        cleaned.append(s)
    return "\n".join(cleaned)


def split_paragraphs(text: str) -> list:
    if re.search(r'\n\s*\n', text):
        return [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    paragraphs = []
    current = []
    for s in sentences:
        current.append(s)
        if len(current) >= 3:
            paragraphs.append(" ".join(current))
            current = []
    if current:
        paragraphs.append(" ".join(current))
    return paragraphs


def bold_numbers(text: str) -> str:
    # Даты
    text = re.sub(
        r'(\d{1,2}\s+(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+\d{4})',
        r'**\1**', text,
    )
    # Числа с единицами (включая полные слова)
    text = re.sub(
        r'(?<![\w*])(\d[\d\s.,]*\s*(?:миллиона|миллионов|млн|млрд|тыс|%|лет|года|год|человек|клеток|руб|долларов|евро))',
        lambda m: "**" + m.group(1).rstrip('.,') + "**", text,
    )
    # Отдельные числа от 100: 1828, 1000
    text = re.sub(r'(?<![\w*.])(\d{3,})(?![\w*.])', r'**\1**', text)
    # Годы
    text = re.sub(r'(?<!\*\*)\b(20\d{2})\s+год[ауе]?\b', r'**\1 год**', text)
    return text


def is_list(para: str) -> bool:
    lines = para.split("\n")
    if len(lines) > 1 and sum(1 for l in lines if l.strip().startswith(("—", "-", "•"))) >= 2:
        return True
    return False


def format_list(para: str) -> str:
    out = []
    for line in para.split("\n"):
        line = line.strip()
        if not line:
            continue
        line = re.sub(r'^[—\-•]\s*', '', line)
        out.append("- " + line)
    return "\n".join(out)


def extract_facts(text: str) -> list:
    facts = []
    patterns = [
        (r'изучил[и]?\s+около\s+([^\n.!?]{5,60})', 'Что изучили'),
        (r'полученных от\s+([^\n.!?]{5,40})', 'Выборка'),
        (r'в возрасте от\s+([^\n.!?]{2,30})', 'Возраст участников'),
        (r'в журнале\s+([А-ЯA-Z][^\n.!?]{2,40})', 'Журнал'),
        (r'опубликован[о]?\s+([^\n.!?]{5,40})', 'Дата публикации'),
        (r'пришл[и]?\s+к\s+([^\n.!?]{5,60})', 'Вывод'),
    ]
    for pattern, label in patterns:
        if label in [k for k, _ in facts]:
            continue
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            val = m.group(1).strip().rstrip(".,;")
            if 3 < len(val) < 80:
                facts.append((label, val))
    return facts[:6]


def text_to_markdown(text: str) -> str:
    text = clean_text(text)
    paragraphs = split_paragraphs(text)
    if not paragraphs:
        return ""
    result = [bold_numbers(paragraphs[0]), ""]
    for para in paragraphs[1:]:
        if re.match(r'^[«"]', para) or ('«' in para and '»' in para and len(para) < 400):
            result.extend(["> " + bold_numbers(para), ""])
            continue
        if is_list(para):
            result.extend([format_list(para), ""])
            continue
        result.extend([bold_numbers(para), ""])
    facts = extract_facts(text)
    if facts:
        result.append("## Ключевые факты")
        result.append("")
        result.append("| Параметр | Значение |")
        result.append("|---|---|")
        for k, v in facts:
            result.append("| " + k + " | " + v + " |")
        result.append("")
    return "\n".join(result).strip()


if __name__ == "__main__":
    sample = """Иммунная система человека претерпевает наиболее заметные возрастные изменения примерно в 40 лет и после 60. К такому выводу пришли сингапурские учёные, пишет ScienceAlert.

ИИ-иллюстрация: создано редакцией Life.ru с использованием ChatGPT (OpenAI)

Исследователи из медицинской школы Duke-NUS изучили около 3,8 миллиона иммунных клеток, полученных от 1828 здоровых добровольцев в возрасте от 19 до 97 лет. Участники представляли разные этнические группы.

Учёные анализировали активность генов в отдельных клетках крови и обнаружили два периода особенно выраженных изменений. Первый пришёлся примерно на 40 лет и затронул преимущественно CD4 T-лимфоциты.

Второй пик наблюдался после 60 лет. На этот раз наиболее заметные изменения происходили в CD8 T-лимфоцитах.

«Мы видим отчётливые периоды быстрых изменений», — отметил один из авторов исследования Жак Бемуара.

Научная работа вышла в журнале Nature Communications 21 августа 2026 года."""

    print(text_to_markdown(sample))
