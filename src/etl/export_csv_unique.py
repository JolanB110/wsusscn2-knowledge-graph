import xml.etree.ElementTree as ET
import os
import json
import csv
import sys

"""
This script exports the data from package.xml and corresponding /x/, /l/en/, /c/ and /e/ files
into a single flat CSV file for the V3 model, for schema-free exploration.

Each row represents one update with all its attributes inlined.
Multi-valued fields (prerequisites, languages, CVEs, etc.) are pipe-separated (|).
"""

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "parsing"))
from parser import parse_update, get_x_data, get_l_data, get_c_data, get_e_data, compute_behavior_id, index, NS, WSUS_DIR, PACKAGE_XML


# CONFIGURATION

OUTPUT_DIR  = "data/csv"
OUTPUT_FILE = "updates_flat.csv"
SAMPLE_SIZE = 5000
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

if not os.path.exists("category_registry.json"):
    print("category_registry.json not found -> run explore_cat_names.py first")
    sys.exit(1)

with open("category_registry.json", encoding="utf-8") as f:
    category_registry = json.load(f)

tree = ET.parse(PACKAGE_XML)
root = tree.getroot()
updates_node = root.find(f"{{{NS}}}Updates")
updates = updates_node.findall(f"{{{NS}}}Update")

if SAMPLE_SIZE is not None:
    updates = updates[:SAMPLE_SIZE]

print(f"Exporting {len(updates)} updates to {OUTPUT_FILE}...")

rows = []

for u in updates:
    data      = parse_update(u)
    rid       = data["revision_id"]
    x         = get_x_data(rid)
    l         = get_l_data(rid)
    c         = get_c_data(rid)
    eula_list = get_e_data(rid)

    # Categories - inlined as pipe-separated values
    update_cats = {cat["type"]: cat for cat in data.get("categories", [])}
    def _name(cat):
        return category_registry.get(cat["id"], {}).get("name") if cat else None
    def _id(cat):
        return cat["id"] if cat else None

    company_cat = update_cats.get("Company")
    family_cat  = update_cats.get("ProductFamily")
    product_cat = update_cats.get("Product")
    classif_cat = update_cats.get("UpdateClassification")

    # UpdateBehavior key
    permanence  = c.get("permanence")
    self_update = c.get("self_update")
    behavior_id = compute_behavior_id(
        x.get("handler"), x.get("reboot_behavior"), x.get("can_request_user_input"),
        x.get("impact"), x.get("requires_network_connectivity"), x.get("patching_type"),
        x.get("reboot_behavior_uninstall"), permanence, self_update
    )

    # EULAs - pipe-separated digests
    eula_digests = [e["digest"] for e in eula_list]

    rows.append({
        # (:Update) attributes
        "revision_id":                 rid,
        "update_id":                   data["update_id"],
        "revision_number":             data["revision_number"],
        "creation_date":               data["creation_date"],
        "default_language":            data["default_language"],
        "is_leaf":                     data["is_leaf"],
        "is_bundle":                   data["is_bundle"],
        "is_software":                 data["is_software"],
        "deployment_action":           data["deployment_action"],
        "url":                         data["url"],
        "title":                       l.get("title"),
        "description":                 l.get("description"),
        "more_info_url":               l.get("more_info_url"),
        "support_url":                 l.get("support_url"),
        "uninstall_notes":             l.get("uninstall_notes"),
        "msr_severity":                x.get("msr_severity"),
        "browse_only":                 x.get("browse_only"),
        "is_beta":                     x.get("is_beta"),
        "release_version":             x.get("release_version"),
        "release_revision":            x.get("release_revision"),
        "min_download_size":           x.get("min_download_size"),
        "max_download_size":           x.get("max_download_size"),
        "recommended_hard_disk_space": x.get("recommended_hard_disk_space"),
        "recommended_memory":          x.get("recommended_memory"),
        "recommended_cpu_speed":       x.get("recommended_cpu_speed"),
        "can_source_be_required":      x.get("can_source_be_required"),
        "product_code":                x.get("product_code"),
        "update_type":                 c.get("update_type"),
        "explicitly_deployable":       c.get("explicitly_deployable"),
        "completely_offline_capable":  c.get("completely_offline_capable"),
        "inf":                         c.get("inf"),
        # Relations - inlined as pipe-separated IDs
        "languages":           "|".join(data.get("languages", [])),
        "prerequisite_ids":    "|".join([p["id"] for p in data.get("prerequisites", []) if not p["is_or"]]),
        "prerequisite_or_ids": "|".join([p["id"] for p in data.get("prerequisites", []) if p["is_or"]]),
        "bundled_by_ids":      "|".join(data.get("bundled_by", [])),
        "superseded_by_ids":   "|".join(data.get("superseded_by", [])),
        "kb_article_id":       x.get("kb_article_id"),
        "bulletin_id":         x.get("bulletin_id"),
        "cve_ids":             "|".join(x.get("cve_ids", [])),
        "eula_digests":        "|".join(eula_digests),
        "requires_reacceptance": x.get("requires_reacceptance"),
        "behavior_id":         behavior_id,
        # Category - inlined
        "company":                  _name(company_cat),
        "company_id":               _id(company_cat),
        "product_family":           _name(family_cat),
        "product_family_id":        _id(family_cat),
        "product":                  _name(product_cat),
        "product_id":               _id(product_cat),
        "update_classification":    _name(classif_cat),
        "update_classification_id": _id(classif_cat),
        "category_source":          "Category" if any([company_cat, family_cat, product_cat, classif_cat]) else (
                                    "AtLeastOne" if c.get("at_least_one_categories") else None
                                    ),
    })

FIELDNAMES = [
    "revision_id", "update_id", "revision_number", "creation_date",
    "default_language", "is_leaf", "is_bundle", "is_software", "deployment_action", "url",
    "title", "description", "more_info_url", "support_url", "uninstall_notes",
    "msr_severity", "browse_only", "is_beta", "release_version", "release_revision",
    "min_download_size", "max_download_size", "recommended_hard_disk_space",
    "recommended_memory", "recommended_cpu_speed", "can_source_be_required", "product_code",
    "update_type", "explicitly_deployable", "completely_offline_capable", "inf",
    "languages", "prerequisite_ids", "prerequisite_or_ids",
    "bundled_by_ids", "superseded_by_ids",
    "kb_article_id", "bulletin_id", "cve_ids",
    "eula_digests", "requires_reacceptance", "behavior_id",
    "company", "company_id",
    "product_family", "product_family_id",
    "product", "product_id",
    "update_classification", "update_classification_id",
    "category_source",
]

path = os.path.join(OUTPUT_DIR, OUTPUT_FILE)
with open(path, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
    writer.writeheader()
    writer.writerows(rows)

print(f"  {OUTPUT_FILE} - {len(rows)} rows")
print("Done.")