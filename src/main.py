import os
import sys
import shutil
import subprocess
import time
import gc

ROOT_DIR      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR       = os.path.dirname(os.path.abspath(__file__))
EXTRACTED_DIR = os.path.join(ROOT_DIR, "data", "catalog", "extracted")
CSV_DIR       = os.path.join(ROOT_DIR, "data", "csv")
INDEX_JSON    = os.path.join(ROOT_DIR, "index.json")
CAT_REGISTRY  = os.path.join(ROOT_DIR, "category_registry.json")

sys.path.insert(0, os.path.join(SRC_DIR, "etl"))
sys.path.insert(0, os.path.join(SRC_DIR, "parsing"))

from patch_neo4j_memory import patch_neo4j_memory
from download import get_remote_info, get_local_last_modified, save_last_modified, download_cab, CAB_PATH
from extract import extract_main_cab, extract_package_xml, extract_packages
from neo4j_detect import select_dbms_choice, verify_connection
from import_graph import import_graph


def clean_generated_files():
    for path in [INDEX_JSON, CAT_REGISTRY]:
        if os.path.exists(path):
            os.remove(path)
    if os.path.exists(CSV_DIR):
        shutil.rmtree(CSV_DIR)
    if os.path.exists(EXTRACTED_DIR):
        shutil.rmtree(EXTRACTED_DIR)
    print("Fichiers générés supprimés.")


def run_step(label, script_path, env):
    print(f"\n=== {label} ===")
    t = time.time()
    result = subprocess.run(["python", script_path], env=env, cwd=ROOT_DIR)
    elapsed = time.time() - t
    print(f"--- {label} : {elapsed:.1f}s ---")
    if result.returncode != 0:
        print(f"Erreur lors de : {label}")
        sys.exit(1)


def main():
    pipeline_start = time.time()
    print("=== Knowledge Graph wsusscn2 — Pipeline V3 ===\n")

    # Étape 1 — Vérification catalogue
    print("--- Vérification du catalogue ---")
    t = time.time()
    remote, size_mb = get_remote_info()
    local = get_local_last_modified()
    new_version = (remote != local) or not os.path.exists(CAB_PATH)
    if new_version:
        if local and remote != local:
            print(f"Nouvelle version disponible : {remote}")
        else:
            print("Aucune version locale détectée.")
        print(f"Taille : ~{size_mb} MB — Durée estimée : ~{round(size_mb/100)} min (100 Mb/s)\n")
        choix = input("Télécharger ? (o/n) : ").strip().lower()
        if choix != "o":
            if not os.path.exists(CAB_PATH):
                print("Aucun catalogue disponible. Abandon.")
                sys.exit(1)
            print("Utilisation de la version existante.")
            new_version = False
        else:
            download_cab()
            save_last_modified(remote)
    else:
        print(f"Catalogue à jour ({remote}).")
    print(f"--- Vérification catalogue : {time.time() - t:.1f}s ---")

    # Étape 2 — Extraction
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
        print("Extraction déjà présente — skip.")

    # Étape 3 — Connexion Neo4j
    print("\n--- Connexion Neo4j ---")
    t = time.time()

    # 3a — Sélection de l'instance
    dbms = select_dbms_choice()
    if not dbms:
        print("Abandon.")
        sys.exit(1)
    print(f"Instance sélectionnée : {dbms['name']}")

    # 3b — Mot de passe
    password = input("Mot de passe Neo4j : ").strip()

    # 3c — Patch mémoire si nécessaire
    result = patch_neo4j_memory(dbms["path"])
    if result == "patched":
        input("\n  Redémarrez l'instance dans Neo4j Desktop, puis appuyez sur Entrée pour continuer...")
        print("  Vérification de la connexion...")
        for attempt in range(10):
            if verify_connection(password):
                print("  Connexion OK.")
                break
            print(f"  Tentative {attempt+1}/10 — attente 5s...")
            time.sleep(5)
        else:
            print("  Neo4j inaccessible après 10 tentatives. Abandon.")
            sys.exit(1)

    # 3d — Vérification connexion avec retry
    print("  Vérification de la connexion...")
    for attempt in range(10):
        if verify_connection(password):
            print("  Connexion OK.")
            break
        print(f"  Tentative {attempt+1}/10 — attente 5s...")
        time.sleep(5)
    else:
        print("  Neo4j inaccessible après 10 tentatives. Abandon.")
        sys.exit(1)

    print(f"--- Connexion Neo4j : {time.time() - t:.1f}s ---")

    # Étape 4 — Pipeline ETL
    env = os.environ.copy()
    env["WSUS_DIR"] = EXTRACTED_DIR

    run_step("Indexation",          os.path.join(SRC_DIR, "parsing", "build_index.py"), env)
    run_step("Registre catégories", os.path.join(SRC_DIR, "etl", "explore_cat_names.py"), env)
    gc.collect()
    run_step("Export CSV",          os.path.join(SRC_DIR, "etl", "export_csv.py"), env)

    # Étape 5 — Import Neo4j
    print("\n=== Import Neo4j ===")
    t = time.time()
    import_graph("bolt://127.0.0.1:7687", password, CSV_DIR, dbms["import_dir"])
    print(f"--- Import Neo4j : {time.time() - t:.1f}s ---")

    total = time.time() - pipeline_start
    print(f"\n=== Pipeline terminée — Total : {total:.1f}s ({total/60:.1f} min) ===")


if __name__ == "__main__":
    main()