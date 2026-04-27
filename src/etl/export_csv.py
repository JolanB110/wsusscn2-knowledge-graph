import xml.etree.ElementTree as ET
import os
import json
import csv
import sys

"""
This script exports the data from package.xml and corresponding /x and /l/en files
into CSV files, which can then be imported into a graph database like Neo4j.
"""


# Add the src/parsing folder to the path to reuse ../parsing/parser.py functions
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "parsing"))
from parser import parse_update, get_x_data, get_title, get_c_data, get_eula, index, NS, WSUS_DIR, PACKAGE_XML


# CONFIGURATION

OUTPUT_DIR = "data/csv"     # Output folder (created automatically if it doesn't exist)
SAMPLE_SIZE = None          # Number of updates to export (use None for all)
# |
# V
# /!\ SAMPLE_SIZE will be huge if you set it to None, 
# be careful when running the script for the first time. 

if SAMPLE_SIZE is not None:
    print(f"/!\ SAMPLE_SIZE is set to {SAMPLE_SIZE} -> only the first {SAMPLE_SIZE} updates will be exported.")
else :
    print("/!\ SAMPLE_SIZE is set to None -> all updates will be exported (this may take a while).")
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

print(f"Exporting {len(updates)} updates to CSV...")

# Preparation of lists of rows for each CSV
updates_rows = []
depends_on_rows = []
bundled_by_rows = []
superseded_by_rows = []
rel_belongs_to_rows = []
rel_part_of_rows = []
rel_has_severity_rows = []
rel_referenced_as_rows = []
rel_has_eula_rows = []
rel_in_language_rows = []

products = {}
product_families = {}
update_classifications = {}
languages = set()
kb_articles = set()
severities = set()
eula = {}


product_to_family = {}  

# First pass to build Product -> ProductFamily mapping (for rel_part_of)
for u in updates:
    cats_node = u.find(f"{{{NS}}}Categories")
    if cats_node is None:
        continue
    product_id = None
    family_id  = None
    for cat in cats_node.findall(f"{{{NS}}}Category"):
        if cat.get("Type") == "Product":
            product_id = cat.get("Id")
        elif cat.get("Type") == "ProductFamily":
            family_id = cat.get("Id")
    if product_id and family_id:
        product_to_family[product_id] = family_id

# Second pass to build rows for updates and relations
for u in updates:
    data  = parse_update(u)
    rid   = data["revision_id"]
    x     = get_x_data(rid, index)
    localized = get_title(rid, index)
    c = get_c_data(rid, index)
    title = localized.get("title") if localized else None
    description = localized.get("description") if localized else None

    severity     = x.get("severity")
    kb_article   = x.get("kb_article_id")

    updates_rows.append({
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
        "support_url":             localized.get("support_url") if localized else None,
        "default_language":        data["default_language"],
        "available_languages":     "|".join(localized.get("available_languages", []) if localized else []),
        # Flags
        "is_leaf":                 data["is_leaf"],
        "is_bundle":               data["is_bundle"],
        "deployment_action":       data["deployment_action"],
        "update_type":             c.get("update_type"),
        "explicitly_deployable":   c.get("explicitly_deployable"),
        "auto_select_on_websites": c.get("auto_select_on_websites"),
        # Product info
        "product_name":            x.get("product_name"),
        "release_version":         x.get("release_version"),
    })

    # Severity node + relation
    if severity:
        severities.add(severity)
        rel_has_severity_rows.append({
            "revision_id": rid,
            "severity":    severity
        })

    # KBArticle node + relation
    if kb_article:
        kb_articles.add(kb_article)
        rel_referenced_as_rows.append({
            "revision_id":  rid,
            "kb_article_id": kb_article
        })

    # EulaFile node + relation
    eula_data = get_eula(rid, index)
    if eula_data:
        eula[eula_data["digest_hex"]] = eula_data
        rel_has_eula_rows.append({
            "revision_id": rid,
            "digest_hex":  eula_data["digest_hex"]
        })

    # IN_LANGUAGE
    for lang_code in x.get("languages", []):
        languages.add(lang_code)
        rel_in_language_rows.append({
            "revision_id": rid,
            "language_code": lang_code
        })

    # DEPENDS_ON
    for prereq_id in data.get("prerequisites", []):
        depends_on_rows.append({
            "source_revision_id": rid,
            "target_update_id":   prereq_id
        })

    # BUNDLED_BY
    bundled_by = u.find(f"{{{NS}}}BundledBy")
    if bundled_by is not None:
        for ref in bundled_by.findall(f"{{{NS}}}Revision"):
            bundled_by_rows.append({
                "revision_id":      rid,
                "bundle_update_id": ref.get("Id")
            })

    # SUPERSEDED_BY
    superseded_by = u.find(f"{{{NS}}}SupersededBy")
    if superseded_by is not None:
        for ref in superseded_by.findall(f"{{{NS}}}Revision"):
            superseded_by_rows.append({
                "revision_id":           rid,
                "superseding_update_id": ref.get("Id")
            })

    # BELONGS_TO — categories
    cats_node = u.find(f"{{{NS}}}Categories")
    if cats_node is not None:
        for cat in cats_node.findall(f"{{{NS}}}Category"):
            cat_type = cat.get("Type")
            cat_id   = cat.get("Id")
            if cat_type == "Company" or not cat_id:
                continue

            info = category_registry.get(cat_id, {})
            name = info.get("name")

            if cat_type == "Product":
                products[cat_id] = name
            elif cat_type == "ProductFamily":
                product_families[cat_id] = name
            elif cat_type == "UpdateClassification":
                update_classifications[cat_id] = name

            rel_belongs_to_rows.append({
                "revision_id":   rid,
                "category_type": cat_type,
                "category_id":   cat_id
            })

