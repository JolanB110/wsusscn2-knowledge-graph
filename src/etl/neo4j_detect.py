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



def _read_bolt_port(conf_dir: str) -> int:
    """Read the Bolt port from neo4j.conf, fallback to 7687."""

    conf_path = os.path.join(conf_dir, "conf", "neo4j.conf")
    if not os.path.exists(conf_path):
        return 7687
    with open(conf_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            if key.strip() == "server.bolt.listen_address":
                try:
                    return int(value.strip().rsplit(":", 1)[-1])
                except ValueError:
                    return 7687
    return 7687


def select_dbms_choice():
    """Prompt the user to select a Neo4j Desktop database and provide the Bolt URI."""
    
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

    detected_port = _read_bolt_port(dbms["path"])
    default_uri = f"neo4j://127.0.0.1:{detected_port}"
    bolt_input = input(f"Bolt URI (Enter to use {default_uri}) : ").strip()
    dbms["bolt_uri"] = bolt_input if bolt_input else default_uri

    return dbms


def verify_connection(bolt_uri: str, password: str) -> bool:
    """Verify that Neo4j is reachable at the given Bolt URI."""

    try:
        driver = GraphDatabase.driver(bolt_uri, auth=("neo4j", password))
        driver.verify_connectivity()
        driver.close()
        return True
    except Exception:
        return False