SITES = {
    "lenta": {
        "name": "Lenta.ru",
        "rss_url": "https://lenta.ru/rss",
        "title_tag": ("h1", "topic-body__titles"),
        "text_tag": ("p", "topic-body__content-text"),
        "cover_tag": ("img", "picture__image"),
    },
    "rbc": { # Оставляем, но имейте в виду, что лента может не работать
        "name": "РБК",
        "rss_url": "http://static.feed.rbc.ru/rbc/logical/footer/news.rss",
        "title_tag": ("h1", "article-entry-title"),
        "text_tag": ("p", "paragraph"),
        "cover_tag": ("img", "picture-image"),
    },
    "rt": {
        "name": "RT",
        "rss_url": "https://russian.rt.com/rss",
        "title_tag": ("h1", "article__heading"), # Примерный селектор
        "text_tag": ("div", "article__text"),     # Примерный селектор
        "cover_tag": ("img", "article__cover"),   # Примерный селектор
    },
    "iz": {
        "name": "Известия",
        "rss_url": "https://iz.ru/xml/rss/all.xml",
        "title_tag": ("h1", "article_title"),    # Примерный селектор
        "text_tag": ("div", "article_text"),     # Примерный селектор
        "cover_tag": ("img", "article_image"),   # Примерный селектор
    },
}