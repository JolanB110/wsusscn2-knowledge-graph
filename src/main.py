import os
import sys
import shutil
import subprocess
import time
import gc

"""This script orchestrates the full pipeline to build the knowledge graph from the wsusscn2 catalog. It performs the following
steps:

1. Checks if a new version of the catalog is available and downloads it if the user agrees.
2. Extracts the catalog data if not already done.
3. Runs the ETL steps (indexation, category registry, CSV export) - skippable if up to date.
4. Connects to a Neo4j instance, applying a memory patch if necessary.
5. Imports the CSV files into Neo4j.

The script is designed to be run from the command line and provides feedback on the progress and timing of each step.
It also handles errors gracefully, exiting if any step fails.
"""


# PATHS TO DATA AND GENERATED FILES
ROOT_DIR      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR       = os.path.dirname(os.path.abspath(__file__))
EXTRACTED_DIR = os.path.join(ROOT_DIR, "data", "catalog", "extracted")
CSV_DIR       = os.path.join(ROOT_DIR, "data", "csv")
INDEX_JSON    = os.path.join(ROOT_DIR, "index.json")
CAT_REGISTRY  = os.path.join(ROOT_DIR, "category_registry.json")

sys.path.insert(0, os.path.join(SRC_DIR, "etl"))
sys.path.insert(0, os.path.join(SRC_DIR, "parsing"))

# Import from local modules
from patch_neo4j_memory import patch_neo4j_memory
from download import get_remote_info, get_local_last_modified, save_last_modified, download_cab, CAB_PATH
from extract import extract_main_cab, extract_package_xml, extract_packages
from neo4j_detect import select_dbms_choice, verify_connection
from import_graph import import_graph

def clean_generated_files():
    """Delete generated files from previous runs."""

    for path in [INDEX_JSON, CAT_REGISTRY]:
        if os.path.exists(path):
            os.remove(path)
    if os.path.exists(CSV_DIR):
        shutil.rmtree(CSV_DIR)
    if os.path.exists(EXTRACTED_DIR):
        shutil.rmtree(EXTRACTED_DIR)
    print("Generated files deleted.")


def run_step(label, script_path, env):
    """Run a pipeline step as a subprocess and print elapsed time. Exit if error."""

    print(f"\n=== {label} ===")
    t = time.time()
    result = subprocess.run(["python", script_path], env=env, cwd=ROOT_DIR)
    elapsed = time.time() - t
    print(f"--- {label} : {elapsed:.1f}s ---")
    if result.returncode != 0:
        print(f"Error when : {label}")
        sys.exit(1)


def wait_for_neo4j(bolt_uri, password):
    """Retry Neo4j connection every 5s, up to 10 attempts. Exit if unreachable."""

    print("  Checking the connection...")
    for attempt in range(10):
        if verify_connection(bolt_uri, password):
            print("  Connection OK.")
            return
        print(f"  Attempt {attempt+1}/10 - waiting 5s...")
        time.sleep(5)
    print("  Neo4j inaccessible after 10 attempts. Giving up.")
    sys.exit(1)


def ask_workers(label, default):
    """Ask the user how many workers to use for a given step. Returns the chosen int."""

    raw = input(f"  Enter number of parallel workers for {label} [recommended: {default}] : ").strip()
    if not raw:
        return default
    try:
        n = int(raw)
        if n < 1:
            print(f"  Invalid value, using recommended ({default}).")
            return default
        return n
    except ValueError:
        print(f"  Invalid value, using recommended ({default}).")
        return default


def csv_ready():
    """Return True if all 17 CSV files are present in CSV_DIR."""

    expected = [
        "updates.csv", "categories.csv", "kb_articles.csv", "cves.csv", "eulas.csv",
        "behaviors.csv", "languages.csv", "rel_belongs_to.csv", "rel_has_kb.csv",
        "rel_fixes.csv", "rel_has_eula.csv", "rel_has_behavior.csv", "rel_has_language.csv",
        "rel_eula_language.csv", "rel_depends_on.csv", "rel_bundled_by.csv", "rel_superseded_by.csv",
    ]
    return all(os.path.exists(os.path.join(CSV_DIR, f)) for f in expected)


