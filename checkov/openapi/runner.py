from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any, Callable  # noqa: F401  # Callable is used in the TypeAlias

from typing_extensions import TypeAlias

from checkov.common.checks.base_check_registry import BaseCheckRegistry
from checkov.common.bridgecrew.check_type import CheckType
from checkov.yaml_doc.runner import Runner as YamlRunner
from checkov.json_doc.runner import Runner as JsonRunner

_ParseFormatJsonCallable: TypeAlias = "Callable[[JsonRunner, str], tuple[dict[str, Any] | list[dict[str, Any]] | None, list[tuple[int, str]] | None] | None]"
_ParseFormatYamlCallable: TypeAlias = "Callable[[YamlRunner, str], tuple[dict[str, Any] | list[dict[str, Any]] | None, list[tuple[int, str]] | None] | None]"

logger = logging.getLogger(__name__)


class Runner(YamlRunner, JsonRunner):
    check_type = CheckType.OPENAPI  # noqa: CCE003  # a static attribute

    def __init__(self) -> None:
        super().__init__()
        self.file_extensions = [".json", ".yml", ".yaml"]

    def import_registry(self) -> BaseCheckRegistry:
        from checkov.openapi.checks.registry import openapi_registry

        return openapi_registry

    def _parse_file(
        self, f: str, file_content: str | None = None
    ) -> tuple[dict[str, Any] | list[dict[str, Any]], list[tuple[int, str]]] | None:
        if f.endswith(".json"):
            return self.parse_format(f, JsonRunner._parse_file)
        elif f.endswith(".yml") or f.endswith(".yaml"):
            return self.parse_format(f, YamlRunner._parse_file)

        return None

    def parse_format(
        self,
        f: str,
        func: _ParseFormatJsonCallable | _ParseFormatYamlCallable,
    ) -> tuple[dict[str, Any] | list[dict[str, Any]], list[tuple[int, str]]] | None:
        try:
            parsed_file = func(self, f)
            if isinstance(parsed_file, tuple) and self.is_valid(parsed_file[0]):
                return parsed_file  # type:ignore[return-value]  # is_valid checks for being not empty
        except ValueError:
            logger.debug(f"Could not parse {f}, skipping file", exc_info=True)
        return None

    def get_start_end_lines(
        self, end: int, result_config: dict[str, Any] | list[dict[str, Any]], start: int
    ) -> tuple[int, int]:
        start_end_line: tuple[int, int]
        if hasattr(result_config, "start_mark"):
            start_end_line = JsonRunner.get_start_end_lines(self, end, result_config, start)  # type:ignore[arg-type]
            return start_end_line
        elif "__startline__" in result_config or isinstance(result_config, list):
            start_end_line = YamlRunner.get_start_end_lines(self, end, result_config, start)
            return start_end_line

        raise Exception("Unexpected dictionary format.")

    def require_external_checks(self) -> bool:
        return False

    def is_valid(self, conf: dict[str, Any] | list[dict[str, Any]] | None) -> bool:
        """validate openAPI configuration."""
        # 'swagger' is a required element on v2.0, and 'openapi' is required on v3.
        # 'info' object is required in v2.0 and v3:
        # https://swagger.io/specification/v2/#schema
        # https://swagger.io/specification/#schema
        try:
            return bool(
                conf
                and isinstance(conf, dict)
                and ("swagger" in conf or "openapi" in conf)
                and isinstance(conf["info"], dict)
            )
        except Exception:
            return False

    def get_resource(self, file_path: str, key: str, supported_entities: Iterable[str], definitions: dict[str, Any] | None = None) -> str:
        return ",".join(supported_entities)