# PART_OF — Product -> ProductFamily (from pairs collected earlier)
for product_id, family_id in product_to_family.items():
    if product_id in products and family_id in product_families:
        rel_part_of_rows.append({
            "product_id": product_id,
            "family_id":  family_id
        })

# Filter out rows with missing revision_id (should not happen, but just in case)
updates_rows           = [r for r in updates_rows           if r["revision_id"]]
depends_on_rows        = [r for r in depends_on_rows        if r["source_revision_id"]]
bundled_by_rows        = [r for r in bundled_by_rows        if r["revision_id"]]
superseded_by_rows     = [r for r in superseded_by_rows     if r["revision_id"]]
rel_belongs_to_rows    = [r for r in rel_belongs_to_rows    if r["revision_id"]]
rel_has_severity_rows  = [r for r in rel_has_severity_rows  if r["revision_id"]]
rel_referenced_as_rows = [r for r in rel_referenced_as_rows if r["revision_id"]]

# Function to write a list of dicts to a CSV file
def write_csv(filename, rows, fieldnames):
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"  {filename} — {len(rows)} rows")


# Nodes
write_csv("updates.csv", updates_rows, [
    "revision_id", "update_id", "revision_number",
    "creation_date",
    "title", "description", "more_info_url", "support_url",
    "default_language", "available_languages",
    "is_leaf", "is_bundle", "deployment_action",
    "update_type", "explicitly_deployable", "auto_select_on_websites",
    "product_name", "release_version"
])

write_csv("products.csv",
    [{"id": k, "name": v} for k, v in products.items()],
    ["id", "name"]
)

write_csv("product_families.csv",
    [{"id": k, "name": v} for k, v in product_families.items()],
    ["id", "name"]
)

write_csv("update_classifications.csv",
    [{"id": k, "name": v} for k, v in update_classifications.items()],
    ["id", "name"]
)

write_csv("kb_articles.csv",
    [{"kb_article_id": kb} for kb in sorted(kb_articles)],
    ["kb_article_id"]
)

write_csv("severities.csv",
    [{"level": s} for s in sorted(severities)],
    ["level"]
)

write_csv("eula_nodes.csv",
    list(eula.values()),
    ["digest_hex", "file_name", "digest_algorithm", "size", "language"]
)

write_csv("languages.csv",
    [{"code": lang} for lang in sorted(languages)],
    ["code"]
)

# Relations

write_csv("rel_has_eula.csv", rel_has_eula_rows, [
    "revision_id", "digest_hex"
])

write_csv("rel_in_language.csv", rel_in_language_rows, [
    "revision_id", "language_code"
])

write_csv("rel_depends_on.csv", depends_on_rows, [
    "source_revision_id", "target_update_id"
])

write_csv("rel_bundled_by.csv", bundled_by_rows, [
    "revision_id", "bundle_update_id"
])

write_csv("rel_superseded_by.csv", superseded_by_rows, [
    "revision_id", "superseding_update_id"
])

write_csv("rel_belongs_to.csv", rel_belongs_to_rows, [
    "revision_id", "category_type", "category_id"
])

write_csv("rel_part_of.csv", rel_part_of_rows, [
    "product_id", "family_id"
])

write_csv("rel_has_severity.csv", rel_has_severity_rows, [
    "revision_id", "severity"
])

write_csv("rel_referenced_as.csv", rel_referenced_as_rows, [
    "revision_id", "kb_article_id"
])

print("Done.")