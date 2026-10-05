# ClearCalc Backend

Python 3.10+ standard-library HTTP JSON API with SQLite persistence. No third-party packages are required.

## Run

```bash
python src/server.py
```

The default address is http://127.0.0.1:8000. The database is created automatically at `data/calculator.db`. Keep this file to retain history and memory. Start the frontend separately on port 5500.

Environment variables: `HOST`, `PORT`, `DATABASE_PATH`, and `ALLOWED_ORIGINS` (comma-separated origins without trailing slashes). Windows PowerShell example:

```powershell
$env:PORT="8000"
$env:ALLOWED_ORIGINS="http://localhost:5500,http://127.0.0.1:5500"
python src/server.py
```

## API

| Method | Path | Purpose |
|---|---|---|
| GET | /api/health | Health check |
| POST | /api/calculate | Calculate and save an expression |
| GET | /api/history?page=1&page_size=5&q= | Search and paginate history |
| DELETE | /api/history/1 | Delete one record by ID |
| GET | /api/memory | Read persistent memory |
| POST | /api/memory | Store, add, subtract, or clear memory |
| GET | /api/history/export | Retrieve all records for CSV export |

Example calculation body: `{"expression":"(1+2)*3","angle_mode":"DEG"}`. Success returns HTTP 201 with `success: true` and a `data` object containing id, expression, result, created_at, and angle_mode. Results are decimal strings to avoid browser floating-point conversion. Errors return `{"success":false,"message":"English explanation"}`.

## Calculation rules

Supports arithmetic, parentheses, decimal numbers, unary signs, powers, factorials, sqrt/sin/cos/tan/ln/log/abs, pi/e, and mem. DEG is the default angle mode. No implicit multiplication is supported. Failed calculations are not saved.

Limits: 500 expression characters, 200 tokens, parser recursion depth 40, absolute result at most 10^100, and nonzero result decimal exponent at least -1000. Factorials accept integers from 0 through 69; absolute exponents cannot exceed 1000. Decimal arithmetic uses 28 significant digits. Trigonometric functions and pi/e are approximations; trigonometric results use about 15 significant digits.

History and memory are shared across visitors. The service is intended for a course project and small demonstrations. Use the supplied Nginx reverse proxy for the container deployment.

## Tests and structure

```bash
python -m unittest discover -s tests -v
```

- `src/server.py`: HTTP controllers and request validation.
- `src/calculator.py`: restricted expression parser and scientific functions.
- `src/database.py`: SQLite history, migrations, and memory transactions.
- `tests/`: calculation, API, persistence, and migration tests.

The combined project includes detailed API and usage documents in its `docs` directory.
