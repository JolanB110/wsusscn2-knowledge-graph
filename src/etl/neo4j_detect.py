import os
import json
from neo4j import GraphDatabase

"""This module provides functions to detect Neo4j Desktop installations and verify connectivity to the Neo4j database. 
It looks for Neo4j Desktop configurations in the user's profile directory and allows the user to select an instance. 
It also includes a function to verify that the Neo4j database is accessible using the Bolt protocol."""


def find_neo4j_dbms():
    """Search for Neo4j Desktop installations by looking for relate.dbms.json files in the user's profile directory."""

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
    """Detect Neo4j Desktop installations and prompt the user to select one as the active database."""

    dbms_list = find_neo4j_dbms()
    if not dbms_list:
        print("No Neo4j database detected.")
        return None

    print("Available Neo4j databases :")
    for i, dbms in enumerate(dbms_list, 1):
        print(f"  {i}. {dbms['name']}")
    choix = input("Choose the active database (number) : ").strip()
    try:
        dbms = dbms_list[int(choix) - 1]
    except (ValueError, IndexError):
        print("Invalid choice.")
        return None

    # Bolt URI — default 7687, user can override
    bolt_input = input("Bolt URI [bolt://127.0.0.1:7687] : ").strip()
    dbms["bolt_uri"] = bolt_input if bolt_input else "bolt://127.0.0.1:7687"

    return dbms


def verify_connection(bolt_uri: str, password: str) -> bool:
    """Vérifie que Neo4j est accessible sur bolt://127.0.0.1:7687."""

    try:
        driver = GraphDatabase.driver(bolt_uri, auth=("neo4j", password))
        driver.verify_connectivity()
        driver.close()
        return True
    except Exception:
        return False