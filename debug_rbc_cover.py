import requests
from bs4 import BeautifulSoup

url = "https://www.rbc.ru/politics/23/11/2026/6b045ef4706a7a3feb32ae3a"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

response = requests.get(url, headers=HEADERS, timeout=10)
soup = BeautifulSoup(response.text, "html.parser")

print("=== ВСЕ META С 'image' ===")
for meta in soup.find_all("meta"):
    prop = meta.get("property", "") or meta.get("name", "")
    if "image" in prop.lower():
        print(f"property={prop}, content={meta.get('content')}")

print("\n=== ВСЕ <img> С БОЛЬШИМИ РАЗМЕРАМИ (width/height) ===")
for img in soup.find_all("img"):
    src = img.get("src") or img.get("data-src")
    if not src:
        continue
    cls = img.get("class", [])
    w = img.get("width", "")
    # Показываем только те, что похожи на обложку (не иконки)
    if any(x in " ".join(cls).lower() for x in ["article", "main", "cover", "picture", "image"]):
        print(f"class={cls}, src={src[:100]}")
    elif w and int(w) > 300:
        print(f"class={cls}, src={src[:100]}")
