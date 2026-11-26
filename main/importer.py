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
                  "Chrome/120.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}

# ═══════════════════════════════════════════════════════════════
# ТОЛЬКО РАБОЧИЕ ИСТОЧНИКИ
# ═══════════════════════════════════════════════════════════════
SITES = {
    "lenta": {
        "name": "Lenta.ru",
        "rss_url": "https://lenta.ru/rss",
        "title_tag": ("h1", "topic-body__titles"),
        "text_tags": [("p", "topic-body__content-text")],
        "cover_tag": ("img", "picture__image"),
    },
    "rt": {
        "name": "RT",
        "rss_url": "https://russian.rt.com/rss",
        "title_tag": ("h1", "article__heading"),
        "text_tags": [
            ("div", "article__text"),
            ("div", "article__text-paragraph"),
            ("p", "article__text-paragraph"),
        ],
        "cover_tag": ("img", "article__cover"),
    },
    "rg": {
        "name": "Российская газета",
        "rss_url": "https://rg.ru/xml/index.xml",
        "title_tag": ("h1", "article__title"),
        "text_tags": [
            ("div", "article__text"),
            ("div", "text-content"),
            ("div", "PageTextContent"),
        ],
        "cover_tag": ("img", "article__image"),
    },
    "ria": {
        "name": "РИА Новости",
        "rss_url": "https://ria.ru/export/rss2/archive/index.xml",
        "title_tag": ("h1", "article__title"),
        "text_tags": [
            ("div", "article__text"),
            ("div", "article__body"),
            ("div", "article__block"),
        ],
        "cover_tag": ("img", "article__image"),
    },
    "iz": {
        "name": "Известия",
        "rss_url": "https://iz.ru/xml/rss/all.xml",
        "title_tag": ("h1", "article_title"),
        "text_tags": [
            ("div", "article_text"),
            ("div", "text-ib"),
        ],
        "cover_tag": ("img", "article_image"),
    },
}

PHOTO_CAPTION_PATTERNS = [
    r'^Фото:', r'^Иллюстрация:', r'^Изображение:', r'^Picture:', r'^Image:',
]


def is_photo_caption(text):
    return any(re.match(p, text.strip(), re.IGNORECASE) for p in PHOTO_CAPTION_PATTERNS)


def get_news_links_rss(site_key):
    config = SITES[site_key]
    try:
        r = requests.get(config["rss_url"], headers=HEADERS, timeout=10)
        r.raise_for_status()
        feed = feedparser.parse(r.content)
    except Exception as e:
        print(f"  ❌ Не удалось загрузить RSS ({config['name']}): {e}")
        return []

    articles = []
    for entry in feed.entries[:5]:
        articles.append({
            "title": entry.get("title", "Без заголовка"),
            "link": entry.get("link", ""),
            "rss_description": entry.get("description", ""),
        })
    return articles


