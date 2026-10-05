"""Restricted arithmetic grammar; no execution of user-supplied code."""
import math
import re
from decimal import Decimal, DecimalException, localcontext


class CalculationError(ValueError):
    """An expression cannot be calculated safely."""


TOKEN = re.compile(r"(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)|[a-z]+|[()+*/^!-]")


class Parser:
    def __init__(self, expression, angle_mode="DEG", memory="0"):
        if angle_mode not in ("DEG", "RAD"):
            raise CalculationError("Angle mode must be DEG or RAD")
        self.angle_mode = angle_mode
        self.memory = Decimal(memory)
        if not isinstance(expression, str) or not expression.strip():
            raise CalculationError("Enter an expression")
        if len(expression) > 500:
            raise CalculationError("Expressions cannot exceed 500 characters")
        text = expression.translate(str.maketrans({"×": "*", "÷": "/", "−": "-"}))
        self.tokens = []
        position = 0
        while position < len(text):
            if text[position].isspace():
                position += 1
                continue
            match = TOKEN.match(text, position)
            if not match:
                raise CalculationError(f"Invalid character at position {position + 1}")
            self.tokens.append(match.group())
            position = match.end()
        if len(self.tokens) > 200:
            raise CalculationError("Expression is too complex; the limit is 200 tokens")
        self.position = 0
        self.depth = 0

    def peek(self):
        return self.tokens[self.position] if self.position < len(self.tokens) else None

    def take(self):
        token = self.peek()
        self.position += 1
        return token

    def expression(self):
        value = self.term()
        while self.peek() in ("+", "-"):
            operator = self.take()
            right = self.term()
            value = value + right if operator == "+" else value - right
        return value

    def term(self):
        value = self.unary()
        while self.peek() in ("*", "/"):
            operator = self.take()
            right = self.unary()
            if operator == "/" and right == 0:
                raise CalculationError("Division by zero is not allowed")
            value = value * right if operator == "*" else value / right
        return value

    def unary(self):
        self.depth += 1
        if self.depth > 40:
            raise CalculationError("Expression nesting exceeds the parser depth limit of 40")
        try:
            if self.peek() in ("+", "-"):
                operator = self.take()
                value = self.unary()
                return value if operator == "+" else -value
            return self.power()
        finally:
            self.depth -= 1

    def power(self):
        value = self.factor()
        while self.peek() == "!":
            self.take()
            if value != value.to_integral_value() or not 0 <= value <= 69:
                raise CalculationError("Factorial requires an integer from 0 to 69")
            value = Decimal(math.factorial(int(value)))
        if self.peek() == "^":
            self.take()
            exponent = self.unary()
            if abs(exponent) > 1000:
                raise CalculationError("The absolute exponent cannot exceed 1000")
            if value == 0 and exponent <= 0:
                raise CalculationError("Zero requires a positive exponent")
            if value < 0 and exponent != exponent.to_integral_value():
                raise CalculationError("A negative base requires an integer exponent")
            value = value ** exponent
        return value

    def function(self, name, value):
        if name == "abs":
            return abs(value)
        if name == "sqrt":
            if value < 0:
                raise CalculationError("Square root requires a nonnegative argument")
            return value.sqrt()
        if name in ("ln", "log"):
            if value <= 0:
                raise CalculationError("Logarithm requires a positive argument")
            return value.ln() if name == "ln" else value.log10()
        if abs(value) > Decimal("1e12"):
            raise CalculationError("The absolute trigonometric argument cannot exceed 10^12")
        angle = math.radians(float(value)) if self.angle_mode == "DEG" else float(value)
        if name == "tan" and abs(math.cos(angle)) < 1e-12:
            raise CalculationError("Tangent is undefined or too close to a singularity at this angle")
        answer = {"sin": math.sin, "cos": math.cos, "tan": math.tan}[name](angle)
        return Decimal(format(answer, ".15g"))

    def factor(self):
        self.depth += 1
        if self.depth > 40:
            raise CalculationError("Expression nesting exceeds the parser depth limit of 40")
        try:
            token = self.take()
            if token in ("+", "-"):
                value = self.factor()
                return value if token == "+" else -value
            if token == "(":
                value = self.expression()
                if self.take() != ")":
                    raise CalculationError("Mismatched parentheses")
                return value
            if token is None or token in (")", "*", "/"):
                raise CalculationError("Incomplete expression or misplaced operator")
            if token in ("pi", "e", "mem"):
                return {"pi": Decimal(str(math.pi)), "e": Decimal(str(math.e)),
                        "mem": self.memory}[token]
            if token in ("sqrt", "sin", "cos", "tan", "ln", "log", "abs"):
                if self.take() != "(":
                    raise CalculationError("Function arguments must be enclosed in parentheses")
                value = self.expression()
                if self.take() != ")":
                    raise CalculationError("Mismatched function parentheses")
                return self.function(token, value)
            if token is None or not re.fullmatch(r"[0-9]+(?:\.[0-9]*)?|\.[0-9]+", token):
                raise CalculationError("Unsupported function or operator")
            return Decimal(token)
        finally:
            self.depth -= 1


def calculate(expression, angle_mode="DEG", memory="0"):
    parser = Parser(expression, angle_mode, memory)
    try:
        with localcontext() as context:
            context.prec = 28
            value = parser.expression()
            if parser.peek() is not None:
                raise CalculationError("Unexpected number or parenthesis, or a missing operator")
            if not value.is_finite() or abs(value) > Decimal("1e100") or (value != 0 and value.adjusted() < -1000):
                raise CalculationError("Result is outside the supported range")
            result = format(value, "f")
            if "." in result:
                result = result.rstrip("0").rstrip(".")
            return "0" if value == 0 else result
    except DecimalException as error:
        raise CalculationError("Number is outside the supported range") from error
