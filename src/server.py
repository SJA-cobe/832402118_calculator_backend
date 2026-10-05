"""JSON HTTP API, independent from the static front-end server."""
import json
import logging
import os
import re
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from calculator import CalculationError, calculate
from database import HistoryStore


LOGGER = logging.getLogger(__name__)


def make_handler(store, allowed_origins):
    class Handler(BaseHTTPRequestHandler):
        def respond(self, status, data):
            content = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            origin = self.headers.get("Origin")
            if origin in allowed_origins:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(content)

        def do_OPTIONS(self):
            self.send_response(204)
            origin = self.headers.get("Origin")
            if origin in allowed_origins:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def dispatch(self):
            try:
                path = urlsplit(self.path)
                if self.command == "GET" and path.path == "/api/health":
                    return self.respond(200, {"success": True, "message": "Service is healthy"})
                if self.command == "POST" and path.path in ("/api/calculate", "/api/memory"):
                    try:
                        length = int(self.headers.get("Content-Length", "0"))
                    except ValueError:
                        raise CalculationError("Invalid request length") from None
                    if length <= 0 or length > 4096:
                        return self.respond(413, {"success": False, "message": "Request length must be between 1 and 4096 bytes"})
                    if self.headers.get_content_type() != "application/json":
                        return self.respond(415, {"success": False, "message": "Use application/json"})
                    try:
                        payload = json.loads(self.rfile.read(length))
                    except (ValueError, UnicodeDecodeError):
                        raise CalculationError("Invalid JSON") from None
                    if not isinstance(payload, dict):
                        raise CalculationError("Request body must be a JSON object")
                    if path.path == "/api/memory":
                        action = payload.get("action")
                        if action not in ("clear", "store", "add", "subtract"):
                            raise CalculationError("Unsupported memory operation")
                        if action == "clear":
                            value = "0"
                        else:
                            record_id = payload.get("record_id")
                            if type(record_id) is not int or not 1 <= record_id <= 9223372036854775807:
                                raise CalculationError("Select a successful calculation record")
                            with store.connect() as connection:
                                row = connection.execute("SELECT result FROM calculation_history WHERE id=?", (record_id,)).fetchone()
                            if row is None:
                                return self.respond(404, {"success": False, "message": "Calculation record was not found; calculate again"})
                            value = row[0]
                        updated = store.update_memory(action, value)
                        return self.respond(200, {"success": True, "data": {"value": updated}})
                    expression = payload.get("expression")
                    angle_mode = payload.get("angle_mode", "DEG")
                    result = calculate(expression, angle_mode, store.memory())
                    record = store.add(expression.strip(), result, angle_mode)
                    return self.respond(201, {"success": True, "data": record})
                if self.command == "GET" and path.path == "/api/memory":
                    return self.respond(200, {"success": True, "data": {"value": store.memory()}})
                if self.command == "GET" and path.path == "/api/history/export":
                    return self.respond(200, {"success": True, "data": {"items": store.export()}})
                if self.command == "GET" and path.path == "/api/history":
                    params = parse_qs(path.query)
                    try:
                        page = int(params.get("page", ["1"])[0])
                        size = int(params.get("page_size", ["10"])[0])
                    except ValueError:
                        raise CalculationError("Pagination parameters must be integers") from None
                    if page < 1 or not 1 <= size <= 100:
                        raise CalculationError("page must be positive and page_size must be between 1 and 100")
                    query = params.get("q", [""])[0]
                    if len(query) > 500:
                        raise CalculationError("Search query is too long")
                    return self.respond(200, {"success": True, "data": store.list(page, size, query)})
                match = re.fullmatch(r"/api/history/([1-9][0-9]*)", path.path)
                if self.command == "DELETE" and match:
                    if store.delete(int(match.group(1))):
                        return self.respond(200, {"success": True, "message": "Deleted"})
                    return self.respond(404, {"success": False, "message": "Record not found"})
                self.respond(404, {"success": False, "message": "Endpoint not found"})
            except CalculationError as error:
                self.respond(400, {"success": False, "message": str(error)})
            except (sqlite3.Error, OverflowError):
                LOGGER.exception("Database request failed")
                self.respond(500, {"success": False, "message": "Database operation failed; try again later"})

        do_GET = dispatch
        do_POST = dispatch
        do_DELETE = dispatch

    return Handler


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    default_path = Path(__file__).resolve().parents[1] / "data" / "calculator.db"
    store = HistoryStore(os.environ.get("DATABASE_PATH", default_path))
    origins = os.environ.get("ALLOWED_ORIGINS", "http://localhost:5500,http://127.0.0.1:5500").split(",")
    address = (os.environ.get("HOST", "127.0.0.1"), int(os.environ.get("PORT", "8000")))
    server = ThreadingHTTPServer(address, make_handler(store, origins))
    server.daemon_threads = True
    print(f"Calculator API: http://{address[0]}:{address[1]}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