def extract_text(soup, config, rss_desc):
    text_parts = []

    # 1. По селекторам
    for tag_name, class_name in config.get("text_tags", []):
        elements = soup.find_all(tag_name, class_=class_name)
        if not elements:
            continue
        for el in elements:
            if el.name in ("div", "section", "article"):
                inner_ps = el.find_all("p")
                if inner_ps:
                    for p in inner_ps:
                        txt = p.get_text(separator=" ", strip=True)
                        if txt and not is_photo_caption(txt) and len(txt) > 15:
                            text_parts.append(txt)
                else:
                    txt = el.get_text(separator=" ", strip=True)
                    if txt and not is_photo_caption(txt) and len(txt) > 40:
                        text_parts.append(txt)
            else:
                txt = el.get_text(separator=" ", strip=True)
                if txt and not is_photo_caption(txt) and len(txt) > 15:
                    text_parts.append(txt)
        if text_parts:
            break

    # 2. <article>
    if not text_parts:
        article = soup.find("article")
        if article:
            for p in article.find_all("p"):
                txt = p.get_text(separator=" ", strip=True)
                if txt and not is_photo_caption(txt) and len(txt) > 15:
                    text_parts.append(txt)
            if not text_parts:
                txt = article.get_text(separator=" ", strip=True)
                if txt and len(txt) > 100:
                    text_parts.append(txt)

    # 3. Самый большой <div> с <p>
    if not text_parts:
        best_div = None
        best_len = 0
        for div in soup.find_all("div"):
            if len(div.find_all("a")) > 10 or len(div.find_all("script")) > 2:
                continue
            txt = div.get_text(separator=" ", strip=True)
            if len(txt) > best_len and len(txt) < 20000:
                best_len = len(txt)
                best_div = div
        if best_div:
            inner_ps = best_div.find_all("p")
            if inner_ps:
                for p in inner_ps:
                    txt = p.get_text(separator=" ", strip=True)
                    if txt and not is_photo_caption(txt) and len(txt) > 15:
                        text_parts.append(txt)
            if not text_parts:
                txt = best_div.get_text(separator=" ", strip=True)
                if txt and len(txt) > 100:
                    text_parts.append(txt)

    # Дедупликация
    seen = set()
    unique = []
    for t in text_parts:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    return "\n\n".join(unique)


def parse_full_article(article_data, site_key):
    config = SITES[site_key]
    title = article_data['title']
    link = article_data['link']
    rss_desc = article_data['rss_description']

    text_md = ""
    cover_url = ""

    try:
        response = requests.get(link, headers=HEADERS, timeout=10)
        response.raise_for_status()
        response.encoding = "utf-8"
        soup = BeautifulSoup(response.text, "html.parser")

        full_text = extract_text(soup, config, rss_desc)
        full_text = re.sub(r'[ \t]+', ' ', full_text)

        if full_text and len(full_text) > 50:
            text_md = text_to_markdown(full_text)
        else:
            clean_rss = re.sub(r'<[^>]+>', '', rss_desc)
            text_md = text_to_markdown(clean_rss.strip())

        tag_name, class_name = config["cover_tag"]
        if tag_name and class_name:
            cover_element = soup.find(tag_name, class_=class_name)
            if cover_element:
                if cover_element.name == "div":
                    img_tag = cover_element.find("img")
                    if img_tag:
                        src = img_tag.get("src") or img_tag.get("data-src")
                        if src:
                            cover_url = requests.compat.urljoin(link, src)
                elif cover_element.name == "img":
                    src = cover_element.get("src") or cover_element.get("data-src")
                    if src:
                        cover_url = requests.compat.urljoin(link, src)

        if not cover_url:
            og_img = soup.find("meta", property="og:image")
            if og_img and og_img.get("content"):
                cover_url = og_img["content"]

        print(f"  📄 Текст: {len(full_text)} симв., обложка: {'есть' if cover_url else 'нет'}")

    except Exception as e:
        print(f"  ⚠️ HTML недоступен ({e}). Используем RSS.")
        clean_rss = re.sub(r'<[^>]+>', '', rss_desc)
        text_md = text_to_markdown(clean_rss.strip())

    return {"title": title, "text_md": text_md, "cover_url": cover_url, "source_url": link}


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

    articles_data = get_news_links_rss(site_key)
    print(f"Найдено новостей в ленте: {len(articles_data)}\n")

    if not articles_data:
        print("❌ Новостей нет. Возможно, RSS недоступен с этого сервера.")
        return

    created_count = 0
    for i, data in enumerate(articles_data, 1):
        print(f"[{i}/{len(articles_data)}] {data['title']}")

        article = parse_full_article(data, site_key)

        if Post.objects.filter(title=article['title']).exists():
            print("  ⏩ Уже есть в базе.")
            continue

        excerpt_text = re.sub(r'[#*>`_\[\]]', '', article['text_md'])[:200].strip()

        post = Post(
            title=article['title'],
            content=article['text_md'],
            excerpt=excerpt_text + "..." if excerpt_text else "",
            author=author,
            status='draft',
            category=default_category,
        )

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
