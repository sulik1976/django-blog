import re
import time
import uuid

import requests
from bs4 import BeautifulSoup
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile

from .models import Post, Category, Tag
from .text_to_markdown import text_to_markdown

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0 Safari/537.36"
}

SITES = {
    "lenta": {
        "name": "Lenta.ru",
        "base_url": "https://lenta.ru/",
        "link_filter": "https://lenta.ru/news/",
        "link_tag": ("a", "card-mini"),
        "title_tag": ("h1", "topic-body__titles"),
        "text_tag": ("p", "topic-body__content-text"),
        "cover_tag": ("img", "picture__image"),
    },
    "rbc": {
        "name": "РБК",
        "base_url": "https://www.rbc.ru/",
        "link_filter": "/politics/|/society/|/economics/|/finance/|/world/",
        "link_tag": ("a", "news-line-link"),
        "title_tag": ("h1", "article-entry-title"),
        "text_tag": ("p", "paragraph"),
        "cover_tag": ("img", "picture-image"), # У РБК картинка в теге с этим классом
    }
}

PHOTO_CAPTION_PATTERNS = [r'^Фото:', r'^Иллюстрация:', r'^Изображение:', r'^Picture:']

def is_photo_caption(text):
    return any(re.match(p, text.strip(), re.IGNORECASE) for p in PHOTO_CAPTION_PATTERNS)


def get_news_links(site_key):
    config = SITES[site_key]
    response = requests.get(config["base_url"], headers=HEADERS, timeout=10)
    response.raise_for_status()
    response.encoding = "utf-8"
    soup = BeautifulSoup(response.text, "html.parser")

    tag_name, class_name = config["link_tag"]
    news_items = soup.find_all(tag_name, class_=class_name)
    
    links = []
    seen = set()
    for item in news_items:
        link = item.get("href")
        if not link or link in seen:
            continue
        
        if site_key == "lenta" and not link.startswith(config["link_filter"]):
            continue
        if site_key == "rbc" and not re.search(config["link_filter"], link):
            continue

        full_link = requests.compat.urljoin(config["base_url"], link)
        links.append(full_link)
        seen.add(link)

    return links[:10]


def parse_article(url, site_key):
    config = SITES[site_key]
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        response.encoding = "utf-8"
        soup = BeautifulSoup(response.text, "html.parser")

        # Заголовок
        title_tag = soup.find(config["title_tag"][0], class_=config["title_tag"][1])
        title = title_tag.get_text(strip=True) if title_tag else "Заголовок не найден"

        # Текст
        paragraphs = soup.find_all(config["text_tag"][0], class_=config["text_tag"][1])
        text_parts = []
        for p in paragraphs:
            txt = p.get_text(separator=" ", strip=True)
            if txt and not is_photo_caption(txt):
                text_parts.append(txt)

        text = "\n\n".join(text_parts)
        text = re.sub(r'[ \t]+', ' ', text)
        if not text:
            text = "Текст статьи не найден"

        # Markdown
        text_md = text_to_markdown(text) if text != "Текст статьи не найден" else ""

        # Обложка (ищем тег img, потом фолбэк на og:image)
        cover_url = ""
        img_tag = soup.find(config["cover_tag"][0], class_=config["cover_tag"][1])
        if img_tag:
            src = img_tag.get("src") or img_tag.get("data-src")
            if src:
                cover_url = requests.compat.urljoin(url, src)
        
        # Если картинку в теге не нашли — пробуем мета-тег
        if not cover_url:
            og_img = soup.find("meta", property="og:image")
            if og_img and og_img.get("content"):
                cover_url = og_img["content"]

        return {"title": title, "text_md": text_md, "cover_url": cover_url}
    except Exception as e:
        print(f"  ❌ Ошибка при парсинге {url}: {e}")
        return None


def get_or_create_default_category():
    category, _ = Category.objects.get_or_create(name="Новости", defaults={'slug': 'novosti'})
    return category

def get_or_create_default_tags(site_name):
    tag_names = ["новости", site_name, "Россия", "мир"]
    tags = []
    for name in tag_names:
        tag, _ = Tag.objects.get_or_create(name=name)
        tags.append(tag)
    return tags


def import_news_to_django(site_key="lenta", author_username="sulik"):
    if site_key not in SITES:
        print(f"❌ Сайт '{site_key}' не поддерживается. Доступны: {list(SITES.keys())}")
        return

    config = SITES[site_key]
    User = get_user_model()
    
    try:
        author = User.objects.get(username=author_username)
    except User.DoesNotExist:
        print(f"❌ Пользователь {author_username} не найден!")
        return

    default_category = get_or_create_default_category()
    default_tags = get_or_create_default_tags(config["name"])
    
    print(f"🌐 Источник: {config['name']}")
    print(f"📂 Категория: {default_category.name}")
    print(f"🏷️  Теги: {', '.join(t.name for t in default_tags)}\n")

    links = get_news_links(site_key)
    print(f"Найдено ссылок: {len(links)}\n")

    created_count = 0
    for i, link in enumerate(links, 1):
        print(f"[{i}/{len(links)}] {link}")
        article = parse_article(link, site_key)

        if not article:
            continue

        if Post.objects.filter(title=article['title']).exists():
            print("  ⏩ Уже есть в базе.")
            continue

        post = Post(
            title=article['title'],
            content=article['text_md'],
            excerpt=article['text_md'][:200] + "...",
            author=author,
            status='draft',
            category=default_category,
        )

        if article['cover_url']:
            try:
                img_response = requests.get(article['cover_url'], headers=HEADERS, timeout=10)
                img_response.raise_for_status()
                ext = article['cover_url'].split('.')[-1].split('?')[0]
                if ext.lower() not in ('jpg', 'jpeg', 'png', 'gif', 'webp'): ext = 'jpg'
                filename = f"{uuid.uuid4().hex}.{ext}"
                post.cover.save(filename, ContentFile(img_response.content), save=False)
                print("  🖼️  Обложка скачана.")
            except Exception as e:
                print(f"  ⚠️  Ошибка обложки: {e}")

        try:
            post.save()
            post.tags.set(default_tags)
            created_count += 1
            print("  ✅ Сохранено (черновик).")
        except Exception as e:
            print(f"  ❌ Ошибка БД: {e}")

        time.sleep(2)

    print(f"\n🎉 Импорт завершён! Создано: {created_count}")
