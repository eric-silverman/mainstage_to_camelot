from __future__ import annotations

import plistlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .models import Concert, Set, Patch, ChannelStrip, KeyRange, Plugin


def parse_concert(path: Path, verbose: bool = False) -> Concert:
    bundle_path, data_path = resolve_projectdata(path)
    raw = load_plist(data_path)

    # Attempt to identify a name
    name = infer_concert_name(raw) or bundle_path.stem

    # Support legacy folder-based format where patches live under "Concert.patch"
    legacy_patch_folder = bundle_path / "Concert.patch"
    if legacy_patch_folder.exists() and legacy_patch_folder.is_dir():
        sets = extract_from_patch_folder(legacy_patch_folder, verbose=verbose)
    else:
        sets = extract_sets_and_patches(raw, verbose=verbose)

    concert = Concert(name=name, sets=sets, attributes={"source": str(bundle_path)})
    return concert


def extract_from_patch_folder(folder: Path, verbose: bool = False) -> List[Set]:
    """Extract patches from legacy MainStage bundle layout
    where each top-level .patch directory represents a Patch and may contain
    nested .patch directories with actual channel strips.
    """
    patches: List[Patch] = []
    for patch_dir in sorted([p for p in folder.iterdir() if p.is_dir() and p.suffix == ".patch"]):
        patch_name = normalize_name(patch_dir.stem)
        strips: List[ChannelStrip] = []

        bpm: Optional[float] = None

        # Channels and tempo defined directly on the patch
        direct_plist = patch_dir / "data.plist"
        if direct_plist.exists():
            try:
                raw = load_plist(direct_plist)
                # BPM from patch.engineNode
                b = infer_bpm_from_patch_dict(raw)
                if b is not None:
                    bpm = b
                if isinstance(raw.get("channels"), list):
                    for ch in raw["channels"]:
                        cs = parse_legacy_channel(ch, subpatch_name=None)
                        if cs:
                            strips.append(cs)
            except Exception:
                pass

        # Channels defined in nested sub-patches (support paths like "Sampler/Synclavier.patch")
        subpatch_dirs = [p for p in patch_dir.rglob("*.patch") if p.is_dir()]
        for sub in sorted(subpatch_dirs):
            sp = sub / "data.plist"
            if not sp.exists():
                continue
            try:
                raw = load_plist(sp)
            except Exception:
                continue
            rel = sub.relative_to(patch_dir)
            rel_str = str(rel)
            if rel_str.endswith(".patch"):
                rel_str = rel_str[:-6]
            subpatch_name = normalize_name(rel_str)
            if isinstance(raw.get("channels"), list):
                for ch in raw["channels"]:
                    cs = parse_legacy_channel(ch, subpatch_name=subpatch_name)
                    if cs:
                        strips.append(cs)

        attrs: Dict[str, Any] = {"_source": "legacy_folder"}
        if bpm is not None:
            attrs["bpm"] = bpm
        patches.append(Patch(name=patch_name, channel_strips=strips, attributes=attrs))

    return [Set(name="Concert", patches=patches, attributes={"_source": "legacy_folder"})]


def parse_legacy_channel(ch: Dict[str, Any], subpatch_name: Optional[str]) -> Optional[ChannelStrip]:
    """Parse a channel dictionary from legacy subpatch data.plist.
    Key ranges and deep plugin info are often NSKeyedArchiver blobs; we skip them.
    """
    if not isinstance(ch, dict):
        return None
    name = normalize_name(ch.get("Channel_name") or ch.get("name") or "Strip")
    midi_channel = None  # Not obvious in legacy; could be present in mappings
    transpose = 0
    key_range = None
    plugins: List[Plugin] = []
    # Try to decode NSKeyedArchiver blob in 'layer' to get key range/transpose
    layer_blob = ch.get("layer")
    if isinstance(layer_blob, (bytes, bytearray)):
        try:
            layer = plistlib.loads(layer_blob)
            objects = layer.get("$objects", [])
            # Find dict with lowNote/highNote
            target = None
            for o in objects:
                if isinstance(o, dict) and "lowNote" in o and "highNote" in o:
                    target = o
                    break
            if target:
                low = coerce_int(target.get("lowNote"))
                high = coerce_int(target.get("highNote"))
                if low is not None and high is not None:
                    low = max(0, min(127, low))
                    high = max(0, min(127, high))
                    key_range = KeyRange(low=low, high=high)
                tz = coerce_int(target.get("transpose"))
                if tz is not None:
                    transpose = tz
        except Exception:
            pass

    # Minimal plugin info from Filename or alias
    inst_filename = ch.get("Filename")
    if isinstance(inst_filename, str) and inst_filename:
        plugins.append(Plugin(name=inst_filename, kind="channelStrip"))

    notes: Dict[str, Any] = {"_legacy": True}
    if subpatch_name:
        notes["subpatch"] = normalize_name(subpatch_name)

    return ChannelStrip(
        name=name,
        kind="instrument",
        midi_channel=midi_channel,
        key_range=key_range,
        transpose=transpose,
        plugins=plugins,
        notes=notes,
    )