def extraction_ready():
    """Return True if all package*.cab files have a corresponding non-empty extracted directory."""

    if not os.path.exists(EXTRACTED_DIR):
        return False
    if not os.path.exists(os.path.join(EXTRACTED_DIR, "package.xml")):
        return False
    cabs = [
        f for f in os.listdir(EXTRACTED_DIR)
        if f.startswith("package") and f.endswith(".cab") and f != "package.cab"
    ]
    if not cabs:
        return False
    for cab in cabs:
        out_dir = os.path.join(EXTRACTED_DIR, cab.replace(".cab", ""))
        if not os.path.exists(out_dir) or not os.listdir(out_dir):
            return False
    return True


def main():
    """Main function to run the full pipeline."""

    pipeline_start = time.time()
    print("=== Knowledge Graph wsusscn2 ===\n")

    # Etape 1 - Catalog verification
    print("--- Catalog verification ---")
    t = time.time()
    remote, size_mb = get_remote_info()
    local = get_local_last_modified()
    new_version = (remote != local) or not os.path.exists(CAB_PATH)
    if new_version:
        if local and remote != local:
            print(f"New version available : {remote}")
        else:
            print("No local version detected.")
        print(f"Size : ~{size_mb} MB\n")
        choix = input("Download ? (y/n) : ").strip().lower()
        if choix != "y":
            if not os.path.exists(CAB_PATH):
                print("No catalog available. Giving up.")
                sys.exit(1)
            print("Using existing version.")
            new_version = False
        else:
            download_cab()
            save_last_modified(remote)
    else:
        print(f"Up-to-date catalog ({remote}).")
    print(f"--- Catalog check : {time.time() - t:.1f}s ---")

    # Etape 2 - Extraction
    if new_version or not extraction_ready():
        print("\n--- Extraction ---")
        t = time.time()
        if new_version:
            clean_generated_files()
        workers_extract = ask_workers("CAB extraction", default=6)
        extract_main_cab()
        extract_package_xml()
        extract_packages(num_workers=workers_extract)
        print(f"--- Extraction : {time.time() - t:.1f}s ---")
    else:
        print("Extraction already present - skip.")

    # Etape 3 - ETL (index, registry, CSV)
    env = os.environ.copy()
    env["WSUS_DIR"] = EXTRACTED_DIR

    index_ready = os.path.exists(INDEX_JSON) and os.path.exists(CAT_REGISTRY)
    files_ready = index_ready and csv_ready()

    skip_etl = False
    if not new_version and files_ready:
        print("\nIndex, registry and CSVs already present.")
        choix = input("Re-generate them anyway ? (y/n) : ").strip().lower()
        skip_etl = (choix != "y")

    if skip_etl:
        print("ETL skipped - using existing files.")
    else:
        # Ask workers once, used for export CSV
        workers_csv = ask_workers("CSV export", default=4)

        if new_version or not index_ready:
            run_step("Indexation",           os.path.join(SRC_DIR, "parsing", "build_index.py"), env)
            run_step("Category registry",    os.path.join(SRC_DIR, "etl", "explore_cat_names.py"), env)
        else:
            print("Index and registry already present - skip.")

        gc.collect()

        # Run export_csv via its run_export() function directly (avoids subprocess worker noise)
        print("\n=== Export CSV ===")
        t = time.time()
        sys.path.insert(0, os.path.join(SRC_DIR, "etl"))
        from export_csv import run_export
        run_export(output_dir=CSV_DIR, sample_size=None, num_workers=workers_csv)
        print(f"--- Export CSV : {time.time() - t:.1f}s ---")

    # Etape 4 - Neo4j connection
    print("\n--- Neo4j connection ---")
    t = time.time()

    dbms = select_dbms_choice()
    if not dbms:
        print("Giving up.")
        sys.exit(1)
    print(f"Selected instance : {dbms['name']}")

    password = input("Neo4j password : ").strip()

    result = patch_neo4j_memory(dbms["path"])
    if result == "patched":
        input("\n  Restart the instance in Neo4j Desktop, then press Enter to continue...")

    wait_for_neo4j(dbms["bolt_uri"], password)
    print(f"--- Neo4j connection : {time.time() - t:.1f}s ---")

    # Etape 5 - Neo4j import
    print("\n=== Import Neo4j ===")
    t = time.time()
    import_graph(dbms["bolt_uri"], password, CSV_DIR, dbms["import_dir"], new_version=new_version)
    print(f"--- Import Neo4j : {time.time() - t:.1f}s ---")

    total = time.time() - pipeline_start
    print(f"\n=== Pipeline completed - Total : {total:.1f}s ({total/60:.1f} min) ===")


if __name__ == "__main__":
    main()