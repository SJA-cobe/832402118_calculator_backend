import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from calculator import CalculationError, calculate
from database import HistoryStore
from server import make_handler


class ParserTests(unittest.TestCase):
    def test_arithmetic(self):
        cases = {'12+8': '20', '8-3': '5', '5*8': '40', '10/2': '5',
                 '1+2*3': '7', '(1+2)*3': '9', '10/2+7': '12',
                 '8-3*2': '2', '-5+8': '3', '3*-2': '-6',
                 '0.1+0.2': '0.3', '.5+1.': '1.5', '+2-(-3)': '5',
                 '12 ÷ 3 × 2': '8', '8/4/2': '1', '-0': '0'}
        for expression, expected in cases.items():
            with self.subTest(expression=expression):
                self.assertEqual(calculate(expression), expected)

    def test_invalid_expressions(self):
        for expression in ['', None, 42, '1/0', '(2+3', '2+3)', '2 3',
                           '1+', '2**3', '1..2', "__import__('os')", '2(3)',
                           '('*41+'1'+')'*41, '1'*501, '1/(-0)']:
            with self.subTest(expression=expression):
                with self.assertRaises(CalculationError):
                    calculate(expression)

    def test_scientific_precedence_and_functions(self):
        cases = {'2^10': '1024', '2^3^2': '512', '-2^2': '-4',
                 '(-2)^2': '4', '2^-2': '0.25', 'sqrt(16)': '4',
                 '5!': '120', '0!': '1', 'log(100)': '2',
                 'ln(1)': '0', 'abs(-3)': '3', 'sin(30)': '0.5',
                 'cos(60)': '0.5', '3!^2': '36', 'sqrt(9)+2^3': '11'}
        for expression, expected in cases.items():
            with self.subTest(expression=expression):
                self.assertEqual(calculate(expression), expected)
        self.assertAlmostEqual(float(calculate('sin(pi/2)', 'RAD')), 1)
        self.assertAlmostEqual(float(calculate('ln(e)')), 1)
        self.assertEqual(calculate('mem*2', memory='7'), '14')

    def test_scientific_domain_and_security(self):
        for expression in ['sqrt(-1)', 'ln(0)', 'log(-1)', 'tan(90)',
                           '70!', '1.5!', '0^0', '0^-1', '(-2)^.5',
                           '2^1001', 'open(1)', 'sin 30', 'sin()',
                           'sin(30,40)', 'pi(2)', 'sin(1e2)', '10^(-1000)/10']:
            with self.subTest(expression=expression):
                with self.assertRaises(CalculationError):
                    calculate(expression)
        with self.assertRaises(CalculationError):
            calculate('sin(30)', 'UNKNOWN')


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / 'test.db'
        self.store = HistoryStore(self.path)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(
            self.store, ['http://localhost:5500']))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.directory.cleanup()

    def request(self, path, method='GET', body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = Request(self.base+path, data=data, method=method,
                      headers={'Content-Type': 'application/json',
                               'Origin': 'http://localhost:5500'})
        try:
            response = urlopen(req, timeout=3)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response), response.headers

    def test_create_read_persist_delete(self):
        status, payload, headers = self.request('/api/calculate', 'POST', {'expression': '(1+2)*3'})
        self.assertEqual(status, 201)
        self.assertEqual(payload['data']['result'], '9')
        self.assertEqual(headers['Access-Control-Allow-Origin'], 'http://localhost:5500')
        record_id = payload['data']['id']
        # A fresh storage instance must see the committed record.
        self.assertEqual(HistoryStore(self.path).list(1, 10, '')['total'], 1)
        self.assertEqual(self.request('/api/history')[1]['data']['items'][0]['id'], record_id)
        self.assertEqual(self.request(f'/api/history/{record_id}', 'DELETE')[0], 200)
        self.assertEqual(HistoryStore(self.path).list(1, 10, '')['total'], 0)
        self.assertEqual(self.request(f'/api/history/{record_id}', 'DELETE')[0], 404)

    def test_failed_calculation_is_not_saved(self):
        for body in [{'expression': '1/0'}, {'expression': '__import__(1)'}, {}, ['1+2']]:
            self.assertEqual(self.request('/api/calculate', 'POST', body)[0], 400)
        self.assertEqual(self.store.list(1, 10, '')['total'], 0)

    def test_pagination_search_validation(self):
        for value in range(7):
            self.request('/api/calculate', 'POST', {'expression': f'{value}+1'})
        data = self.request('/api/history?page=2&page_size=5')[1]['data']
        self.assertEqual(len(data['items']), 2)
        self.assertEqual(data['total'], 7)
        self.assertEqual(self.request('/api/history?q=3')[1]['data']['total'], 1)
        for path in ['/api/history?page=0', '/api/history?page=x', '/api/history?page_size=101']:
            self.assertEqual(self.request(path)[0], 400)
        self.assertEqual(self.request('/unknown')[0], 404)

    def test_memory_export_and_angle_mode(self):
        self.assertEqual(self.request('/api/memory')[1]['data']['value'], '0')
        _, payload, _ = self.request('/api/calculate', 'POST',
                                    {'expression': 'sin(pi/2)', 'angle_mode': 'RAD'})
        record = payload['data']
        self.assertEqual(record['result'], '1')
        self.assertEqual(record['angle_mode'], 'RAD')
        body = {'action': 'store', 'record_id': record['id']}
        self.assertEqual(self.request('/api/memory', 'POST', body)[1]['data']['value'], '1')
        body['action'] = 'add'
        self.assertEqual(self.request('/api/memory', 'POST', body)[1]['data']['value'], '2')
        body['action'] = 'subtract'
        self.assertEqual(self.request('/api/memory', 'POST', body)[1]['data']['value'], '1')
        self.assertEqual(HistoryStore(self.path).memory(), '1')
        self.assertEqual(self.request('/api/calculate', 'POST', {'expression': 'mem+2'})[1]['data']['result'], '3')
        self.assertEqual(len(self.request('/api/history/export')[1]['data']['items']), 2)
        self.assertEqual(self.request('/api/memory', 'POST', {'action': 'clear'})[1]['data']['value'], '0')
        self.assertEqual(self.request('/api/memory', 'POST', {'action': 'store', 'record_id': 999})[0], 404)
        self.assertEqual(self.request('/api/memory', 'POST', {'action': 'store', 'value': '999'})[0], 400)
        self.assertEqual(self.request('/api/calculate', 'POST', {'expression': 'sin(1)', 'angle_mode': 'x'})[0], 400)

    def test_migrate_original_database(self):
        import sqlite3
        old_path = Path(self.directory.name) / 'old.db'
        with sqlite3.connect(old_path) as connection:
            connection.execute('CREATE TABLE calculation_history (id INTEGER PRIMARY KEY, expression TEXT NOT NULL, result TEXT NOT NULL, created_at TEXT NOT NULL)')
            connection.execute("INSERT INTO calculation_history VALUES (1, '1+2', '3', '2026-10-01T00:00:00Z')")
        upgraded = HistoryStore(old_path)
        record = upgraded.list(1, 10, '')['items'][0]
        self.assertEqual(record['result'], '3')
        self.assertEqual(record['angle_mode'], 'DEG')
        self.assertEqual(upgraded.memory(), '0')


if __name__ == '__main__':
    unittest.main()
