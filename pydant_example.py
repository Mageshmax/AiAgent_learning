"""
Pydantic example: check and convert function inputs using type hints.

Plain Python ignores type hints, so add('1', 1) crashes with
"can only concatenate str (not 'int') to str".

With pydantic's @validate_call:
    - '1' is CONVERTED to the int 1, so add('1', 1) returns 2
    - 'abc' can't become an int, so pydantic raises a clear ValidationError

Run:
    python pydant_example.py
"""

from pydantic import ValidationError, validate_call


@validate_call
def add(a: int, b: int) -> int:
    return a + b


print(add('1', 1))   # 2  ('1' was converted to 1)

try:
    add('abc', 1)
except ValidationError as e:
    print(e)          # explains which input was wrong and why