def normalize_name(name: str) -> str:
    """Normalize display names: replace slashes, collapse spaces, strip."""
    if not isinstance(name, str):
        return ""
    s = str(name).replace("\\", " — ").replace("/", " — ")
    # Normalize weird double spaces around dashes
    s = s.replace(" —  ", " — ").replace("  — ", " — ")
    s = " ".join(s.split())
    return s.strip()



def resolve_projectdata(path: Path) -> Tuple[Path, Path]:
    """Return (bundle_path, projectdata_path) for a given input path.
    Accepts either a .concert bundle path or a direct ProjectData path.
    More tolerant search for common variants like ProjectData.plist.
    """
    p = path
    if p.is_dir() and p.suffix == ".concert":
        # Typical locations inside MainStage bundle
        candidates = [
            p / "Alternatives" / "000" / "ProjectData",
            p / "Alternatives" / "000" / "ProjectData.plist",
            p / "ProjectData",
            p / "ProjectData.plist",
        ]
        for c in candidates:
            if c.exists():
                return (p, c)

        # Fallbacks: search broadly for any ProjectData* file
        for pattern in ("ProjectData", "ProjectData.plist", "**/ProjectData", "**/ProjectData.plist", "**/*ProjectData*"):
            for c in p.rglob(pattern):
                if c.is_file():
                    return (p, c)

        # Last resort: search for the largest plist inside the bundle
        plist_candidates = sorted(
            [c for c in p.rglob("*.plist") if c.is_file()],
            key=lambda x: x.stat().st_size if x.exists() else 0,
            reverse=True,
        )
        if plist_candidates:
            return (p, plist_candidates[0])

        raise FileNotFoundError("Could not find ProjectData inside the .concert bundle")
    elif p.is_file():
        # If the user passed a ProjectData directly
        return (p.parent, p)
    else:
        raise FileNotFoundError(f"Unsupported input: {p}")


def load_plist(path: Path) -> Dict[str, Any]:
    with path.open("rb") as f:
        return plistlib.load(f)


def infer_concert_name(raw: Dict[str, Any]) -> Optional[str]:
    # Heuristics: check common keys where a name/title could live
    for key in ("name", "Name", "title", "Title", "concertName"):
        v = raw.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def extract_sets_and_patches(raw: Dict[str, Any], verbose: bool = False) -> List[Set]:
    """Attempt to navigate MainStage structure to sets/patches.
    The project format is a hierarchy of objects; we’ll look for known patterns
    but also fall back to a generic traversal by class/kind.
    """

    # Strategy:
    # 1) Find the root list of children that resembles the Patch List
    # 2) Build Sets (top-level groups) and Patches (leaf nodes)

    root_children = find_patchlist_children(raw)
    if not root_children:
        # Fall back to single Set with all patches extracted heuristically
        patches = extract_patches_recursive(raw, verbose=verbose)
        return [Set(name="Default", patches=patches, attributes={})]

    sets: List[Set] = []
    for child in root_children:
        child_type = classify_node(child)
        if child_type == "set":
            set_name = normalize_name(node_name(child) or "Set")
            patches = extract_patches_from_set(child, verbose=verbose)
            sets.append(Set(name=set_name, patches=patches, attributes={"_sourceClass": node_class(child)}))
        elif child_type == "patch":
            # Put top-level patches into an implicit set
            patch = extract_patch(child, verbose=verbose)
            sets.append(Set(name=patch.name, patches=[patch], attributes={"_implicit": True}))
        else:
            # Unknown node type: try extracting patches underneath
            patches = extract_patches_recursive(child, verbose=verbose)
            if patches:
                sets.append(Set(name=node_name(child) or "Set", patches=patches, attributes={"_sourceClass": node_class(child)}))

    return sets if sets else [Set(name="Default", patches=extract_patches_recursive(raw, verbose=verbose))]


