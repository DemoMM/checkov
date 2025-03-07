from __future__ import annotations

from detect_secrets.core.potential_secret import PotentialSecret
from detect_secrets.plugins.high_entropy_strings import Base64HighEntropyString, HexHighEntropyString
from detect_secrets.plugins.keyword import KeywordDetector
from detect_secrets.plugins.base import BasePlugin
from typing import Generator, Any, TYPE_CHECKING

from checkov.secrets.runner import SOURCE_CODE_EXTENSION

if TYPE_CHECKING:
    from detect_secrets.util.code_snippet import CodeSnippet

MAX_LINE_LENGTH = 10000


class EntropyKeywordCombinator(BasePlugin):
    secret_type = ""  # nosec  # noqa: CCE003  # a static attribute

    def __init__(self, limit: float) -> None:
        self.high_entropy_scanners = (Base64HighEntropyString(limit=limit), HexHighEntropyString(limit=limit))
        self.keyword_scanner = KeywordDetector()

    def analyze_line(
            self,
            filename: str,
            line: str,
            line_number: int = 0,
            context: CodeSnippet | None = None,
            **kwargs: Any,
    ) -> set[PotentialSecret]:
        """
        This method first runs the keyword plugin. If it finds a match - it runs the entropy scanners, and if
        one of the entropy scanners find a match (on a line which was already matched by keyword plugin) - it is returned.
        for source code files run and merge the two plugins.
        """
        entropy_matches = set()
        if len(line) <= MAX_LINE_LENGTH:
            keyword_matches = self.keyword_scanner.analyze_line(filename, line, line_number, **kwargs)
            if f".{filename.split('.')[-1]}" in SOURCE_CODE_EXTENSION:
                for entropy_scanner in self.high_entropy_scanners:
                    matches = entropy_scanner.analyze_line(filename, line, line_number, **kwargs)
                    if matches:
                        entropy_matches = matches
                        break
                keyword_entropy = keyword_matches.union(entropy_matches)
                return keyword_entropy
            if keyword_matches:
                for entropy_scanner in self.high_entropy_scanners:
                    matches = entropy_scanner.analyze_line(filename, line, line_number, **kwargs)
                    if matches:
                        return matches
        return set()

    def analyze_string(self, string: str) -> Generator[str, None, None]:
        raise NotImplementedError()
