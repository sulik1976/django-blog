import re
import time
import uuid
import feedparser
import requests
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
# НАСТРОЙКИ RSS-ЛЕНТ
# ═══════════════════════════════════════════════════════════════
SITES = {
    "lenta": {
        "name": "Lenta.ru",
        "rss_url": "https://lenta.ru/rss",  # Основная лента
    },
    "rbc": {
        "name": "РБК",
        "rss_url": "http://static.feed.rbc.ru/rbc/internal/rss.rbc.ru/rbc.ru/mainnews.rss",
    }
}

def get_news_links_rss(site_key):
    """Получает список новостей из RSS-ленты."""
    config = SITES[site_key]
    feed = feedparser.parse(config["rss_url"])
    
    articles = []
    for entry in feed.entries[:10]:
        articles.append({
            "title": entry.get("title", "Без заголовка"),
            "link": entry.get("link", ""),
            "description": entry.get("description", ""),
        })
    return articles

def parse_article_rss(article_data, site_key):
    """Обрабатывает одну статью из RSS."""
    title = article_data['title']
    raw_text = article_data['description']
    
    # Очищаем текст от HTML-тегов
    clean_text = re.sub(r'<[^>]+>', '', raw_text)
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()
    
    # Конвертируем в Markdown
    text_md = text_to_markdown(clean_text) if clean_text else ""
    
    # В простом RSS обложек обычно нет, оставляем пустой
    cover_url = ""
    
    return {"title": title, "text_md": text_md, "cover_url": cover_url, "link": article_data['link']}

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
    
    print(f"🌐 Источник (RSS): {config['name']}")
    print(f"📂 Категория: {default_category.name}")
    print(f"🏷️  Теги: {', '.join(t.name for t in default_tags)}\n")

    articles_data = get_news_links_rss(site_key)
    print(f"Найдено новостей в ленте: {len(articles_data)}\n")

    created_count = 0
    for i, data in enumerate(articles_data, 1):
        print(f"[{i}/{len(articles_data)}] {data['title']}")
        
        article = parse_article_rss(data, site_key)

        # Проверка на дубликат по заголовку
        if Post.objects.filter(title=article['title']).exists():
            print("  ⏩ Уже есть в базе.")
            continue

        post = Post(
            title=article['title'],
            content=article['text_md'],
            excerpt=article['text_md'][:200] + "..." if article['text_md'] else "",
            author=author,
            status='draft',
            category=default_category,
        )

        # Скачивание обложки (в RSS её обычно нет, но код оставлен для будущего)
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

        time.sleep(1)

    print(f"\n🎉 Импорт завершён! Создано: {created_count}")