"""Loads ``AGENTS.md`` — the agent-facing instructions for this system.

Agents discover how to use FamilyOS by calling ``get_agent_instructions``
(MCP tool) or ``GET /internal/agent/instructions``. Both surfaces read the
same file, so there is one place to edit and no drift.

The file lives at the repository root, which resolves differently in a
container (``/app``) than in a local checkout (``backend/``). Rather than
hard-code one layout, candidate paths are probed in order and the first
readable file wins. ``AGENTS_INSTRUCTIONS_PATH`` overrides the search
entirely, which is how a deployment can point at a bind-mounted copy and
pick up edits without a rebuild.
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_VAR = "AGENTS_INSTRUCTIONS_PATH"
FILENAME = "AGENTS.md"

# ``__file__`` is ``<repo>/backend/app/agent/instructions.py`` in a checkout and
# ``/app/app/agent/instructions.py`` in the image. Walking up from this module
# covers both without assuming which one we are in.
_HERE = Path(__file__).resolve()
_CANDIDATES = (
    _HERE.parents[2] / FILENAME,  # image: /app/AGENTS.md
    _HERE.parents[3] / FILENAME,  # checkout: <repo>/AGENTS.md
)

_FALLBACK = (
    "# FamilyOS Agent Instructions\n\n"
    "Instructions are unavailable: no AGENTS.md was found. "
    "Contact the system administrator.\n"
)


def load_agent_instructions() -> str:
    """Return the AGENTS.md content, or a short notice if it cannot be read.

    Never raises: a missing instructions file must not take down the tool
    call an agent is making, it just has to say so.
    """

    override = os.environ.get(ENV_VAR)
    candidates = (Path(override), *_CANDIDATES) if override else _CANDIDATES

    for path in candidates:
        try:
            return path.read_text(encoding="utf-8")
        except (FileNotFoundError, NotADirectoryError, IsADirectoryError):
            continue
        except OSError:
            continue

    return _FALLBACK
