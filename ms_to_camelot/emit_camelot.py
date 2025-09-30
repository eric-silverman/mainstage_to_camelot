from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from .models import Concert, Set, Patch, ChannelStrip


def build_camelot_session(concert: Concert, flatten_sets: bool, source_path: str) -> Dict[str, Any]:
    now_iso = datetime.now().isoformat()
    session: Dict[str, Any] = {
        "version": 1,
        "name": concert.name,
        "createdAt": now_iso,
        "source": {
            "type": "mainstage",
            "path": source_path,
            "extractedAt": now_iso,
        },
        "songs": [],
        "metadata": concert.attributes,
    }

    if flatten_sets:
        # Each patch becomes a Song with a single Scene
        for s in concert.sets:
            for p in s.patches:
                meta = {"_fromSet": s.name}
                if isinstance(p.attributes, dict) and p.attributes.get("bpm") is not None:
                    meta["bpm"] = p.attributes.get("bpm")
                song = {
                    "name": p.name,
                    "scenes": [scene_from_patch(p)],
                    "metadata": meta,
                }
                session["songs"].append(song)
    else:
        # Map Set -> Song, Patch -> Scene; tempo belongs at Song level
        for s in concert.sets:
            meta = dict(s.attributes) if isinstance(s.attributes, dict) else {}
            # Pull BPM from the first patch that has it
            bpm = None
            for p in s.patches:
                if isinstance(p.attributes, dict) and p.attributes.get("bpm") is not None:
                    bpm = p.attributes.get("bpm")
                    break
            if bpm is not None:
                meta["bpm"] = bpm

            song = {"name": s.name, "scenes": [], "metadata": meta}
            for p in s.patches:
                song["scenes"].append(scene_from_patch(p, include_bpm=False))
            session["songs"].append(song)

    return session


def scene_from_patch(patch: Patch, include_bpm: bool = True) -> Dict[str, Any]:
    meta = patch.attributes.copy() if isinstance(patch.attributes, dict) else {}
    if not include_bpm and isinstance(meta, dict) and "bpm" in meta:
        # Keep bpm only at song level when requested
        meta = {k: v for k, v in meta.items() if k != "bpm"}
    return {
        "name": patch.name,
        "layers": [layer_from_strip(cs) for cs in patch.channel_strips if cs.kind == "instrument"],
        "metadata": meta,
    }


def layer_from_strip(cs: ChannelStrip) -> Dict[str, Any]:
    layer: Dict[str, Any] = {
        "name": cs.name,
        "keyRange": cs.key_range.to_dict() if cs.key_range else None,
        "transpose": cs.transpose,
        "source": plugin_source(cs),
        "midiChannel": cs.midi_channel,
        "metadata": cs.notes,
    }
    return layer


def plugin_source(cs: ChannelStrip) -> Dict[str, Any]:
    # Best effort: first plugin as the source instrument
    if cs.plugins:
        p = cs.plugins[0]
        return {
            "type": "plugin",
            "name": p.name,
            "manufacturer": p.manufacturer,
            "kind": p.kind,
            "identifier": p.identifier,
        }
    return {"type": cs.kind, "name": cs.name}
