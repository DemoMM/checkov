from typing import List, Optional, Any, Dict

from checkov.common.graph.checks_infra.enums import Operators
from .exists_attribute_solver import ExistsAttributeSolver


class NotExistsAttributeSolver(ExistsAttributeSolver):
    operator = Operators.NOT_EXISTS  # noqa: CCE003  # a static attribute

    def _get_operation(self, vertex: Dict[str, Any], attribute: Optional[str]) -> bool:  # type:ignore[override]
        return not super()._get_operation(vertex, attribute)
