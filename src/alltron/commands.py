"""Small, explicit local command grammar. No model output can authorize actions."""

from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Callable

from .answers import CodexAnswers
from .home_assistant import HomeAssistant
from .timers import TimerStore


_TIMER = re.compile(
    r"(?:set|start) (?:a )?timer (?:for )?(\d{1,4}) (seconds?|minutes?|hours?)"
    r"(?: (?:called|named) (.{1,80}))?",
    re.IGNORECASE,
)
_ALARM = re.compile(
    r"set (?:an? )?alarm in (\d{1,4}) (seconds?|minutes?|hours?)"
    r"(?: (?:called|named) (.{1,80}))?",
    re.IGNORECASE,
)
_ADD_ITEM = re.compile(r"add (.{1,120}) to (?:my |the )?shopping list", re.IGNORECASE)
_COMPLETE_ITEM = re.compile(
    r"(?:mark|check off|complete) (.{1,120}?) (?:as done )?(?:on )?(?:my |the )?shopping list",
    re.IGNORECASE,
)
_SHOW_LIST = re.compile(r"(?:show|read|what(?:'s| is) on) (?:my |the )?shopping list", re.IGNORECASE)
_TIME = re.compile(r"(?:what(?:'s| is) the time|what time is it|tell me the time|time)", re.IGNORECASE)
_HA_ACTION = re.compile(r"(?:turn|switch) (on|off) (?:the )?(.+)", re.IGNORECASE)
_QUESTION = re.compile(r"(?:what|when|where|who|why|how|which|is|are|can|could|do|does)\b.+", re.IGNORECASE)


def _seconds(amount: str, unit: str) -> int:
    scale = 3600 if unit.lower().startswith("hour") else 60 if unit.lower().startswith("minute") else 1
    return int(amount) * scale


class CommandRouter:
    def __init__(self, store: TimerStore, alarm_available: Callable[[], bool] | None = None,
                 home_assistant: HomeAssistant | None = None, answers: CodexAnswers | None = None):
        self.store = store
        self.alarm_available = alarm_available or (lambda: False)
        self.home_assistant = home_assistant
        self.answers = answers

    def execute(self, text: str, *, request_id: str | None = None, now: float | None = None) -> dict:
        if not isinstance(text, str):
            raise ValueError("Command must be text")
        spoken = " ".join(text.strip().split())
        if not spoken or len(spoken) > 500:
            raise ValueError("Command must contain 1 to 500 characters")
        spoken = re.sub(r"^alltron[,!.?]?\s+", "", spoken, flags=re.IGNORECASE).rstrip(".!?")
        timestamp = time.time() if now is None else now

        if match := _TIMER.fullmatch(spoken):
            duration = _seconds(match[1], match[2])
            timer = self.store.add(duration, match[3] or "Timer", now=timestamp, request_id=request_id)
            return {"kind": "timer", "status": "ok", "text": f"Timer set for {duration} seconds.", "timer": timer}
        if match := _ALARM.fullmatch(spoken):
            if not self.alarm_available():
                return {"kind": "alarm", "status": "unavailable",
                        "text": "Alarm sound is not configured. No alarm was saved."}
            duration = _seconds(match[1], match[2])
            alarm = self.store.add_alarm(timestamp + duration, match[3] or "Alarm", now=timestamp,
                                         request_id=request_id)
            return {"kind": "alarm", "status": "scheduled",
                    "text": f"Alarm saved for {duration} seconds from now. Speaker output still needs a live test.",
                    "alarm": alarm}
        if match := _ADD_ITEM.fullmatch(spoken):
            item = self.store.add_shopping_item(match[1], now=timestamp, request_id=request_id)
            if item["done"]:
                return {"kind": "shopping", "status": "already-completed",
                        "text": "That earlier add request was completed. No new item was added.", "item": item}
            return {"kind": "shopping", "status": "ok", "text": f"{item['text']} is on the shopping list.",
                    "item": item}
        if match := _COMPLETE_ITEM.fullmatch(spoken):
            if self.store.complete_shopping_text(match[1], request_id=request_id):
                return {"kind": "shopping", "status": "ok", "text": "Shopping item completed."}
            return {"kind": "shopping", "status": "not-found", "text": "That exact item is not on the open shopping list."}
        if _SHOW_LIST.fullmatch(spoken):
            items = [item["text"] for item in self.store.list_shopping_items() if not item["done"]]
            spoken_items = items[:3]
            return {"kind": "shopping", "status": "ok",
                    "text": ("Shopping list: " + ", ".join(spoken_items) +
                             (f", and {len(items) - 3} more on screen." if len(items) > 3 else "."))
                    if items else "The shopping list is empty.",
                    "items": items}
        if _TIME.fullmatch(spoken):
            return {"kind": "time", "status": "ok",
                    "text": "It is " + datetime.fromtimestamp(timestamp).strftime("%I:%M %p").lstrip("0")}
        if match := _HA_ACTION.fullmatch(spoken):
            if self.home_assistant:
                return self.home_assistant.switch(match[2], match[1].lower() == "on")
            return {"kind": "home-assistant", "status": "not-configured",
                    "text": "Home Assistant controls are not connected yet."}
        if _QUESTION.fullmatch(spoken) and self.answers:
            return self.answers.answer(spoken)
        return {"kind": "unknown", "status": "unavailable",
                "text": "I don't know that local command yet. General answers are not connected."}
