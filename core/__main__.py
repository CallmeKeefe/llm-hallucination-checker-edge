"""Enable ``python -m core`` to invoke the command-line interface."""

from core.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
