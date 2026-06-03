import os
import json
from neo4j import GraphDatabase


def find_neo4j_dbms():
    """Scanne les dbms disponibles et retourne leurs infos."""
    dbms_base = os.path.join(os.environ["USERPROFILE"], ".Neo4jDesktop2", "Data", "dbmss")
    dbms_list = []

    for entry in os.listdir(dbms_base):
        if not entry.startswith("dbms-"):
            continue
        meta_path = os.path.join(dbms_base, entry, "relate.dbms.json")
        import_dir = os.path.join(dbms_base, entry, "import")
        if not os.path.exists(meta_path):
            continue
        with open(meta_path) as f:
            meta = json.load(f)
        dbms_list.append({
            "name":       meta.get("name", entry),
            "uuid":       meta.get("id", entry),
            "import_dir": import_dir,
        })

    return dbms_list


def select_dbms(password):
    """Détecte la base active ou demande à l'user de choisir."""
    dbms_list = find_neo4j_dbms()

    if not dbms_list:
        print("Aucune base Neo4j détectée.")
        return None

    uri = "neo4j://127.0.0.1:7687"
    for dbms in dbms_list:
        try:
            driver = GraphDatabase.driver(uri, auth=("neo4j", password))
            driver.verify_connectivity()
            driver.close()
            print(f"Base active détectée : {dbms['name']}")
            return dbms
        except Exception:
            continue

    print("Bases Neo4j disponibles :")
    for i, dbms in enumerate(dbms_list, 1):
        print(f"  {i}. {dbms['name']} ({dbms['uuid'][:8]}...)")

    choix = input("Choisissez une base (numéro) : ").strip()
    try:
        return dbms_list[int(choix) - 1]
    except (ValueError, IndexError):
        print("Choix invalide.")
        return None