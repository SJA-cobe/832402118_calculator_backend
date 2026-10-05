# Backend Code Style

Source: [PEP 8](https://peps.python.org/pep-0008/). This project adopts its naming, indentation, and import conventions, with exceptions for long SQL statements.

- Use UTF-8 and four spaces for indentation. Use snake_case for functions and variables and PascalCase for classes.
- Place imports at the top, grouped as standard library, third-party, and local modules.
- Separate expression parsing, persistence, and HTTP controllers.
- Validate input types, lengths, and syntax. Do not use eval, exec, or arbitrary code execution.
- Bind SQL parameters. Return consistent JSON responses and appropriate HTTP status codes.
- Catch specific exceptions. Log internal errors without exposing database details in responses.
- Use English for comments, documentation, and user-facing messages.
- Run `python -m unittest discover -s tests -v` after changing calculation rules or API behavior.
