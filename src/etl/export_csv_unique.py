import xml.etree.ElementTree as ET
import os
import json
import csv
import sys

"""
This script exports the data from package.xml and corresponding /x and /l/en files
into a single flat CSV file, which can then be imported into a graph database like Neo4j
for schema-free exploration (no pre-modeled nodes or relations).

Each row represents one update with all its attributes inlined.
Multi-valued fields (prerequisites, languages, products, etc.) are pipe-separated (|).
"""


# Add the src/parsing folder to the path to reuse ../parsing/parser.py functions
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "parsing"))
from parser import parse_update, get_x_data, get_title, get_c_data, get_eula, index, NS, WSUS_DIR, PACKAGE_XML


# CONFIGURATION

OUTPUT_DIR  = "data/csv"    # Output folder (created automatically if it doesn't exist)
OUTPUT_FILE = "updates_flat.csv"
SAMPLE_SIZE = 5000          # Number of updates to export (use None for all)
# |
# V
# /!\ SAMPLE_SIZE will be huge if you set it to None,
# be careful when running the script for the first time.
# Neo4j Aura free tier is limited to ~400K elements (nodes + relations combined).
# Start with a small SAMPLE_SIZE and increase if the import is accepted.

if SAMPLE_SIZE is not None:
    print(f"/!\\ SAMPLE_SIZE is set to {SAMPLE_SIZE} -> only the first {SAMPLE_SIZE} updates will be exported.")
else:
    print("/!\\ SAMPLE_SIZE is set to None -> all updates will be exported (this may take a while).")
    print("Press Ctrl+C to abort")

os.makedirs(OUTPUT_DIR, exist_ok=True)

# Load category registry built by explore_cat_names.py
if not os.path.exists("category_registry.json"):
    print("category_registry.json not found -> run explore_cat_names.py first")
    sys.exit(1)

with open("category_registry.json", encoding="utf-8") as f:
    category_registry = json.load(f)

# Parse package.xml
tree = ET.parse(PACKAGE_XML)
root = tree.getroot()
updates_node = root.find(f"{{{NS}}}Updates")
updates = updates_node.findall(f"{{{NS}}}Update")

# Apply sample size
if SAMPLE_SIZE is not None:
    updates = updates[:SAMPLE_SIZE]

print(f"Exporting {len(updates)} updates to {OUTPUT_FILE}...")

rows = []

for u in updates:
    data     = parse_update(u)
    rid      = data["revision_id"]
    x        = get_x_data(rid, index)
    localized = get_title(rid, index)
    c        = get_c_data(rid, index)
    eula_data = get_eula(rid, index)

    title       = localized.get("title")       if localized else None
    description = localized.get("description") if localized else None

    # Collect category info per type, inlined as pipe-separated IDs and names
    product_ids        = []
    product_names      = []
    family_ids         = []
    family_names       = []
    classif_ids        = []
    classif_names      = []

    cats_node = u.find(f"{{{NS}}}Categories")
    if cats_node is not None:
        for cat in cats_node.findall(f"{{{NS}}}Category"):
            cat_type = cat.get("Type")
            cat_id   = cat.get("Id")
            if not cat_id or cat_type == "Company":
                continue
            name = category_registry.get(cat_id, {}).get("name")
            if cat_type == "Product":
                product_ids.append(cat_id)
                product_names.append(name or "")
            elif cat_type == "ProductFamily":
                family_ids.append(cat_id)
                family_names.append(name or "")
            elif cat_type == "UpdateClassification":
                classif_ids.append(cat_id)
                classif_names.append(name or "")

    # Collect bundled_by IDs
    bundled_by_ids = []
    bundled_by = u.find(f"{{{NS}}}BundledBy")
    if bundled_by is not None:
        bundled_by_ids = [ref.get("Id") for ref in bundled_by.findall(f"{{{NS}}}Revision")]

    # Collect superseded_by IDs
    superseded_by_ids = []
    superseded_by = u.find(f"{{{NS}}}SupersededBy")
    if superseded_by is not None:
        superseded_by_ids = [ref.get("Id") for ref in superseded_by.findall(f"{{{NS}}}Revision")]

    rows.append({
        # Identifiers
        "revision_id":             rid,
        "update_id":               data["update_id"],
        "revision_number":         data["revision_number"],
        # Dates
        "creation_date":           data["creation_date"],
        # Localized content
        "title":                   title,
        "description":             description,
        "more_info_url":           localized.get("more_info_url") if localized else None,
        "support_url":             localized.get("support_url")   if localized else None,
        "default_language":        data["default_language"],
        "available_languages":     "|".join(localized.get("available_languages", []) if localized else []),
        # Flags
        "is_leaf":                 data["is_leaf"],
        "is_bundle":               data["is_bundle"],
        "deployment_action":       data["deployment_action"],
        "update_type":             c.get("update_type"),
        "explicitly_deployable":   c.get("explicitly_deployable"),
        "auto_select_on_websites": c.get("auto_select_on_websites"),
        # Product info (from x file)
        "product_name":            x.get("product_name"),
        "release_version":         x.get("release_version"),
        # Security
        "severity":                x.get("severity"),
        "kb_article_id":           x.get("kb_article_id"),
        # Languages (from x file)
        "languages":               "|".join(x.get("languages", [])),
        # Categories — inlined as pipe-separated values
        "product_ids":             "|".join(product_ids),
        "product_names":           "|".join(product_names),
        "product_family_ids":      "|".join(family_ids),
        "product_family_names":    "|".join(family_names),
        "classification_ids":      "|".join(classif_ids),
        "classification_names":    "|".join(classif_names),
        # Relations — inlined as pipe-separated IDs
        "prerequisite_ids":        "|".join(data.get("prerequisites", [])),
        "bundled_by_ids":          "|".join(bundled_by_ids),
        "superseded_by_ids":       "|".join(superseded_by_ids),
        # EULA
        "has_eula":                "true" if eula_data else "false",
        "eula_digest":             eula_data.get("digest_hex") if eula_data else None,
    })

# Write the single flat CSV
FIELDNAMES = [
    "revision_id", "update_id", "revision_number",
    "creation_date",
    "title", "description", "more_info_url", "support_url",
    "default_language", "available_languages",
    "is_leaf", "is_bundle", "deployment_action",
    "update_type", "explicitly_deployable", "auto_select_on_websites",
    "product_name", "release_version",
    "severity", "kb_article_id",
    "languages",
    "product_ids", "product_names",
    "product_family_ids", "product_family_names",
    "classification_ids", "classification_names",
    "prerequisite_ids", "bundled_by_ids", "superseded_by_ids",
    "has_eula", "eula_digest",
]

path = os.path.join(OUTPUT_DIR, OUTPUT_FILE)
with open(path, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
    writer.writeheader()
    writer.writerows(rows)

print(f"  {OUTPUT_FILE} — {len(rows)} rows")
print("Done.")