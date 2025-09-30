from __future__ import annotations

from typing import Dict, Any

from .models import Concert, midi_to_note


def render_summary(concert: Concert, camelot: Dict[str, Any]) -> str:
    lines = []
    lines.append(f"Concert: {concert.name}")

    # Songs > Patch > Layer view
    lines.append("Songs (Song → Patch → Layer):")
    for set_obj in concert.sets:
        for patch in set_obj.patches:
            # Treat each top-level Patch as a Song name
            bpm = patch.attributes.get("bpm") if isinstance(patch.attributes, dict) else None
            bpm_txt = f" (BPM: {int(bpm) if isinstance(bpm, (int, float)) and abs(bpm - int(bpm)) < 1e-6 else bpm})" if bpm else ""
            lines.append(f"- Song: {patch.name}{bpm_txt}")
            # Group channel strips by subpatch if available
            groups: Dict[str, list] = {}
            for cs in patch.channel_strips:
                if cs.kind != "instrument":
                    continue
                sub = (cs.notes or {}).get("subpatch") or patch.name
                # Normalize any lingering separators for readability
                if isinstance(sub, str):
                    sub = sub.replace("\\", " — ").replace("/", " — ")
                groups.setdefault(sub, []).append(cs)
            for sub_name, strips in groups.items():
                lines.append(f"  - Patch: {sub_name}")
                for cs in strips:
                    kr = cs.key_range
                    if kr:
                        rng = f"{midi_to_note(kr.low)}..{midi_to_note(kr.high)} ({kr.low}-{kr.high})"
                    else:
                        rng = "full"
                    src = cs.plugins[0].name if cs.plugins else cs.kind
                    lines.append(f"    - Layer: {cs.name}  | {src}  | range: {rng}  | trans: {cs.transpose}")

    lines.append("")
    lines.append("Camelot Session Preview:")
    for song in camelot.get("songs", []):
        sbpm = None
        # prefer song-level bpm in metadata
        md = song.get("metadata") or {}
        if isinstance(md, dict):
            sbpm = md.get("bpm")
        lines.append(f"- Song: {song.get('name')}{(f' (BPM: {sbpm})' if sbpm else '')}")
        for scene in song.get("scenes", []):
            sc_bpm = None
            smd = scene.get("metadata") or {}
            if isinstance(smd, dict):
                sc_bpm = smd.get("bpm")
            lines.append(f"  - Scene: {scene.get('name')}{(f' (BPM: {sc_bpm})' if sc_bpm else '')}")
            for layer in scene.get("layers", []):
                kr = layer.get("keyRange") or {}
                rng = (
                    f"{kr.get('lowName')}..{kr.get('highName')} ({kr.get('low')}–{kr.get('high')})"
                    if kr else "full"
                )
                src = layer.get("source", {}).get("name") or layer.get("source", {}).get("type")
                lines.append(f"    - Layer: {layer.get('name')}  | {src}  | range: {rng}  | trans: {layer.get('transpose')}")

    return "\n".join(lines) + "\n"
