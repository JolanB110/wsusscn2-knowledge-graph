import subprocess
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

CATALOG_DIR  = os.path.join(os.path.dirname(__file__), "..", "..", "data", "catalog")
EXTRACTED_DIR = os.path.join(CATALOG_DIR, "extracted")
CAB_PATH      = os.path.join(CATALOG_DIR, "wsusscn2.cab")
MAX_WORKERS   = 12


def extract_main_cab():
    """Passe 1 — extrait les package*.cab et index.xml depuis wsusscn2.cab."""
    os.makedirs(EXTRACTED_DIR, exist_ok=True)
    print("Extraction du catalogue principal (wsusscn2.cab)...")
    subprocess.run(["expand", CAB_PATH, "-F:*", EXTRACTED_DIR], check=True, capture_output=True)
    print("Catalogue principal extrait.")


def extract_package_xml():
    """Passe 2 — extrait package.xml depuis package.cab en deux passes."""
    print("Extraction de package.xml...")
    package_cab = os.path.join(EXTRACTED_DIR, "package.cab")
    package_xml = os.path.join(EXTRACTED_DIR, "package.xml")

    # Passe 1 : extraire package.cab depuis wsusscn2.cab
    subprocess.run(["expand", CAB_PATH, EXTRACTED_DIR, "-f:package.cab"], check=True, capture_output=True)
    # Passe 2 : extraire package.xml depuis package.cab
    subprocess.run(["expand", package_cab, package_xml, "-f:package.xml"], check=True, capture_output=True)
    print(f"package.xml extrait ({os.path.getsize(package_xml) // 1_000_000} MB).")


def extract_package(cab_name):
    cab_path = os.path.join(EXTRACTED_DIR, cab_name)
    out_dir  = os.path.join(EXTRACTED_DIR, cab_name.replace(".cab", ""))
    os.makedirs(out_dir, exist_ok=True)
    result = subprocess.run(["expand", cab_path, "-F:*", out_dir], capture_output=True)
    return cab_name, result.returncode


def extract_packages():
    """Passe 3 — extrait tous les package*.cab en parallèle."""
    cabs = sorted([
        f for f in os.listdir(EXTRACTED_DIR)
        if f.startswith("package") and f.endswith(".cab") and f != "package.cab"
    ])
    total = len(cabs)
    print(f"Extraction de {total} packages ({MAX_WORKERS} en parallèle)...")

    done = 0
    errors = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(extract_package, cab): cab for cab in cabs}
        for future in as_completed(futures):
            cab_name, code = future.result()
            done += 1
            status = "✓" if code == 0 else "✗"
            print(f"\r  {status} {done}/{total} — {cab_name}          ", end="")
            if code != 0:
                errors.append(cab_name)

    print()
    if errors:
        print(f"Erreurs : {errors}")
    else:
        print("Tous les packages extraits avec succès.")


def extract_all():
    extract_main_cab()
    extract_package_xml()
    extract_packages()


if __name__ == "__main__":
    extract_all()