import re
import time
import uuid

import requests
from bs4 import BeautifulSoup

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile

from .models import Post, Category, Tag
from .text_to_markdown import text_to_markdown

BASE_URL = "https://lenta.ru/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0 Safari/537.36"
}
PHOTO_CAPTION_PATTERNS = [
    r'^Фото:',
    r'^Иллюстрация:',
    r'^Изображение:',
    r'^Picture:',
    r'^Image:',
]


def is_photo_caption(text):
    return any(re.match(p, text.strip(), re.IGNORECASE) for p in PHOTO_CAPTION_PATTERNS)


def get_news_links():
    """Собирает ссылки на новости с главной страницы (только lenta.ru)."""
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
    """Парсит заголовок, текст, Markdown и URL обложки."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        response.encoding = "utf-8"
        soup = BeautifulSoup(response.text, "html.parser")

        # 1. Заголовок
        title_tag = soup.find("h1", class_="topic-body__titles")
        title = title_tag.get_text(strip=True) if title_tag else "Заголовок не найден"

        # 2. Текст статьи (без подписей к фото)
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

        # 3. Markdown-версия
        text_md = text_to_markdown(text) if text != "Текст статьи не найден" else ""

        # 4. URL обложки (picture__image — чистое фото без заголовка)
        cover_url = ""
        img_tag = soup.find("img", class_="picture__image")
        if img_tag:
            src = img_tag.get("src") or img_tag.get("data-src")
            if src:
                cover_url = requests.compat.urljoin(url, src)

        return {
            "title": title,
            "text_md": text_md,
            "cover_url": cover_url,
        }
    except Exception as e:
        print(f"  ❌ Ошибка при парсинге {url}: {e}")
        return None


def get_or_create_default_category():
    """Создаёт (или находит) категорию «Новости»."""
    category, _ = Category.objects.get_or_create(
        name="Новости",
        defaults={'slug': 'novosti'},
    )
    return category


def get_or_create_default_tags():
    """Создаёт (или находит) базовые теги."""
    tag_names = ["новости", "Lenta.ru", "Россия", "мир"]
    tags = []
    for name in tag_names:
        tag, _ = Tag.objects.get_or_create(name=name)
        tags.append(tag)
    return tags


def import_news_to_django(author_username="sulik"):
    """Основная функция: парсит новости и сохраняет как черновики в БД."""
    User = get_user_model()
    try:
        author = User.objects.get(username=author_username)
    except User.DoesNotExist:
        print(f"❌ Пользователь {author_username} не найден в базе!")
        return

    # Категория и теги по умолчанию
    default_category = get_or_create_default_category()
    default_tags = get_or_create_default_tags()
    print(f"📂 Категория: {default_category.name}")
    print(f"🏷️  Теги: {', '.join(t.name for t in default_tags)}\n")

    print(f"Собираем ссылки с {BASE_URL}...")
    links = get_news_links()
    print(f"Найдено ссылок: {len(links)}\n")

    created_count = 0
    for i, link in enumerate(links, 1):
        print(f"[{i}/{len(links)}] {link}")
        article = parse_article(link)

        if not article:
            continue

        # Проверка на дубликат (по заголовку)
        if Post.objects.filter(title=article['title']).exists():
            print("  ⏩ Статья уже есть в базе, пропускаем.")
            continue

        # Создаём объект поста (пока без сохранения)
        post = Post(
            title=article['title'],
            content=article['text_md'],
            excerpt=article['text_md'][:200] + "...",
            author=author,
            status='draft',
            category=default_category,
        )

        # Скачиваем обложку (если есть URL)
        if article['cover_url']:
            try:
                img_response = requests.get(article['cover_url'], headers=HEADERS, timeout=10)
                img_response.raise_for_status()

                # Уникальное имя файла
                ext = article['cover_url'].split('.')[-1].split('?')[0]
                if ext.lower() not in ('jpg', 'jpeg', 'png', 'gif', 'webp'):
                    ext = 'jpg'
                filename = f"{uuid.uuid4().hex}.{ext}"

                # Сохраняем в поле cover, но пока не пишем в БД (save=False)
                post.cover.save(filename, ContentFile(img_response.content), save=False)
                print("  🖼️  Обложка скачана.")
            except Exception as e:
                print(f"  ⚠️  Не удалось скачать обложку: {e}")

        # Сохраняем пост в БД
        try:
            post.save()
            # Теги (ManyToMany) — только после save()
            post.tags.set(default_tags)
            created_count += 1
            print("  ✅ Сохранено как черновик (с обложкой и тегами).")
        except Exception as e:
            print(f"  ❌ Ошибка БД: {e}")

        time.sleep(2)

    print(f"\n🎉 Импорт завершён! Создано черновиков: {created_count}")
