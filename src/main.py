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
3. Connects to a Neo4j instance, applying a memory patch if necessary.
4. Runs the ETL steps to build the CSV files for Neo4j import.
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
    """Run a step of the pipeline and print elapsed time. Exit if error."""

    print(f"\n=== {label} ===")
    t = time.time()
    result = subprocess.run(["python", script_path], env=env, cwd=ROOT_DIR)
    elapsed = time.time() - t
    print(f"--- {label} : {elapsed:.1f}s ---")
    if result.returncode != 0:
        print(f"Error when : {label}")
        sys.exit(1)


def main():
    """Main function to run the full pipeline."""

    pipeline_start = time.time()
    print("=== Knowledge Graph wsusscn2 ===\n")

    # Étape 1 - Vérification catalogue
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
        print(f"Size : ~{size_mb} MB - Estimated run time : ~{round(size_mb/100)} min (100 Mb/s)\n")
        choix = input("Download ? (o/n) : ").strip().lower()
        if choix != "o":
            if not os.path.exists(CAB_PATH):
                print("No catalog available. Abandon.")
                sys.exit(1)
            print("Use of the existing version.")
            new_version = False
        else:
            download_cab()
            save_last_modified(remote)
    else:
        print(f"Up-to-date catalog ({remote}).")
    print(f"--- Catalog check : {time.time() - t:.1f}s ---")

    # Étape 2 - Extraction
    extracted_ready = (
        os.path.exists(EXTRACTED_DIR) and
        os.path.exists(os.path.join(EXTRACTED_DIR, "package.xml")) and
        len(os.listdir(EXTRACTED_DIR)) > 10
    )
    if new_version or not extracted_ready:
        print("\n--- Extraction ---")
        t = time.time()
        if new_version:
            clean_generated_files()
        extract_main_cab()
        extract_package_xml()
        extract_packages()
        print(f"--- Extraction : {time.time() - t:.1f}s ---")
    else:
        print("Extraction already present - skip.")

    # Étape 3 - Connection Neo4j
    print("\n--- Connection Neo4j ---")
    t = time.time()

    # 3a - Sélection de l'instance
    dbms = select_dbms_choice()
    if not dbms:
        print("Giving up.")
        sys.exit(1)
    print(f"Selected instance : {dbms['name']}")

    # 3b - Mot de passe
    password = input("Neo4j password: ").strip()

    # 3c - Patch mémoire si nécessaire
    result = patch_neo4j_memory(dbms["path"])
    if result == "patched":
        input("\n  Restart the instance in Neo4j Desktop, then press Enter to continue...")
        print("  Checking the connection...")
        for attempt in range(10):
            if verify_connection(password):
                print("  Connexion OK.")
                break
            print(f"  Attempt {attempt+1}/10 - waiting 5s...")
            time.sleep(5)
        else:
            print("  Neo4j inaccessible after 10 attempts. Giving up.")
            sys.exit(1)

    # 3d - Vérification connexion avec retry
    print("  Checking the connection...")
    for attempt in range(10):
        if verify_connection(password):
            print("  Connection OK.")
            break
        print(f"  Attempt {attempt+1}/10 - waiting 5s...")
        time.sleep(5)
    else:
        print("  Neo4j inaccessible after 10 attempts. Giving up.")
        sys.exit(1)

    print(f"--- Neo4j Connection : {time.time() - t:.1f}s ---")

    # Étape 4 - Pipeline ETL
    env = os.environ.copy()
    env["WSUS_DIR"] = EXTRACTED_DIR

    run_step("Indexation",          os.path.join(SRC_DIR, "parsing", "build_index.py"), env)
    run_step("Registre catégories", os.path.join(SRC_DIR, "etl", "explore_cat_names.py"), env)
    gc.collect()
    run_step("Export CSV",          os.path.join(SRC_DIR, "etl", "export_csv.py"), env)

    # Étape 5 - Import Neo4j
    print("\n=== Import Neo4j ===")
    t = time.time()
    import_graph("bolt://127.0.0.1:7687", password, CSV_DIR, dbms["import_dir"])
    print(f"--- Import Neo4j : {time.time() - t:.1f}s ---")

    total = time.time() - pipeline_start
    print(f"\n=== Pipeline completed - Total : {total:.1f}s ({total/60:.1f} min) ===")


if __name__ == "__main__":
    main()