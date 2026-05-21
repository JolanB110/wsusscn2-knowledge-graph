import xml.etree.ElementTree as ET
import os
import json
import csv
import sys

"""
This script exports the data from package.xml and corresponding /x and /l/en files
into multiple CSV files without pre-named relations, which can then be imported into
a graph database like Neo4j for schema-free exploration.

Each entity type gets its own CSV file. Cross-references between entities are expressed
as junction tables (two ID columns only) — no relation names are imposed, letting the
import tool or LLM discover the model by itself.
"""


# Add the src/parsing folder to the path to reuse ../parsing/parser.py functions
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "parsing"))
from parser import parse_update, get_x_data, get_title, get_c_data, get_eula, index, NS, WSUS_DIR, PACKAGE_XML


# CONFIGURATION

OUTPUT_DIR  = "data/csv"    # Output folder (created automatically if it doesn't exist)
SAMPLE_SIZE = 2000          # Number of updates to export (use None for all)
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

print(f"Exporting {len(updates)} updates to CSV...")

# Preparation of lists of rows for each CSV

# Entity tables
updates_rows     = []
products         = {}   # id -> name
product_families = {}   # id -> name
classifications  = {}   # id -> name
kb_articles      = set()
severities       = set()
languages        = set()
eulas            = {}   # digest_hex -> eula data

# Junction tables (two ID columns only, no relation name)
junc_update_product        = []  # revision_id, product_id
junc_update_family         = []  # revision_id, family_id
junc_update_classification = []  # revision_id, classification_id
junc_update_kb             = []  # revision_id, kb_article_id
junc_update_severity       = []  # revision_id, severity
junc_update_language       = []  # revision_id, language_code
junc_update_eula           = []  # revision_id, digest_hex
junc_update_prerequisite   = []  # revision_id, prerequisite_id
junc_update_bundled_by     = []  # revision_id, bundle_update_id
junc_update_superseded_by  = []  # revision_id, superseding_update_id


for u in updates:
    data      = parse_update(u)
    rid       = data["revision_id"]
    x         = get_x_data(rid, index)
    localized = get_title(rid, index)
    c         = get_c_data(rid, index)
    eula_data = get_eula(rid, index)

    title       = localized.get("title")       if localized else None
    description = localized.get("description") if localized else None

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
        "support_url":             localized.get("support_url")   if localized else None,
        "default_language":        data["default_language"],
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
    })

    # Severity entity + junction
    severity = x.get("severity")
    if severity:
        severities.add(severity)
        junc_update_severity.append({"revision_id": rid, "severity": severity})

    # KBArticle entity + junction
    kb_article = x.get("kb_article_id")
    if kb_article:
        kb_articles.add(kb_article)
        junc_update_kb.append({"revision_id": rid, "kb_article_id": kb_article})

    # EulaFile entity + junction
    if eula_data:
        eulas[eula_data["digest_hex"]] = eula_data
        junc_update_eula.append({"revision_id": rid, "digest_hex": eula_data["digest_hex"]})

    # Language entity + junction
    for lang_code in x.get("languages", []):
        languages.add(lang_code)
        junc_update_language.append({"revision_id": rid, "language_code": lang_code})

    # Prerequisites junction
    for prereq_id in data.get("prerequisites", []):
        junc_update_prerequisite.append({"revision_id": rid, "prerequisite_id": prereq_id})

    # BundledBy junction
    bundled_by = u.find(f"{{{NS}}}BundledBy")
    if bundled_by is not None:
        for ref in bundled_by.findall(f"{{{NS}}}Revision"):
            junc_update_bundled_by.append({"revision_id": rid, "bundle_update_id": ref.get("Id")})

    # SupersededBy junction
    superseded_by = u.find(f"{{{NS}}}SupersededBy")
    if superseded_by is not None:
        for ref in superseded_by.findall(f"{{{NS}}}Revision"):
            junc_update_superseded_by.append({"revision_id": rid, "superseding_update_id": ref.get("Id")})

    # Category entities + junctions
    cats_node = u.find(f"{{{NS}}}Categories")
    if cats_node is not None:
        for cat in cats_node.findall(f"{{{NS}}}Category"):
            cat_type = cat.get("Type")
            cat_id   = cat.get("Id")
            if not cat_id or cat_type == "Company":
                continue
            name = category_registry.get(cat_id, {}).get("name")
            if cat_type == "Product":
                products[cat_id] = name
                junc_update_product.append({"revision_id": rid, "product_id": cat_id})
            elif cat_type == "ProductFamily":
                product_families[cat_id] = name
                junc_update_family.append({"revision_id": rid, "family_id": cat_id})
            elif cat_type == "UpdateClassification":
                classifications[cat_id] = name
                junc_update_classification.append({"revision_id": rid, "classification_id": cat_id})


# Function to write a list of dicts to a CSV file
def write_csv(filename, rows, fieldnames):
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"  {filename} — {len(rows)} rows")


# Entity tables
write_csv("updates.csv", updates_rows, [
    "revision_id", "update_id", "revision_number",
    "creation_date",
    "title", "description", "more_info_url", "support_url",
    "default_language",
    "is_leaf", "is_bundle", "deployment_action",
    "update_type", "explicitly_deployable", "auto_select_on_websites",
    "product_name", "release_version",
])

write_csv("products.csv",
    [{"product_id": k, "name": v} for k, v in products.items()],
    ["product_id", "name"]
)

write_csv("product_families.csv",
    [{"family_id": k, "name": v} for k, v in product_families.items()],
    ["family_id", "name"]
)

write_csv("classifications.csv",
    [{"classification_id": k, "name": v} for k, v in classifications.items()],
    ["classification_id", "name"]
)

write_csv("kb_articles.csv",
    [{"kb_article_id": kb} for kb in sorted(kb_articles)],
    ["kb_article_id"]
)

write_csv("severities.csv",
    [{"severity": s} for s in sorted(severities)],
    ["severity"]
)

write_csv("languages.csv",
    [{"language_code": lang} for lang in sorted(languages)],
    ["language_code"]
)

write_csv("eulas.csv",
    list(eulas.values()),
    ["digest_hex", "file_name", "digest_algorithm", "size", "language"]
)

# Junction tables
write_csv("junc_update_product.csv",        junc_update_product,        ["revision_id", "product_id"])
write_csv("junc_update_family.csv",         junc_update_family,         ["revision_id", "family_id"])
write_csv("junc_update_classification.csv", junc_update_classification, ["revision_id", "classification_id"])
write_csv("junc_update_kb.csv",             junc_update_kb,             ["revision_id", "kb_article_id"])
write_csv("junc_update_severity.csv",       junc_update_severity,       ["revision_id", "severity"])
write_csv("junc_update_language.csv",       junc_update_language,       ["revision_id", "language_code"])
write_csv("junc_update_eula.csv",           junc_update_eula,           ["revision_id", "digest_hex"])
write_csv("junc_update_prerequisite.csv",   junc_update_prerequisite,   ["revision_id", "prerequisite_id"])
write_csv("junc_update_bundled_by.csv",     junc_update_bundled_by,     ["revision_id", "bundle_update_id"])
write_csv("junc_update_superseded_by.csv",  junc_update_superseded_by,  ["revision_id", "superseding_update_id"])

print("Done.")