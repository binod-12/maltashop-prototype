"""Minimal JSON-schema-style validator (type, required, properties, items, minimum, minLength, minItems).

Dependency-free on purpose; enough for consumer-driven contract checks between two services.
"""


def _actual_type(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _type_ok(expected: str, actual: str) -> bool:
    if expected == "number":
        return actual in ("number", "integer")
    return expected == actual


def validate(schema: dict, value, path: str = "$") -> list[str]:
    errors: list[str] = []
    expected = schema.get("type")
    actual = _actual_type(value)

    if expected and not _type_ok(expected, actual):
        return [f"{path}: expected {expected}, got {actual}"]

    if "minimum" in schema and isinstance(value, (int, float)) and value < schema["minimum"]:
        errors.append(f"{path}: below minimum {schema['minimum']}")
    if "minLength" in schema and len(str(value)) < schema["minLength"]:
        errors.append(f"{path}: shorter than {schema['minLength']}")

    if expected == "object":
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}.{key}: required field missing")
        for key, sub in schema.get("properties", {}).items():
            if key in value:
                errors.extend(validate(sub, value[key], f"{path}.{key}"))

    if expected == "array":
        if "items" in schema:
            for i, item in enumerate(value):
                errors.extend(validate(schema["items"], item, f"{path}[{i}]"))
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(f"{path}: needs at least {schema['minItems']} item(s)")

    return errors
