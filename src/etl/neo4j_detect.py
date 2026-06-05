import os
import json
from neo4j import GraphDatabase


def find_neo4j_dbms():
    dbms_base = os.path.join(os.environ["USERPROFILE"], ".Neo4jDesktop2", "Data", "dbmss")
    dbms_list = []
    for entry in os.listdir(dbms_base):
        if not entry.startswith("dbms-"):
            continue
        meta_path = os.path.join(dbms_base, entry, "relate.dbms.json")
        import_dir = os.path.join(dbms_base, entry, "import")
        conf_dir   = os.path.join(dbms_base, entry)
        if not os.path.exists(meta_path):
            continue
        with open(meta_path) as f:
            meta = json.load(f)
        dbms_list.append({
            "name":      meta.get("name", entry),
            "uuid":      meta.get("id", entry),
            "path":      conf_dir,
            "import_dir": import_dir,
        })
    return sorted(dbms_list, key=lambda x: x["name"])


def select_dbms_choice():
    """Liste les instances et demande à l'user de choisir — sans vérifier la connexion."""
    dbms_list = find_neo4j_dbms()
    if not dbms_list:
        print("Aucune base Neo4j détectée.")
        return None

    print("Bases Neo4j disponibles :")
    for i, dbms in enumerate(dbms_list, 1):
        print(f"  {i}. {dbms['name']}")
    choix = input("Choisissez la base active (numéro) : ").strip()
    try:
        return dbms_list[int(choix) - 1]
    except (ValueError, IndexError):
        print("Choix invalide.")
        return None


def verify_connection(password):
    """Vérifie que Neo4j est accessible sur bolt://127.0.0.1:7687."""
    try:
        driver = GraphDatabase.driver("bolt://127.0.0.1:7687", auth=("neo4j", password))
        driver.verify_connectivity()
        driver.close()
        return True
    except Exception:
        return False