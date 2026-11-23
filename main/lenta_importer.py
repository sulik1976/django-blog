import re
import time
import requests
from bs4 import BeautifulSoup
from django.contrib.auth import get_user_model
from .models import Post
from .text_to_markdown import text_to_markdown

BASE_URL = "https://lenta.ru/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0 Safari/537.36"
}
PHOTO_CAPTION_PATTERNS = [r'^Фото:', r'^Иллюстрация:', r'^Изображение:']


def is_photo_caption(text):
    return any(re.match(p, text.strip(), re.IGNORECASE) for p in PHOTO_CAPTION_PATTERNS)


def get_news_links():
    response = requests.get(BASE_URL, headers=HEADERS, timeout=10)
    response.raise_for_status()
    response.encoding = "utf-8"
    soup = BeautifulSoup(response.text, "html.parser")

    news_items = soup.find_all("a", class_="card-mini")
    if not news_items:
        news_items = soup.find_all("a", href=lambda h: h and "/news/" in h)

    links = []
    seen = set()
    for item in news_items:
        link = item.get("href")
        if not link or link in seen:
            continue
        full_link = requests.compat.urljoin(BASE_URL, link)
        if full_link.startswith("https://lenta.ru/news/"):
            links.append(full_link)
            seen.add(link)
    return links[:10]


def parse_article(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        response.encoding = "utf-8"
        soup = BeautifulSoup(response.text, "html.parser")

        title_tag = soup.find("h1", class_="topic-body__titles")
        title = title_tag.get_text(strip=True) if title_tag else "Заголовок не найден"

        paragraphs = soup.find_all("p", class_="topic-body__content-text")
        text_parts = []
        for p in paragraphs:
            txt = p.get_text(separator=" ", strip=True)
            if txt and not is_photo_caption(txt):
                text_parts.append(txt)

        text = "\n\n".join(text_parts)
        text = re.sub(r'[ \t]+', ' ', text)

        if not text:
            text = "Текст статьи не найден"

        text_md = text_to_markdown(text) if text != "Текст статьи не найден" else ""

        return {"title": title, "text_md": text_md}
    except Exception as e:
        print(f"  Ошибка при парсинге {url}: {e}")
        return None


def import_news_to_django(author_username="sulik"):
    """
    Основная функция импорта.
    Берет автора, парсит новости и сохраняет их как черновики в БД.
    """
    User = get_user_model()
    try:
        author = User.objects.get(username=author_username)
    except User.DoesNotExist:
        print(f"❌ Пользователь {author_username} не найден в базе!")
        return

    print(f"Собираем ссылки с {BASE_URL}...")
    links = get_news_links()
    print(f"Найдено ссылок: {len(links)}\n")

    created_count = 0
    for i, link in enumerate(links, 1):
        print(f"[{i}/{len(links)}] Парсим и сохраняем: {link}")
        article = parse_article(link)
        
        if not article:
            continue

        # Проверка, нет ли уже такой статьи (по заголовку)
        if Post.objects.filter(title=article['title']).exists():
            print("  ⏩ Статья уже есть в базе, пропускаем.")
            continue

        # Создаем черновик
        try:
            Post.objects.create(
                title=article['title'],
                content=article['text_md'],
                excerpt=article['text_md'][:200] + "...", # обрезаем для краткого описания
                author=author,
                status='draft', # Важно: сохраняем как черновик!
            )
            created_count += 1
            print("  ✅ Сохранено как черновик.")
        except Exception as e:
            print(f"  ❌ Ошибка БД: {e}")
            
        time.sleep(2)

    print(f"\n🎉 Импорт завершен! Создано черновиков: {created_count}")
