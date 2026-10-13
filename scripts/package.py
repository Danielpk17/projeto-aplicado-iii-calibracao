from pathlib import Path
import subprocess
from zipfile import ZIP_DEFLATED, ZipFile


base = Path(__file__).resolve().parents[1]
tracked = subprocess.check_output(["git", "ls-files"], cwd=base, text=True).splitlines()
destination = base / "Entrega_AV3_Calibra.zip"
with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
    for name in tracked:
        archive.write(base / name, name)
print(f"{destination.name}: {len(tracked)} arquivos versionados")
