import xml.etree.ElementTree as ET
import os
import json
import sys
from lxml import etree

"""This script resolves the names of all categories (Product, ProductFamily, UpdateClassification)
present in the wsusscn2 catalog by mapping their UpdateId to a RevisionId, then reading the
corresponding /l/en/ file to extract the Title.

The output is a JSON file (category_registry.json) used by export_csv.py to label the
category nodes when building the knowledge graph."""


# Add the src/parsing folder to the path to reuse parser.py constants
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "parsing"))
from parser import index, NS, WSUS_DIR, PACKAGE_XML


# We parse the package.xml to get all updates and build a mapping UpdateId -> RevisionId
tree = ET.parse(PACKAGE_XML)
root = tree.getroot()
updates_node = root.find(f"{{{NS}}}Updates")
updates = updates_node.findall(f"{{{NS}}}Update")

# Build dict UpdateId -> RevisionId from package.xml
# This is needed because category IDs in <Categories> are UpdateIds, not RevisionIds
updateid_to_revid = {}
for u in updates:
    uid = u.get("UpdateId")
    rid = u.get("RevisionId")
    if uid and rid:
        updateid_to_revid[uid] = rid


def get_title_from_revid(revision_id):
    """Read /l/en/revision_id and return the Title text, or None if not found."""

    # First check if the revision_id exists in the index and has an /l/ entry
    if revision_id not in index:
        return None
    if not index[revision_id].get("has_l"):
        return None

    package = index[revision_id]["package"]
    path = os.path.join(WSUS_DIR, package, "l", "en", revision_id)

    if not os.path.exists(path):
        return None

    try:
        with open(path, "rb") as f:
            content = f.read()

        # Wrap in <root> to handle potentially malformed XML with multiple root elements
        l_root = etree.fromstring(b"<root>" + content + b"</root>")
        title = l_root.find(".//Title")
        return title.text if title is not None else None

    except Exception:
        return None


def build_category_registry():
    """Collect all distinct category IDs from updates in package.xml,
    resolve their names via /l/en/, and return a dict:
    { category_id: { "type": ..., "name": ..., "revision_id": ... } }

    Company categories are excluded as there is only one (Microsoft)
    and it brings no value to the knowledge graph."""

    registry = {}

    # Iterate over all updates and their categories, resolve names, and populate the registry
    for u in updates:
        cats_node = u.find(f"{{{NS}}}Categories")
        if cats_node is None:
            continue

        for cat in cats_node.findall(f"{{{NS}}}Category"):
            cat_id   = cat.get("Id")
            cat_type = cat.get("Type")

            # Skip already processed IDs
            if not cat_id:
                continue
            if cat_id in registry:
                continue

            # Resolve the name by mapping UpdateId -> RevisionId -> /l/en/ title
            rev_id = updateid_to_revid.get(cat_id)
            name   = get_title_from_revid(rev_id) if rev_id else None

            registry[cat_id] = {
                "type":        cat_type,
                "name":        name,
                "revision_id": rev_id
            }

    return registry

# When run as a script, build the registry and save to JSON for use in export_csv.py
if __name__ == "__main__":
    print("Building category registry...")
    registry = build_category_registry()

    # Print a summary grouped by category type
    by_type = {}
    for cat_id, info in registry.items():
        by_type.setdefault(info["type"], []).append((cat_id, info["name"]))

    for cat_type, entries in sorted(by_type.items()):
        print(f"\n  {cat_type} - {len(entries)} entries")
        for cat_id, name in entries[:5]:
            print(f"    {cat_id} -> {name}")
        if len(entries) > 5:
            print(f"    ... ({len(entries) - 5} more)")

    # Save to JSON for reuse in export_csv.py
    with open("category_registry.json", "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)

    print(f"\nSaved to category_registry.json ({len(registry)} categories)")