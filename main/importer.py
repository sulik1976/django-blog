import re
import time
import uuid
import feedparser
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

# ═══════════════════════════════════════════════════════════════
# НАСТРОЙКИ САЙТОВ (RSS для ссылок + HTML для контента)
# ═══════════════════════════════════════════════════════════════
SITES = {
    "lenta": {
        "name": "Lenta.ru",
        "rss_url": "https://lenta.ru/rss",
        "title_tag": ("h1", "topic-body__titles"),
        "text_tag": ("p", "topic-body__content-text"),
        "cover_tag": ("img", "picture__image"),
    },
    "rbc": {
        "name": "РБК",
        # Обновлённая, актуальная RSS-лента
        "rss_url": "http://static.feed.rbc.ru/rbc/logical/footer/news.rss",
        "title_tag": ("h1", "article-entry-title"),
        "text_tag": ("p", "paragraph"),
        "cover_tag": ("img", "picture-image"),
    }
}

PHOTO_CAPTION_PATTERNS = [r'^Фото:', r'^Иллюстрация:', r'^Изображение:', r'^Picture:']


def is_photo_caption(text):
    return any(re.match(p, text.strip(), re.IGNORECASE) for p in PHOTO_CAPTION_PATTERNS)


def get_news_links_rss(site_key):
    """Получает список новостей из RSS-ленты."""
    config = SITES[site_key]
    feed = feedparser.parse(config["rss_url"])

    articles = []
    for entry in feed.entries[:10]:
        articles.append({
            "title": entry.get("title", "Без заголовка"),
            "link": entry.get("link", ""),
            "rss_description": entry.get("description", ""),
        })
    return articles


def parse_full_article(article_data, site_key):
    """
    Пытается загрузить полную статью по ссылке.
    Если не получается — возвращает то, что было в RSS.
    """
    config = SITES[site_key]
    title = article_data['title']
    link = article_data['link']
    rss_desc = article_data['rss_description']

    text_md = ""
    cover_url = ""

    # Пытаемся загрузить HTML статьи
    try:
        response = requests.get(link, headers=HEADERS, timeout=10)
        response.raise_for_status()
        response.encoding = "utf-8"
        soup = BeautifulSoup(response.text, "html.parser")

        # 1. Пытаемся достать полный текст
        paragraphs = soup.find_all(config["text_tag"][0], class_=config["text_tag"][1])
        text_parts = []
        for p in paragraphs:
            txt = p.get_text(separator=" ", strip=True)
            if txt and not is_photo_caption(txt):
                text_parts.append(txt)

        full_text = "\n\n".join(text_parts)
        full_text = re.sub(r'[ \t]+', ' ', full_text)

        if full_text:
            text_md = text_to_markdown(full_text)
        else:
            # Если HTML пустой, берем описание из RSS
            clean_rss = re.sub(r'<[^>]+>', '', rss_desc)
            text_md = text_to_markdown(clean_rss.strip())

        # 2. Пытаемся достать обложку
        img_tag = soup.find(config["cover_tag"][0], class_=config["cover_tag"][1])
        if img_tag:
            src = img_tag.get("src") or img_tag.get("data-src")
            if src:
                cover_url = requests.compat.urljoin(link, src)
        else:
            og_img = soup.find("meta", property="og:image")
            if og_img and og_img.get("content"):
                cover_url = og_img["content"]

        print("  📄 Полный текст и обложка загружены из HTML.")

    except Exception as e:
        print(f"  ⚠️ HTML недоступен ({e}). Используем RSS.")
        clean_rss = re.sub(r'<[^>]+>', '', rss_desc)
        text_md = text_to_markdown(clean_rss.strip())

    return {"title": title, "text_md": text_md, "cover_url": cover_url}


# ═══════════════════════════════════════════════════════════════
# СОХРАНЕНИЕ В DJANGO
# ═══════════════════════════════════════════════════════════════

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
        print(f"❌ Сайт '{site_key}' не поддерживается.")
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

    articles_data = get_news_links_rss(site_key)
    print(f"Найдено новостей в ленте: {len(articles_data)}\n")

    created_count = 0
    for i, data in enumerate(articles_data, 1):
        print(f"[{i}/{len(articles_data)}] {data['title']}")

        article = parse_full_article(data, site_key)

        if Post.objects.filter(title=article['title']).exists():
            print("  ⏩ Уже есть в базе.")
            continue

        # Обрезаем текст для excerpt
        excerpt_text = re.sub(r'[#*>`_\[\]]', '', article['text_md'])[:200].strip()

        post = Post(
            title=article['title'],
            content=article['text_md'],
            excerpt=excerpt_text + "..." if excerpt_text else "",
            author=author,
            status='draft',
            category=default_category,
        )

        # Скачивание обложки
        if article['cover_url']:
            try:
                img_response = requests.get(article['cover_url'], headers=HEADERS, timeout=10)
                img_response.raise_for_status()
                ext = article['cover_url'].split('.')[-1].split('?')[0]
                if ext.lower() not in ('jpg', 'jpeg', 'png', 'gif', 'webp'):
                    ext = 'jpg'
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