def find_patchlist_children(raw: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    # Common heuristics: keys that hold the patch list
    for key in ("children", "_children", "patches", "sets", "rootChildren", "PatchList"):
        if isinstance(raw.get(key), list) and raw[key]:
            return raw[key]
    # Search one level down for a container with children
    for v in raw.values():
        if isinstance(v, dict):
            ch = find_patchlist_children(v)
            if ch:
                return ch
    return None


def classify_node(node: Dict[str, Any]) -> str:
    cls = node_class(node).lower()
    name = (node.get("name") or node.get("Name") or "").lower()
    if "set" in cls or name.startswith("set "):
        return "set"
    if "patch" in cls:
        return "patch"
    # sometimes group nodes contain children
    if isinstance(node.get("children") or node.get("_children"), list):
        return "set"
    return "unknown"


def node_class(node: Dict[str, Any]) -> str:
    return str(node.get("class") or node.get("_class") or node.get("isa") or node.get("type") or "")


def node_name(node: Dict[str, Any]) -> Optional[str]:
    v = node.get("name") or node.get("Name") or node.get("title") or node.get("Title")
    return v if isinstance(v, str) else None


def extract_patches_from_set(node: Dict[str, Any], verbose: bool = False) -> List[Patch]:
    children = node.get("children") or node.get("_children") or node.get("patches") or []
    patches: List[Patch] = []
    for ch in children:
        if classify_node(ch) == "patch":
            patches.append(extract_patch(ch, verbose=verbose))
        else:
            patches.extend(extract_patches_recursive(ch, verbose=verbose))
    return patches


def extract_patches_recursive(node: Dict[str, Any], verbose: bool = False) -> List[Patch]:
    out: List[Patch] = []
    if classify_node(node) == "patch":
        out.append(extract_patch(node, verbose=verbose))
    for key in ("children", "_children", "patches"):
        ch = node.get(key)
        if isinstance(ch, list):
            for c in ch:
                out.extend(extract_patches_recursive(c, verbose=verbose))
    return out


def extract_patch(node: Dict[str, Any], verbose: bool = False) -> Patch:
    name = normalize_name(node_name(node) or "Patch")
    strips = extract_channel_strips(node, verbose=verbose)
    attrs: Dict[str, Any] = {"_sourceClass": node_class(node)}
    bpm = infer_bpm_from_node(node)
    if bpm is not None:
        attrs["bpm"] = bpm
    return Patch(name=name, channel_strips=strips, attributes=attrs)


def infer_bpm_from_patch_dict(raw: Dict[str, Any]) -> Optional[float]:
    """Legacy patch data.plist format: raw['patch']['engineNode']['tempo']"""
    try:
        p = raw.get("patch")
        if isinstance(p, dict):
            eng = p.get("engineNode")
            if isinstance(eng, dict):
                if not eng.get("hasTempo") and eng.get("followMIDITempo"):
                    return None
                t = eng.get("tempo")
                if isinstance(t, (int, float)):
                    return float(t)
    except Exception:
        return None
    return None


def infer_bpm_from_node(node: Dict[str, Any]) -> Optional[float]:
    """Best-effort BPM inference from a generic patch node."""
    # Direct keys
    if isinstance(node.get("tempo"), (int, float)):
        return float(node["tempo"])
    # engineNode dict
    eng = node.get("engineNode")
    if isinstance(eng, dict):
        t = eng.get("tempo")
        if isinstance(t, (int, float)):
            return float(t)
    # nested dicts search limited depth
    for k, v in node.items():
        if isinstance(v, dict):
            t = v.get("tempo")
            if isinstance(t, (int, float)):
                return float(t)
    return None


def extract_channel_strips(node: Dict[str, Any], verbose: bool = False) -> List[ChannelStrip]:
    strips: List[ChannelStrip] = []
    candidates = []
    # Typical keys where channel strips may be stored
    for key in ("channelStrips", "channel_strips", "strips", "mixerStrips"):
        v = node.get(key)
        if isinstance(v, list):
            candidates = v
            break

    if not candidates:
        # Search deeper one level for any list of dicts that look like strips
        for k, v in node.items():
            if isinstance(v, list) and v and isinstance(v[0], dict) and any(x in v[0] for x in ("stripType", "strip", "instrument", "plugins")):
                candidates = v
                break

    for raw_strip in candidates or []:
        cs = parse_channel_strip(raw_strip)
        if cs:
            strips.append(cs)
    return strips


def parse_channel_strip(raw_strip: Dict[str, Any]) -> Optional[ChannelStrip]:
    name = normalize_name(raw_strip.get("name") or raw_strip.get("stripName") or raw_strip.get("Name") or "Strip")
    kind = infer_strip_kind(raw_strip)
    midi_channel = coerce_int(raw_strip.get("midiChannel") or raw_strip.get("midi_channel"))
    transpose = coerce_int(raw_strip.get("transpose") or 0)
    key_range = infer_key_range(raw_strip)
    plugins = infer_plugins(raw_strip)

    return ChannelStrip(
        name=name,
        kind=kind,
        midi_channel=midi_channel,
        key_range=key_range,
        transpose=transpose or 0,
        plugins=plugins,
        notes={"_sourceClass": raw_strip.get("class") or raw_strip.get("_class")},
    )


def infer_strip_kind(raw_strip: Dict[str, Any]) -> str:
    # Heuristics based on known fields
    kind = (raw_strip.get("stripType") or raw_strip.get("type") or "").lower()
    if "inst" in kind:
        return "instrument"
    if "audio" in kind:
        return "audio"
    if "midi" in kind:
        return "midi"
    # Fall back: if it has instrument/plugin slot
    if any(k in raw_strip for k in ("instrument", "softwareInstrument", "instrumentPlugin")):
        return "instrument"
    return "instrument"


def infer_key_range(raw_strip: Dict[str, Any]) -> Optional[KeyRange]:
    # Common MainStage fields for key range
    candidates = [
        (raw_strip.get("keyRangeLow"), raw_strip.get("keyRangeHigh")),
        (raw_strip.get("keyLow"), raw_strip.get("keyHigh")),
        (raw_strip.get("noteLow"), raw_strip.get("noteHigh")),
        (raw_strip.get("lowKey"), raw_strip.get("highKey")),
    ]
    for low, high in candidates:
        low_i = coerce_int(low)
        high_i = coerce_int(high)
        if low_i is not None and high_i is not None:
            low_i = max(0, min(127, low_i))
            high_i = max(0, min(127, high_i))
            return KeyRange(low=low_i, high=high_i)
    return None


def infer_plugins(raw_strip: Dict[str, Any]) -> List[Plugin]:
    plugins: List[Plugin] = []
    # Look for instrument and insert slots
    possibles = []
    for key in ("instrument", "instrumentPlugin", "softwareInstrument"):
        v = raw_strip.get(key)
        if isinstance(v, dict):
            possibles.append(v)
    inserts = raw_strip.get("inserts") or raw_strip.get("audioFX") or []
    if isinstance(inserts, list):
        possibles.extend([x for x in inserts if isinstance(x, dict)])

    for p in possibles:
        name = _first_str(p, ["name", "Name", "title", "Title"]) or "Plugin"
        manufacturer = _first_str(p, ["manufacturer", "maker"]) or None
        kind = _first_str(p, ["type", "kind"]) or None
        ident = _first_str(p, ["identifier", "bundleID", "componentID"]) or None
        params = p.get("params") if isinstance(p.get("params"), dict) else {}
        plugins.append(Plugin(name=name, manufacturer=manufacturer, kind=kind, identifier=ident, params=params))

    return plugins


def _first_str(d: Dict[str, Any], keys: List[str]) -> Optional[str]:
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def coerce_int(v: Any) -> Optional[int]:
    try:
        if v is None:
            return None
        return int(v)
    except Exception:
        return None
