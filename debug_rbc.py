import requests
from bs4 import BeautifulSoup

URL = "https://www.rbc.ru/"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

response = requests.get(URL, headers=HEADERS, timeout=10)
soup = BeautifulSoup(response.text, "html.parser")

print("=== ССЫЛКИ НА НОВОСТИ ===")
# Ищем ссылки, в которых есть /politics/, /society/, /economics/ и т.д.
links = soup.find_all("a", href=lambda h: h and any(x in h for x in ["/politics/", "/society/", "/economics/", "/finance/", "/world/"]))
for a in links[:5]:
    print(f"class={a.get('class')}, href={a.get('href')}, text={a.get_text(strip=True)[:50]}")

print("\n=== ЗАГОЛОВОК СТАТЬИ (пример) ===")
if links:
    article_url = links[0]['href']
    if not article_url.startswith("http"):
        article_url = "https://www.rbc.ru" + article_url
    
    print(f"Открываем: {article_url}")
    art_resp = requests.get(article_url, headers=HEADERS, timeout=10)
    art_soup = BeautifulSoup(art_resp.text, "html.parser")
    
    # Ищем H1
    h1 = art_soup.find("h1")
    if h1:
        print(f"H1: class={h1.get('class')}, text={h1.get_text(strip=True)}")
    
    # Ищем абзацы
    print("\nАбзацы:")
    for p in art_soup.find_all("p")[:5]:
        txt = p.get_text(strip=True)
        if len(txt) > 20:
            print(f"class={p.get('class')}, text={txt[:50]}...")
