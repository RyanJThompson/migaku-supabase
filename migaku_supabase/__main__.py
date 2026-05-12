"""Entry point so `python -m migaku_supabase <subcommand>` works."""
from __future__ import annotations

import sys

from migaku_supabase.cli import main


if __name__ == "__main__":
    sys.exit(main())
