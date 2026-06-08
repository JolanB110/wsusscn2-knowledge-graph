import os
import re

"""Patch Neo4j configuration to set transaction memory limit to 2g, which is necessary for large imports."""

TARGET = {
    "dbms.memory.transaction.total.max": "2g",
}

def _is_already_patched(content):
    """Check if all target keys are already set to the desired values, ignoring comments and whitespace."""

    for key, value in TARGET.items():
        if not re.search(rf"^{re.escape(key)}={re.escape(value)}\s*$", content, re.MULTILINE):
            return False
    return True


def _apply_patch(content):
    """Uncomment and set target keys in place - never append, never touch other settings."""

    for key, value in TARGET.items():
        new_line = f"{key}={value}"
        # Match commented or uncommented line with this exact key
        pattern = rf"^[ \t]*#[ \t]*{re.escape(key)}[ \t]*=.*$"
        if re.search(pattern, content, re.MULTILINE):
            # Uncomment and set value in place
            content = re.sub(pattern, new_line, content, count=1, flags=re.MULTILINE)
        elif not re.search(rf"^{re.escape(key)}=", content, re.MULTILINE):
            # Key absent entirely - find the Memory block and insert after the comment line
            insert_after = "# The default value is 70% of the heap size limit."
            content = content.replace(insert_after, insert_after + f"\n{new_line}")
    return content


def patch_neo4j_memory(dbms_path):
    """Patch Neo4j configuration to set transaction memory limit to 2g, which is necessary for large imports."""

    conf_path = os.path.join(dbms_path, "conf", "neo4j.conf")
    if not os.path.exists(conf_path):
        print(f"  neo4j.conf not found : {conf_path}")
        return "not_found"

    with open(conf_path, "r", encoding="utf-8") as f:
        content = f.read()

    if _is_already_patched(content):
        print("  neo4j.conf already configured - skip")
        return "already_ok"

    print("\n  Neo4j configuration need to be modified :")
    print("    dbms.memory.transaction.total.max : → 2g")
    choix = input("\n  Allow automatic modification ? (o/n) : ").strip().lower()

    if choix != "o":
        print("  Modification denied - import will continue without patch.")
        print("  /!\\ Memory error can be expected.")
        return "skipped_user"

    new_content = _apply_patch(content)
    with open(conf_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    print("  neo4j.conf patched with success.")
    return "patched"