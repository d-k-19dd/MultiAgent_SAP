from typing import Dict, Any


class ContextManager:
    """Manages within-conversation grounding: IDs and key scalar outputs for downstream tools."""

    def __init__(self):
        self.state: Dict[str, Any] = {}

    def extract_from_output(self, output: Dict[str, Any]):
        for k, v in output.items():
            if k == "error":
                continue
            kl = k.lower()
            if "id" in kl or kl in (
                "disposable_income_usd",
                "nightly_rate_usd",
                "price_usd",
                "running_total_usd",
                "monthly_contribution_usd",
                "airline",
                "status",
                "summary",
            ):
                self.state[k] = v
            if isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict):
                for idx, dic in enumerate(v):
                    if not isinstance(dic, dict):
                        continue
                    for sub_k, sub_v in dic.items():
                        skl = sub_k.lower()
                        if "id" in skl:
                            self.state[f"{k}_{idx}_{sub_k}"] = sub_v

    def formulate_context_prompt(self) -> str:
        if not self.state:
            return "No previous tool outputs recorded yet; use reasonable defaults only where parameters are optional."
        return f"[SYSTEM NOTIFICATION]: Ground arguments using these values from prior tool outputs: {self.state}"
