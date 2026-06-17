import subprocess
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

"""Module d'extraction du catalogue de mises à jour Microsoft. Il extrait le fichier CAB principal pour obtenir package.cab,
puis extrait package.xml pour savoir quels autres fichiers CAB de package* extraire, et enfin extrait tous les fichiers CAB 
de package* en parallèle."""

# CONFIGURATION
CATALOG_DIR  = os.path.join(os.path.dirname(__file__), "..", "..", "data", "catalog")
EXTRACTED_DIR = os.path.join(CATALOG_DIR, "extracted")
CAB_PATH      = os.path.join(CATALOG_DIR, "wsusscn2.cab")
MAX_WORKERS   = 10


def extract_main_cab():
    """Extract wsusscn2.cab to get package.cab, which contains package.xml and all package*.cab files."""

    os.makedirs(EXTRACTED_DIR, exist_ok=True)
    print("Extracting the main catalog (wsusscn2.cab)...")
    subprocess.run(["expand", CAB_PATH, "-F:*", EXTRACTED_DIR], check=True, capture_output=True)
    print("Main catalog excerpt.")


def extract_package_xml():
    """Extract package.xml from package.cab, which is needed to know which package*.cab files to extract in the next step."""

    print("Extraction of package.xml...")
    package_cab = os.path.join(EXTRACTED_DIR, "package.cab")
    package_xml = os.path.join(EXTRACTED_DIR, "package.xml")

    # extract package.cab from wsusscn2.cab
    subprocess.run(["expand", CAB_PATH, EXTRACTED_DIR, "-f:package.cab"], check=True, capture_output=True)
    # extract package.xml from package.cab
    subprocess.run(["expand", package_cab, package_xml, "-f:package.xml"], check=True, capture_output=True)
    print(f"package.xml extracted ({os.path.getsize(package_xml) // 1_000_000} MB).")


def extract_package(cab_name):
    """Extract a single package*.cab file, which contains the actual update metadata and files."""

    cab_path = os.path.join(EXTRACTED_DIR, cab_name)
    out_dir  = os.path.join(EXTRACTED_DIR, cab_name.replace(".cab", ""))
    os.makedirs(out_dir, exist_ok=True)
    result = subprocess.run(["expand", cab_path, "-F:*", out_dir], capture_output=True)
    return cab_name, result.returncode


def extract_packages(num_workers=MAX_WORKERS):
    """Extract all package*.cab files in parallel, which contain the actual update metadata and files."""

    cabs = sorted([
        f for f in os.listdir(EXTRACTED_DIR)
        if f.startswith("package") and f.endswith(".cab") and f != "package.cab"
    ])
    total = len(cabs)
    print(f"Extraction of {total} packages ({num_workers} workers)...")

    done = 0
    errors = []

    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = {executor.submit(extract_package, cab): cab for cab in cabs}
        for future in as_completed(futures):
            cab_name, code = future.result()
            done += 1
            status = "✓" if code == 0 else "✗"
            print(f"\r  {status} {done}/{total} - {cab_name}          ", end="")
            if code != 0:
                errors.append(cab_name)

    print()
    if errors:
        print(f"Errors : {errors}")
    else:
        print("All package extracted with success.")


def extract_all(num_workers=MAX_WORKERS):
    extract_main_cab()
    extract_package_xml()
    extract_packages(num_workers=num_workers)


if __name__ == "__main__":
    extract_all()