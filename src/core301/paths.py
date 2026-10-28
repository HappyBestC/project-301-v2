from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
# Temporary V1 adapter data; not the authoritative V2 research model.
LEGACY_COMPATIBILITY_ROOT = PROJECT_ROOT / "config" / "compatibility" / "v1"
FROZEN_ROOT = LEGACY_COMPATIBILITY_ROOT  # Preserve existing imports until M3-A migration.
PULSE_ROOT = PROJECT_ROOT / "pulse" / "bin"
