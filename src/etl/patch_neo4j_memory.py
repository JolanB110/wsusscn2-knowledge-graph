import os
import re


TARGET = {
    "dbms.memory.transaction.total.max": "2g",
}


def _is_already_patched(content):
    for key, value in TARGET.items():
        if not re.search(rf"^{re.escape(key)}={re.escape(value)}\s*$", content, re.MULTILINE):
            return False
    return True


def _apply_patch(content):
    """Uncomment and set target keys in place — never append, never touch other settings."""
    for key, value in TARGET.items():
        new_line = f"{key}={value}"
        # Match commented or uncommented line with this exact key
        pattern = rf"^[ \t]*#[ \t]*{re.escape(key)}[ \t]*=.*$"
        if re.search(pattern, content, re.MULTILINE):
            # Uncomment and set value in place
            content = re.sub(pattern, new_line, content, count=1, flags=re.MULTILINE)
        elif not re.search(rf"^{re.escape(key)}=", content, re.MULTILINE):
            # Key absent entirely — find the Memory block and insert after the comment line
            insert_after = "# The default value is 70% of the heap size limit."
            content = content.replace(insert_after, insert_after + f"\n{new_line}")
    return content


def patch_neo4j_memory(dbms_path):
    conf_path = os.path.join(dbms_path, "conf", "neo4j.conf")
    if not os.path.exists(conf_path):
        print(f"  neo4j.conf introuvable : {conf_path}")
        return "not_found"

    with open(conf_path, "r", encoding="utf-8") as f:
        content = f.read()

    if _is_already_patched(content):
        print("  neo4j.conf déjà configuré — skip")
        return "already_ok"

    print("\n  La configuration Neo4j doit être modifiée pour l'import :")
    print("    dbms.memory.transaction.total.max : → 2g")
    choix = input("\n  Autoriser la modification automatique ? (o/n) : ").strip().lower()

    if choix != "o":
        print("  Modification refusée — l'import tentera de continuer sans patch.")
        print("  /!\\ Des erreurs mémoire sont possibles sur les grosses relations.")
        return "skipped_user"

    new_content = _apply_patch(content)
    with open(conf_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    print("  neo4j.conf patché avec succès.")
    return "patched"