"""ECHO pedagogical state machine with conservative evidence rules."""

from __future__ import annotations


class EchoFSM:
    states = ("E", "C", "H", "O")

    def __init__(self, rounds: dict[str, int] | None = None) -> None:
        self.rounds = {state: int((rounds or {}).get(state, 0)) for state in self.states}
        self.allowed = {
            "E": {"E", "C"},
            "C": {"C", "H"},
            "H": {"H", "C", "O"},
            "O": {"O", "E"},
        }

    @staticmethod
    def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
        normalized = (text or "").strip()
        return any(phrase in normalized for phrase in phrases)

    def detect_confusion(self, text: str) -> bool:
        return self._contains_any(
            text,
            (
                "没听懂",
                "还是不懂",
                "无法理解",
                "不明白这里",
                "请换一种解释",
                "再讲一遍",
                "有点乱",
            ),
        )

    def detect_emotion(self, text: str) -> bool:
        return self._contains_any(
            text,
            ("学不动了", "压力很大", "很焦虑", "想放弃学习", "完全没动力"),
        )

    def detect_reflection(self, text: str) -> bool:
        return self._contains_any(
            text,
            (
                "如果换一个场景",
                "我总结一下",
                "我的推理是",
                "这个方法还能用于",
                "我需要验证",
            ),
        )

    def update(self, user_input: str, proposed_state: str, current_state: str) -> dict:
        current = current_state if current_state in self.states else "E"
        proposed = proposed_state if proposed_state in self.states else current

        if self.detect_emotion(user_input):
            next_state, reason = "E", "检测到明确学习压力，回到唤起与支持阶段。"
        elif self.detect_confusion(user_input):
            next_state, reason = "C", "检测到明确理解困难，进入共同建构阶段。"
        elif self.detect_reflection(user_input):
            next_state, reason = "O", "检测到迁移或自我校验证据，进入开放反思阶段。"
        elif proposed in self.allowed[current]:
            next_state, reason = proposed, "采用合法的 ECHO 阶段转换。"
        else:
            next_state, reason = current, "拦截缺少证据的阶段跳转。"

        self.rounds[next_state] += 1
        return {
            "selected_state": proposed,
            "normalized_state": next_state,
            "reason": reason,
            "rounds": dict(self.rounds),
        }
