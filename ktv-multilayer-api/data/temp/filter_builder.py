from typing import Any, Dict, List


class FilterBuilder:
    def __init__(self, filters: Dict[str, Any]):
        self.filters = filters
        self.params = {}

    def build_conditions(self) -> List[str]:
        conditions = []
        for field, value in self.filters.items():
            if value is not None:
                param_name = f"param_{field}"
                conditions.append(f"{field} = :{param_name}")
                self.params[param_name] = value
        return conditions

    def get_params(self) -> Dict[str, Any]:
        return self.params
