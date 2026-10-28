#!/usr/bin/env python3
"""
engine/transition_registry.py — Unified Transition Registry for Rendering Studio Engine v2.

Integrates Built-in cinematic transitions and imported transition packs (including the YouTube Pack)
into ONE authoritative registry and data model.

Supports:
  - Built-in transitions (dissolve, wipeleft, fadeblack, fadewhite, fade, fadefast)
  - Imported packs (e.g. youtube_transition_pack with 20 4K overlay clips)
  - Future pack auto-discovery in transition_pack/*/transition_manifest.json
  - Rich metadata: id, name, category, subcategory, asset_path, duration, width, height,
    fps, asset_type, compositing_mode, preview, media_url, source
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
TRANSITION_PACK_DIR = WORKSPACE_DIR / "transition_pack"

# Built-in transition catalog
BUILTIN_TRANSITIONS = [
    {
        "id": "cinematic_dissolve",
        "name": "Cinematic Dissolve",
        "category": "Built-in",
        "subcategory": "Dissolve",
        "asset_type": "xfade",
        "compositing_mode": "xfade",
        "xfade_name": "dissolve",
        "duration": 0.40,
        "width": 1920,
        "height": 1080,
        "fps": 30.0,
        "preview": "/static/img/transitions/cinematic_dissolve.png",
        "media_url": "",
        "source": "native_ffmpeg_xfade",
        "sfx": False,
        "icon": "🎬"
    },
    {
        "id": "dissolve",
        "name": "Cross Dissolve",
        "category": "Built-in",
        "subcategory": "Dissolve",
        "asset_type": "xfade",
        "compositing_mode": "xfade",
        "xfade_name": "fade",
        "duration": 0.35,
        "width": 1920,
        "height": 1080,
        "fps": 30.0,
        "preview": "/static/img/transitions/dissolve.png",
        "media_url": "",
        "source": "native_ffmpeg_xfade",
        "sfx": False,
        "icon": "✨"
    },
    {
        "id": "soft_wipe",
        "name": "Soft Directional Wipe",
        "category": "Built-in",
        "subcategory": "Wipe",
        "asset_type": "xfade",
        "compositing_mode": "xfade",
        "xfade_name": "wipeleft",
        "duration": 0.35,
        "width": 1920,
        "height": 1080,
        "fps": 30.0,
        "preview": "/static/img/transitions/soft_wipe.png",
        "media_url": "",
        "source": "native_ffmpeg_xfade",
        "sfx": True,
        "icon": "↔️"
    },
    {
        "id": "dip_to_black",
        "name": "Dip to Black",
        "category": "Built-in",
        "subcategory": "Fade",
        "asset_type": "xfade",
        "compositing_mode": "xfade",
        "xfade_name": "fadeblack",
        "duration": 0.40,
        "width": 1920,
        "height": 1080,
        "fps": 30.0,
        "preview": "/static/img/transitions/dip_to_black.png",
        "media_url": "",
        "source": "native_ffmpeg_xfade",
        "sfx": False,
        "icon": "⬛"
    },
    {
        "id": "dip_to_white",
        "name": "Dip to White",
        "category": "Built-in",
        "subcategory": "Fade",
        "asset_type": "xfade",
        "compositing_mode": "xfade",
        "xfade_name": "fadewhite",
        "duration": 0.35,
        "width": 1920,
        "height": 1080,
        "fps": 30.0,
        "preview": "/static/img/transitions/dip_to_white.png",
        "media_url": "",
        "source": "native_ffmpeg_xfade",
        "sfx": False,
        "icon": "⬜"
    },
    {
        "id": "fade",
        "name": "Subtle Film Fade",
        "category": "Built-in",
        "subcategory": "Fade",
        "asset_type": "xfade",
        "compositing_mode": "xfade",
        "xfade_name": "fade",
        "duration": 0.30,
        "width": 1920,
        "height": 1080,
        "fps": 30.0,
        "preview": "/static/img/transitions/fade.png",
        "media_url": "",
        "source": "native_ffmpeg_xfade",
        "sfx": False,
        "icon": "🎞️"
    },
    {
        "id": "clean_cut",
        "name": "Clean Cut",
        "category": "Built-in",
        "subcategory": "Cut",
        "asset_type": "xfade",
        "compositing_mode": "xfade",
        "xfade_name": "clean_cut",
        "duration": 0.04,
        "width": 1920,
        "height": 1080,
        "fps": 30.0,
        "preview": "/static/img/transitions/clean_cut.png",
        "media_url": "",
        "source": "native_ffmpeg_xfade",
        "sfx": False,
        "icon": "✂️"
    },
    {
        "id": "slow_dissolve",
        "name": "Slow Cinematic Dissolve",
        "category": "Built-in",
        "subcategory": "Dissolve",
        "asset_type": "xfade",
        "compositing_mode": "xfade",
        "xfade_name": "dissolve",
        "duration": 0.50,
        "width": 1920,
        "height": 1080,
        "fps": 30.0,
        "preview": "/static/img/transitions/slow_dissolve.png",
        "media_url": "",
        "source": "native_ffmpeg_xfade",
        "sfx": False,
        "icon": "🌊"
    }
]


class TransitionRegistry:
    """Authoritative registry for all transition assets in Rendering Studio."""

    _instance = None

    def __init__(self, pack_base_dir: Optional[Path] = None):
        self.pack_base_dir = Path(pack_base_dir or TRANSITION_PACK_DIR).resolve()
        self.transitions: Dict[str, Dict[str, Any]] = {}
        self.alias_map: Dict[str, str] = {}
        self._load_registry()

    @classmethod
    def get_instance(cls, pack_base_dir: Optional[Path] = None) -> "TransitionRegistry":
        if cls._instance is None:
            cls._instance = cls(pack_base_dir)
        return cls._instance

    def _load_registry(self):
        """Register built-in transitions and discover external transition packs."""
        self.transitions.clear()
        self.alias_map.clear()

        # 1. Register Built-in Transitions
        for t in BUILTIN_TRANSITIONS:
            tid = t["id"]
            self.transitions[tid] = dict(t)
            self._register_alias(tid, tid)
            self._register_alias(t["name"].lower().replace(" ", "_"), tid)
            self._register_alias(t["xfade_name"], tid)

        # Aliases for built-in compatibility
        self.alias_map["cross_dissolve"] = "dissolve"
        self.alias_map["soft_dissolve"] = "dissolve"
        self.alias_map["soft_directional"] = "soft_wipe"
        self.alias_map["wipeleft"] = "soft_wipe"
        self.alias_map["wiperight"] = "soft_wipe"
        self.alias_map["fadeblack"] = "dip_to_black"
        self.alias_map["fadewhite"] = "dip_to_white"
        self.alias_map["clean_short"] = "clean_cut"
        self.alias_map["cut"] = "clean_cut"
        self.alias_map["slow_soft_dissolve"] = "slow_dissolve"
        self.alias_map["stronger_cinematic"] = "cinematic_dissolve"

        # 2. Discover and Load Transition Packs
        self._discover_packs()

    def _register_alias(self, alias: str, target_id: str):
        key = alias.strip().lower()
        if key and key not in self.alias_map:
            self.alias_map[key] = target_id

    def _discover_packs(self):
        """Scans transition_pack/ directory for transition packs with manifests."""
        if not self.pack_base_dir.exists():
            return

        # Look for transition_manifest.json in any subfolder
        manifest_files = list(self.pack_base_dir.glob("**/transition_manifest.json"))
        # De-duplicate if nested
        seen_dirs = set()

        for mf in sorted(manifest_files, key=lambda p: len(str(p))):
            pack_dir = mf.parent
            if any(str(pack_dir).startswith(str(d) + "/") or str(pack_dir).startswith(str(d) + "\\") for d in seen_dirs):
                continue
            seen_dirs.add(pack_dir)
            self._load_pack_manifest(mf, pack_dir)

    def _load_pack_manifest(self, manifest_path: Path, pack_dir: Path):
        """Loads a transition pack defined by transition_manifest.json."""
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"[REGISTRY WARNING] Could not read {manifest_path}: {e}")
            return

        pack_name = data.get("pack_name", pack_dir.name)
        category_name = "YouTube Pack" if "youtube" in pack_dir.name.lower() or "light leak" in pack_name.lower() else pack_name
        source_title = data.get("source_title", "Imported Transition Pack")

        for item in data.get("transitions", []):
            tid = item["id"]
            name = item["name"]
            subcat = item.get("category", "Overlay Effect")
            rel_file = item["file"]

            # Locate actual asset file
            asset_file = pack_dir / rel_file
            if not asset_file.exists():
                # Try finding by name in transitions/
                fallback_file = pack_dir / "transitions" / Path(rel_file).name
                if fallback_file.exists():
                    asset_file = fallback_file
                else:
                    # Search recursively in pack_dir
                    found = list(pack_dir.glob(f"**/{Path(rel_file).name}"))
                    if found:
                        asset_file = found[0]

            if not asset_file.exists():
                print(f"[REGISTRY WARNING] Asset not found for {tid}: {rel_file}")
                continue

            # Preview thumbnail path
            preview_file = pack_dir / "previews" / f"{tid}.jpg"
            if not preview_file.exists():
                # Fallback to catalog preview sheet if individual preview not yet made
                preview_file = pack_dir / "transition_preview.png"

            # Compute relative paths for web media serving
            rel_asset = asset_file.relative_to(WORKSPACE_DIR) if str(asset_file).startswith(str(WORKSPACE_DIR)) else asset_file
            rel_preview = preview_file.relative_to(WORKSPACE_DIR) if preview_file.exists() and str(preview_file).startswith(str(WORKSPACE_DIR)) else None

            media_url = f"/media/{rel_asset.as_posix()}"
            preview_url = f"/media/{rel_preview.as_posix()}" if rel_preview else media_url

            entry = {
                "id": tid,
                "name": name,
                "category": category_name,
                "subcategory": subcat,
                "pack_id": pack_dir.name,
                "asset_path": str(asset_file.resolve()),
                "rel_asset_path": rel_asset.as_posix(),
                "duration": float(item.get("duration", 1.0)),
                "width": int(item.get("width", 3840)),
                "height": int(item.get("height", 2160)),
                "fps": float(item.get("fps", 25.0)),
                "asset_type": "overlay_effect",
                "compositing_mode": "screen_blend",
                "preview": preview_url,
                "media_url": media_url,
                "source": source_title,
                "icon": "✨" if "Light" in subcat else ("🔥" if "Burn" in subcat else "⚡")
            }

            self.transitions[tid] = entry
            self._register_alias(tid, tid)
            self._register_alias(f"yt_{tid}", tid)
            self._register_alias(f"youtube_{tid}", tid)
            self._register_alias(name, tid)
            self._register_alias(name.lower().replace(" ", "_"), tid)
            self._register_alias(Path(rel_file).stem, tid)

    def get(self, transition_id_or_name: Optional[str]) -> Optional[Dict[str, Any]]:
        """Lookup transition by ID, name, or alias."""
        if not transition_id_or_name:
            return None
        key = str(transition_id_or_name).strip().lower()
        target_id = self.alias_map.get(key) or self.alias_map.get(key.replace(" ", "_"))
        if target_id and target_id in self.transitions:
            return self.transitions[target_id]
        if transition_id_or_name in self.transitions:
            return self.transitions[transition_id_or_name]
        return None

    def is_overlay_effect(self, transition_id_or_name: Optional[str]) -> bool:
        t = self.get(transition_id_or_name)
        return bool(t and t.get("asset_type") == "overlay_effect")

    def is_builtin(self, transition_id_or_name: Optional[str]) -> bool:
        t = self.get(transition_id_or_name)
        return bool(t and t.get("category") == "Built-in")

    def list_transitions(
        self,
        category: Optional[str] = None,
        subcategory: Optional[str] = None,
        asset_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Return filtered list of transitions in deterministic order."""
        res = []
        for t in self.transitions.values():
            if category and t["category"].lower() != category.lower():
                continue
            if subcategory and t["subcategory"].lower() != subcategory.lower():
                continue
            if asset_type and t["asset_type"] != asset_type:
                continue
            res.append(t)
        return res

    def get_categories(self) -> List[str]:
        """Return unique category names."""
        cats = []
        for t in self.transitions.values():
            if t["category"] not in cats:
                cats.append(t["category"])
        return cats


# Global singleton instance
registry = TransitionRegistry.get_instance()
