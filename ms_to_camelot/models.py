from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, List, Optional, Dict


@dataclass
class KeyRange:
    low: int  # 0-127
    high: int  # 0-127

    def to_dict(self) -> Dict[str, Any]:
        return {"low": self.low, "high": self.high, "lowName": midi_to_note(self.low), "highName": midi_to_note(self.high)}


@dataclass
class Plugin:
    name: str
    manufacturer: Optional[str] = None
    kind: Optional[str] = None  # AU/VST/etc
    identifier: Optional[str] = None  # bundle id / component id
    params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ChannelStrip:
    name: str
    kind: str  # instrument/audio/midi
    midi_channel: Optional[int] = None
    key_range: Optional[KeyRange] = None
    transpose: int = 0
    plugins: List[Plugin] = field(default_factory=list)
    notes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if self.key_range:
            d["key_range"] = self.key_range.to_dict()
        d["plugins"] = [p.to_dict() for p in self.plugins]
        return d


@dataclass
class Patch:
    name: str
    channel_strips: List[ChannelStrip] = field(default_factory=list)
    attributes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "channel_strips": [cs.to_dict() for cs in self.channel_strips],
            "attributes": self.attributes,
        }


@dataclass
class Set:
    name: str
    patches: List[Patch] = field(default_factory=list)
    attributes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "patches": [p.to_dict() for p in self.patches],
            "attributes": self.attributes,
        }


@dataclass
class Concert:
    name: str
    sets: List[Set] = field(default_factory=list)
    attributes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "sets": [s.to_dict() for s in self.sets],
            "attributes": self.attributes,
        }


NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def midi_to_note(n: int) -> str:
    if n is None:
        return ""
    n = max(0, min(127, int(n)))
    name = NOTE_NAMES[n % 12]
    octave = n // 12 - 1
    return f"{name}{octave}"

