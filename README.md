MainStage to Camelot Converter
================================

This tool converts an Apple MainStage `.concert` file into a best‑effort Camelot Session JSON, preserving the song list (sets/patches) and keyboard splits where possible.

What it does
- Parses a `.concert` bundle (MainStage 3 format) and extracts Sets and Patches.
- Attempts to read instrument channel strips and their key ranges (splits).
- Emits a Camelot‑style JSON session with:
  - Songs = MainStage Sets (by default)
  - Scenes = Patches inside each Set
  - Layers = Instrument strips with key ranges (splits)
- Includes rich metadata (plugin names, MIDI channels, notes) to aid manual adjustments.

Limitations
- MainStage’s internal format is complex and may vary by version. This tool uses heuristics and may not capture every detail (articulation IDs, advanced routing, multi‑mapping, etc.).
- Camelot’s session format is not publicly documented; we emit a reasonable JSON approximation (`.camelot.json`). You may need to tweak fields in Camelot or via a custom importer.

Quick start
1) Install and run with Python 3.10+:

   `python -m ms_to_camelot --input "/path/MyShow.concert" --output out/`

2) Outputs:
   - `out/MyShow.camelot.json` — Camelot‑style session JSON
   - `out/MyShow.extracted.json` — Raw normalized data extracted from the concert
   - `out/MyShow.summary.txt` — Readable summary of songs/scenes/splits

CLI options
- `--flatten-sets`  Map every Patch as an independent Song (no Scenes)
- `--dry-run`       Don’t write files; print a summary instead
- `--verbose`       Print more details while parsing

Notes
- If parsing fails, run with `--verbose` and share the `*.extracted.json` to refine mappings.
- Key ranges are reported in MIDI note numbers (0–127). Names (e.g., C3) are added for readability.

How it maps your show
- Song vs Scene:
  - Non‑flattened: Set → Song, Patch → Scene, Channel Strip → Layer
  - Flattened (`--flatten-sets`): Patch → Song with a single Scene
- Layers: Only “instrument” strips are emitted as layers.
- BPM: Treated as per‑song. When available it is attached to `song.metadata.bpm`.

Legacy bundles (Concert.patch)
- Supports older MainStage bundles where patches live under `Concert.patch/` and sub‑patches are nested folders (e.g., `Sampler/Synclavier.patch`).
- The parser walks nested `.patch` folders and decodes NSKeyedArchiver blobs to recover key ranges and transpose.

Name normalization
- All names (songs, patches, layers, sub‑patch groups) normalize slashes to an em‑dash style separator for readability:
  - `Sampler/Synclavier` → `Sampler — Synclavier`

BPM behavior
- Extracted from MainStage patch data when present. In legacy bundles, it is read from `patch.engineNode.tempo`.
- Non‑flattened export: BPM is set on the Camelot Song (not on each Scene).
- Flattened export: BPM is set on each Camelot Song created from a patch.

Usage examples
- Non‑flattened (Set → Song, Patch → Scene):
  - `python -m ms_to_camelot -i "/path/Show.concert" -o out/ -v`
- Flattened (each Patch becomes a Song):
  - `python -m ms_to_camelot -i "/path/Show.concert" -o out/ --flatten-sets`
- Dry run (summary only):
  - `python -m ms_to_camelot -i "/path/Show.concert" --dry-run`

Outputs
- `*.camelot.json`  Camelot‑style session you can import or adapt.
- `*.extracted.json`  Normalized data that you can inspect or transform.
- `*.summary.txt`  Human‑readable rundown of Songs → Patches → Layers with ranges and transpose.

Importing into Camelot
- Open Camelot and create a new empty setlist/session.
- Use any available JSON import or custom script/importer you have to map the fields.
- At minimum, map:
  - Session `name` → Project name
  - Each `song` (with `metadata.bpm`) → Camelot Song
  - Each Song’s `scenes[]` → Camelot Scenes
  - Each Scene’s `layers[]` → instruments/items, using `keyRange`, `transpose`, `source`
- If your Camelot build expects different field names, adjust with a small transform script using `*.extracted.json` as a reference.

Example Camelot JSON
{
  "version": 1,
  "name": "My Show",
  "source": {"type": "mainstage", "path": "/path/Show.concert"},
  "songs": [
    {
      "name": "All In My Head",
      "metadata": {"bpm": 89},
      "scenes": [
        {
          "name": "All In My Head",
          "metadata": {},
          "layers": [
            {
              "name": "Minimoog",
              "transpose": 0,
              "keyRange": {"low": 0, "high": 127, "lowName": "C-1", "highName": "G9"},
              "source": {"type": "plugin", "name": "Minimoog.cst"}
            }
          ]
        }
      ]
    }
  ]
}

Troubleshooting
- “Could not find ProjectData”: Some .concert bundles store data differently. The parser now searches for `ProjectData(.plist)` and falls back to the largest `.plist` inside.
- Legacy patch depth: Deeply nested sub‑patches are supported; if names look odd, check normalization rules above.
- If key ranges are missing for some layers, they may be stored in vendor‑specific blobs that aren’t decoded yet. Share your `*.extracted.json` so we can improve heuristics.
