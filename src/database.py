"""SQLite storage with parameterized queries and one connection per request."""
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from pathlib import Path

from calculator import CalculationError


class HistoryStore:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode=DELETE")
            connection.execute("""CREATE TABLE IF NOT EXISTS calculation_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                expression TEXT NOT NULL,
                result TEXT NOT NULL,
                created_at TEXT NOT NULL
            )""")

            connection.execute("""CREATE TABLE IF NOT EXISTS calculator_memory (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                value TEXT NOT NULL
            )""")
            connection.execute("INSERT OR IGNORE INTO calculator_memory VALUES (1, '0')")
            columns = {row[1] for row in connection.execute("PRAGMA table_info(calculation_history)")}
            if "angle_mode" not in columns:
                connection.execute("ALTER TABLE calculation_history ADD COLUMN angle_mode TEXT NOT NULL DEFAULT 'DEG'")

    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def add(self, expression, result, angle_mode="DEG"):
        record = {"expression": expression, "result": result,
                  "created_at": datetime.now(timezone.utc).isoformat(), "angle_mode": angle_mode}
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO calculation_history (expression,result,created_at,angle_mode) VALUES (?,?,?,?)",
                tuple(record.values()),
            )
            record["id"] = cursor.lastrowid
        return record

    def list(self, page, page_size, query):
        search = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        with self.connect() as connection:
            total = connection.execute(
                "SELECT COUNT(*) FROM calculation_history WHERE expression LIKE ? ESCAPE '\\'",
                (search,),
            ).fetchone()[0]
            rows = connection.execute(
                "SELECT * FROM calculation_history WHERE expression LIKE ? ESCAPE '\\' ORDER BY id DESC LIMIT ? OFFSET ?",
                (search, page_size, (page - 1) * page_size),
            ).fetchall()
        return {"items": [dict(row) for row in rows], "total": total,
                "page": page, "page_size": page_size}

    def delete(self, record_id):
        with self.connect() as connection:
            return connection.execute(
                "DELETE FROM calculation_history WHERE id=?", (record_id,)
            ).rowcount > 0

    def memory(self):
        with self.connect() as connection:
            return connection.execute("SELECT value FROM calculator_memory WHERE id=1").fetchone()[0]

    def update_memory(self, action, value):
        with self.connect() as connection:
            # Serialize read-modify-write operations across concurrent requests.
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute("SELECT value FROM calculator_memory WHERE id=1").fetchone()[0]
            if action == "clear":
                updated = "0"
            elif action == "store":
                updated = value
            else:
                operator = "+" if action == "add" else "-"
                # Stored decimals may exceed the input length limit; add using
                # Decimal directly, not by reparsing a generated expression.
                with localcontext() as context:
                    context.prec = 28
                    number = Decimal(current) + Decimal(value) if operator == "+" else Decimal(current) - Decimal(value)
                    if abs(number) > Decimal("1e100"):
                        raise CalculationError("Memory value is outside the supported range")
                    updated = format(number, "f")
                    if "." in updated:
                        updated = updated.rstrip("0").rstrip(".")
                    if number == 0:
                        updated = "0"
            connection.execute("UPDATE calculator_memory SET value=? WHERE id=1", (updated,))
        return updated

    def export(self):
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM calculation_history ORDER BY id DESC LIMIT 10001").fetchall()
        if len(rows) > 10000:
            raise CalculationError("Export is limited to 10,000 records; reduce the history before exporting")
        return [dict(row) for row in rows]
