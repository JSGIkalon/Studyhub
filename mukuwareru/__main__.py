"""Permite ejecutar la aplicacion con ``python -m mukuwareru``."""

from __future__ import annotations

import sys

from mukuwareru.aplicacion import main

if __name__ == "__main__":
    sys.exit(main())
