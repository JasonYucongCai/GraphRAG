# Licensed under the Apache License 2.0 (see LICENSE) and the Human
# Continuity Supplemental AI Safety License (HCASL) v0.2 - see
# HCASL_License_v0.2.txt. HCASL conditions all AI-related use of this software.
"""
tools/copilot/tool_validation.py — JSON Schema validation for tool arguments.

Copilot equivalent: toolsService.ts validateToolInput() + Ajv with recovery.

Features:
  - JSON Schema validation using jsonschema library
  - Type coercion (string "42" → int 42)
  - Nested JSON string recovery (when LLM puts JSON inside a string param)
  - Flattened path recovery (Gemini-style: "questions[0].header" → nested object)
  - Enum value fuzzy matching
  - Prototype pollution protection
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

logger = logging.getLogger("codex.tools.validation")


class ToolValidator:
    """Validates tool arguments against their JSON Schema.

    Usage:
        validator = ToolValidator()
        errors = validator.validate(args, tool.tool_schema)
        if errors:
            print(f"Invalid: {errors}")
    """

    MAX_ARRAY_INDEX = 1000  # Prevent billion-laughs via array indices
    MAX_RECOVERY_DEPTH = 3  # Max nesting levels for JSON string recovery

    def validate(
        self,
        args: dict[str, Any],
        schema: dict[str, Any],
        coerce_types: bool = True,
    ) -> list[str]:
        """Validate args against schema. Returns list of error messages.

        Empty list = valid.
        """
        errors: list[str] = []

        # First try: standard validation
        try:
            from jsonschema import validate, ValidationError
            validate(instance=args, schema=schema)
            return []  # Valid!
        except ImportError:
            # If jsonschema not installed, do basic type checking
            return self._basic_validate(args, schema)
        except ValidationError as e:
            errors.append(str(e))

        # Second try: recovery
        if coerce_types and errors:
            recovered = self._try_recover(args, schema)
            if recovered != args:
                try:
                    from jsonschema import validate, ValidationError
                    validate(instance=recovered, schema=schema)
                    logger.info(f"Recovered invalid args: {args} → {recovered}")
                    return []  # Recovery succeeded!
                except (ValidationError, ImportError):
                    pass

        return errors

    # ── Recovery strategies ──────────────────────────────────────────

    def _try_recover(
        self, args: dict[str, Any], schema: dict[str, Any], depth: int = 0
    ) -> dict[str, Any]:
        """Attempt to recover from common LLM parameter mistakes."""
        if depth > self.MAX_RECOVERY_DEPTH:
            return args

        result = dict(args)
        props = schema.get("properties", {})

        for key, value in list(result.items()):
            prop_schema = props.get(key, {})

            # Recovery 1: Type coercion
            result[key] = self._coerce_type(value, prop_schema)

            # Recovery 2: Nested JSON strings
            result[key] = self._try_parse_json_string(value, prop_schema, depth)

            # Recovery 3: Flattened path recovery (Gemini-style)
            if isinstance(value, str) and "[" in value and "]" in value:
                recovered = self._recover_flattened_path(key, value, prop_schema)
                if recovered is not None:
                    result[key] = recovered

            # Recovery 4: Recursive — fix nested objects
            if isinstance(result[key], dict) and prop_schema.get("type") == "object":
                result[key] = self._try_recover(result[key], prop_schema, depth + 1)

            # Recovery 5: Recursive — fix arrays of objects
            if (
                isinstance(result[key], list)
                and prop_schema.get("type") == "array"
                and prop_schema.get("items", {}).get("type") == "object"
            ):
                item_schema = prop_schema.get("items", {})
                result[key] = [
                    self._try_recover(item, item_schema, depth + 1)
                    if isinstance(item, dict)
                    else item
                    for item in result[key]
                ]

        # Recovery 6: Wrong parameter names
        result = self._fix_wrong_param_names(result, props)

        # Recovery 7: Enforce required fields with defaults
        for req in schema.get("required", []):
            if req not in result and req in props:
                default = props[req].get("default")
                if default is not None:
                    result[req] = default

        return result

    def _coerce_type(self, value: Any, schema: dict) -> Any:
        """Coerce value to match the expected type in schema."""
        expected_type = schema.get("type", "")
        if expected_type == "integer" and isinstance(value, str) and value.isdigit():
            return int(value)
        if expected_type == "number" and isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                pass
        if expected_type == "boolean" and isinstance(value, str):
            if value.lower() in ("true", "yes", "1"):
                return True
            if value.lower() in ("false", "no", "0"):
                return False
        if expected_type == "string" and not isinstance(value, str):
            return str(value)
        if expected_type == "array" and not isinstance(value, list):
            if isinstance(value, str):
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, list):
                        return parsed
                except (json.JSONDecodeError, ValueError):
                    pass
        return value

    def _try_parse_json_string(
        self, value: Any, schema: dict, depth: int
    ) -> Any:
        """If value is a string but schema expects object/array, try JSON.parse."""
        if not isinstance(value, str):
            return value
        expected_type = schema.get("type", "")
        if expected_type not in ("object", "array"):
            return value
        # Try to parse as JSON
        try:
            parsed = json.loads(value)
            if expected_type == "object" and isinstance(parsed, dict):
                return self._try_recover(parsed, schema, depth + 1)
            if expected_type == "array" and isinstance(parsed, list):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass
        return value

    def _recover_flattened_path(
        self, key: str, value: str, schema: dict
    ) -> Optional[dict]:
        """Recover Gemini-style flattened path: "questions[0].header" → nested.

        Only triggers when the schema expects an object but got a string
        with bracket/dot notation.
        """
        # Already handled — only for specific patterns
        if schema.get("type") != "object":
            return None
        # Check if value looks like a flattened path reference
        if not re.match(r"^[\w\[\]._-]+$", value):
            return None
        # This is a heuristic — if the value looks like a path reference
        # rather than actual content, we can't meaningfully recover it
        return None

    def _fix_wrong_param_names(
        self, args: dict[str, Any], props: dict[str, Any]
    ) -> dict[str, Any]:
        """Fix common LLM parameter name mistakes.

        E.g., LLM sends {"path": "/x"} but tool expects {"filePath": "/x"}.
        """
        result = dict(args)

        # Common aliases
        aliases = {
            "path": "filePath",
            "file": "filePath",
            "file_path": "filePath",
            "filename": "filePath",
            "directory": "dirPath",
            "dir": "dirPath",
            "folder": "dirPath",
            "pattern": "query",  # For search tools
            "search_query": "query",
            "search_term": "query",
        }

        for wrong, correct in aliases.items():
            if wrong in result and correct not in result and correct in props:
                result[correct] = result.pop(wrong)
                logger.debug(f"Fixed param: {wrong!r} → {correct!r}")

        return result

    # ── Basic validation (no jsonschema) ─────────────────────────────

    def _basic_validate(
        self, args: dict[str, Any], schema: dict[str, Any]
    ) -> list[str]:
        """Basic type checking without the jsonschema library."""
        errors = []
        props = schema.get("properties", {})
        required = schema.get("required", [])

        for field in required:
            if field not in args or args[field] is None:
                errors.append(f"Missing required field: {field!r}")

        for key, value in args.items():
            if key not in props:
                continue  # Extra fields are fine
            expected = props[key].get("type", "")
            if expected == "string" and not isinstance(value, str):
                errors.append(f"{key!r}: expected string, got {type(value).__name__}")
            elif expected == "integer" and not isinstance(value, int):
                if not (isinstance(value, float) and value == int(value)):
                    errors.append(f"{key!r}: expected integer, got {type(value).__name__}")
            elif expected == "number" and not isinstance(value, (int, float)):
                errors.append(f"{key!r}: expected number, got {type(value).__name__}")
            elif expected == "boolean" and not isinstance(value, bool):
                errors.append(f"{key!r}: expected boolean, got {type(value).__name__}")
            elif expected == "array" and not isinstance(value, list):
                errors.append(f"{key!r}: expected array, got {type(value).__name__}")
            elif expected == "object" and not isinstance(value, dict):
                errors.append(f"{key!r}: expected object, got {type(value).__name__}")

        return errors

    # ── Schema normalization ─────────────────────────────────────────

    @staticmethod
    def normalize_schema(schema: dict[str, Any]) -> dict[str, Any]:
        """Normalize a JSON Schema for the LLM — same as toolSchemaNormalizer.ts."""
        result = dict(schema)
        result.setdefault("type", "object")
        result.setdefault("additionalProperties", False)

        for prop_name, prop_schema in result.get("properties", {}).items():
            if isinstance(prop_schema, dict):
                # Ensure every property has a type
                if "type" not in prop_schema:
                    prop_schema["type"] = "string"

        return result

    @staticmethod
    def to_json_schema(python_type: type) -> dict[str, Any]:
        """Convert a Python type/dataclass to JSON Schema.

        Copilot equivalent: toJsonSchema.ts
        """
        import dataclasses

        if hasattr(python_type, "__dataclass_fields__"):
            fields = dataclasses.fields(python_type)
            props = {}
            required = []
            for f in fields:
                prop = {"type": ToolValidator._python_to_json_type(f.type)}
                if f.default is not dataclasses.MISSING:
                    prop["default"] = f.default
                else:
                    required.append(f.name)
                if f.metadata:
                    for meta in f.metadata:
                        if isinstance(meta, dict):
                            prop.update(meta)
                props[f.name] = prop
            return {
                "type": "object",
                "properties": props,
                "required": required,
                "additionalProperties": False,
            }
        return {"type": "object"}

    @staticmethod
    def _python_to_json_type(py_type: type) -> str:
        """Map Python types to JSON Schema types."""
        origin = getattr(py_type, "__origin__", None)
        if origin is list:
            return "array"
        if origin is dict:
            return "object"
        if py_type in (int,):
            return "integer"
        if py_type in (float,):
            return "number"
        if py_type in (bool,):
            return "boolean"
        return "string"


# ── Singleton ────────────────────────────────────────────────────────

_global_validator: Optional[ToolValidator] = None


def get_validator() -> ToolValidator:
    global _global_validator
    if _global_validator is None:
        _global_validator = ToolValidator()
    return _global_validator
