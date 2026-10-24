"""Shared action names for bundled sprites, offline packs, and controls."""

# Keep the original walk/dance keys compatible with saved packs.
ACTION_FOLDERS = {
    "idle": ("idle",),
    "walk": ("walking", "walk"),
    "running": ("running", "run"),
    "sitting": ("sitting", "sit"),
    "waving": ("waving", "wave"),
    "happy": ("happy",),
    "dance": ("dancing", "dance"),
    "sleeping": ("sleeping", "sleep"),
    "sad": ("sad",),
    "angry": ("angry",),
    "shy": ("shy",),
    "peeking": ("peeking", "peek"),
    "blink": ("blink",),
    "surprised": ("surprised",),
}
ACTIONS = tuple(ACTION_FOLDERS)
ALIASES = {alias: name for name, aliases in ACTION_FOLDERS.items() for alias in aliases}
ACTION_LABELS = {name: aliases[0].capitalize() for name, aliases in ACTION_FOLDERS.items()}
ACTION_SECONDS = {"sitting": 8.0, "sleeping": 15.0, "dance": 6.0, "peeking": 4.0, "blink": 0.22}


def normalize_action(name: str) -> str:
    return ALIASES.get(name.lower(), name.lower())
