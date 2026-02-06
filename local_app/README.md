YT Tree → Graph

Simple app: Flask backend crawls YouTube choices from video descriptions and builds `graph.json` for a D3 force-directed graph.

Run

1. Create venv and install:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

2. Start the server:

```bash
python backend/app.py
```

3. Open frontend:

- `http://127.0.0.1:5000/frontend/input.html` — paste YouTube URL and start crawl
- `http://127.0.0.1:5000/frontend/graph.html` — view graph


