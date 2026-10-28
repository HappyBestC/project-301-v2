"""Bind an independently installed, hash-compatible Pulse runtime."""
from pathlib import Path
import argparse, hashlib, json
root = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser(); p.add_argument("installation", type=Path); a = p.parse_args()
target = a.installation.resolve()
manifest = json.loads((root / "research_artifacts/v2_1_battle_composite_injuries_v0.1/validation/admission_v2.json").read_text())
for name, digest in manifest["proof_sha256"].items():
    if name.startswith("pulse/"):
        assert hashlib.sha256((target / name.removeprefix("pulse/")).read_bytes()).hexdigest() == digest, name
link = root / "pulse"
if link.is_symlink(): link.unlink()
elif link.exists(): raise SystemExit("Refusing to replace an existing directory")
link.symlink_to(target, target_is_directory=True)
print(link, "->", target)
