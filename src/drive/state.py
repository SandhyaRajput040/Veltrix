"""
Lightweight local JSON state file that remembers, per tracked source
file, the Drive `modifiedTime` we last successfully downloaded. This
lets the downloader skip files that haven't changed since the last run.

Design decision: a single local JSON file, not a database.
  - We track at most a handful of files (2 today: the daily delta and
    the full catalog snapshot).
  - The job runs once a day, sequentially, from one place -- there is
    no concurrent-writer problem a database would solve here.
  - A JSON file is trivial to inspect, back up, or reset by hand
    (e.g. delete state/drive_state.json to force a full re-download).
If this automation later needs to track many more files, or run from
multiple machines concurrently, this decision should be revisited.
"""

import json
import os
from typing import Dict


def load_state(state_file: str) -> Dict[str, Dict]:
    """
    Load the state file. Returns an empty dict if the file doesn't
    exist yet (first-ever run) or is empty. Raises ValueError if the
    file exists but contains invalid JSON -- we'd rather fail loudly
    than silently treat corrupt state as "nothing downloaded yet" and
    re-download everything without the operator knowing why.
    """
    if not os.path.isfile(state_file):
        return {}

    with open(state_file, "r", encoding="utf-8") as fh:
        content = fh.read().strip()

    if not content:
        return {}

    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"State file {state_file!r} exists but is not valid JSON. "
            "Refusing to guess -- inspect or delete it manually before rerunning."
        ) from exc


def save_state(state_file: str, state: Dict[str, Dict]) -> None:
    """Persist `state` to `state_file`, creating parent directories as needed."""
    parent_dir = os.path.dirname(state_file)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    with open(state_file, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, sort_keys=True)