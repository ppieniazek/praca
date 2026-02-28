# System zarządzania firmą

Aplikacja webowa do ewidencji czasu pracy, zarządzania portfelami i zaliczkami brygadzistów oraz kontroli kosztów (SaaS). Zbudowana w podejściu Hypermedia-Driven (HATEOAS).

## Technologie

- **Backend**: Python 3.14+, Django 6.0+ (ASGI / Daphne)
- **Frontend**: Datastar.js (SSE)
- **Styling**: Tailwind CSS v4, DaisyUI v5 (CDN)
- **Baza danych**: SQLite (MVP)
- **Narzędzia**: `uv`, `ruff`, `pytest`

## Instalacja i uruchomienie

Sklonuj repozytorium:
```bash
git clone https://github.com/ppieniazek/praca.git
cd praca
```

### Opcja 1: Użycie `uv` (zalecane)

```bash
uv sync
uv run manage.py migrate
uv run manage.py seed_db
uv run manage.py runserver
```

### Opcja 2: Użycie standardowego `pip`

```bash
python -m venv venv
source venv/bin/activate  # Linux/macOS
# .\venv\Scripts\activate # Windows

pip install -r requirements.txt
python manage.py migrate
python manage.py seed_db
python manage.py runserver
```

## Konta testowe

Komenda `seed_db` generuje testowe dane i konta dostępowe:

- **Szef (pełen dostęp):** 
  - Login: `owner`
  - Hasło: `test`
- **Brygadziści (wprowadzanie czasu pracy, portfele):** 
  - Loginy: od `foreman1` do `foreman4`
  - Hasło: `test`
