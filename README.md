cat > README.md << 'EOF'
# МойБлог

Блог на Django + SQLite.

## Стек
- Python 3.12, Django 6.x
- SQLite
- Bootstrap 5
- Markdown + Pygments

## Запуск

```bash
git clone https://github.com/sulik1976/django-blog.git
cd django-blog
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Создай .env (см. .env.example)
cp .env.example .env
# Отредактируй SECRET_KEY

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
