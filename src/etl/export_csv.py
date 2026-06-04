import xml.etree.ElementTree as ET
import os
import json
import csv
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "parsing"))
from parser import parse_update, get_x_data, get_l_data, get_c_data, get_e_data, compute_behavior_id, index, NS, WSUS_DIR, PACKAGE_XML


# CONFIGURATION
OUTPUT_DIR  = "data/csv"
SAMPLE_SIZE = None
NUM_WORKERS = 6  # adjust to your CPU core count

if SAMPLE_SIZE is not None:
    print(f"/!\\ SAMPLE_SIZE is set to {SAMPLE_SIZE} -> only the first {SAMPLE_SIZE} updates will be exported.")
else:
    print("/!\\ SAMPLE_SIZE is set to None -> all updates will be exported.")
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

print(f"Exporting {len(updates)} updates to CSV...")

# First pass: collect category_id -> type mapping (needed by workers)
category_id_to_type = {}
for u in updates:
    cats_node = u.find(f"{{{NS}}}Categories")
    if cats_node is None:
        continue
    for cat in cats_node.findall(f"{{{NS}}}Category"):
        cid  = cat.get("Id")
        ctype = cat.get("Type")
        if cid and ctype:
            category_id_to_type[cid] = ctype


def process_chunk(chunk_data):
    """Process a chunk of (update_xml_string, category_id_to_type) and return all local rows/dicts.
    Workers receive serialized XML strings to avoid pickling ET elements."""
    import xml.etree.ElementTree as ET
    import os, sys, json

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "parsing"))
    from parser import parse_update, get_x_data, get_l_data, get_c_data, get_e_data, compute_behavior_id, NS

    xml_strings, category_id_to_type, cat_registry = chunk_data

    updates_rows           = []
    kb_articles            = {}
    cves                   = set()
    eulas                  = {}
    behaviors              = {}
    languages              = set()
    categories             = {}
    rel_depends_on_rows    = []
    rel_bundled_by_rows    = []
    rel_superseded_by_rows = []
    rel_belongs_to_rows    = []
    rel_has_kb_rows        = []
    rel_fixes_rows         = []
    rel_has_eula_rows      = []
    rel_has_behavior_rows  = []
    rel_has_language_rows  = []
    rel_eula_language_rows = []

    for xml_str in xml_strings:
        u    = ET.fromstring(xml_str)
        data = parse_update(u)
        rid  = data["revision_id"]
        x    = get_x_data(rid)
        l    = get_l_data(rid)
        c    = get_c_data(rid)
        eula_list = get_e_data(rid)

        updates_rows.append({
            "revision_id":                 rid,
            "update_id":                   data["update_id"],
            "revision_number":             data["revision_number"],
            "creation_date":               data["creation_date"],
            "default_language":            data["default_language"],
            "is_leaf":                     data["is_leaf"],
            "is_bundle":                   data["is_bundle"],
            "is_software":                 data["is_software"],
            "deployment_action":           data["deployment_action"],
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
            "auto_select_on_websites":     c.get("auto_select_on_websites"),
        })

        for lang_code in l.get("available_languages", []):
            languages.add(lang_code)
            rel_has_language_rows.append({"revision_id": rid, "language_code": lang_code})

        for prereq in data.get("prerequisites", []):
            rel_depends_on_rows.append({
                "source_revision_id": rid,
                "target_update_id":   prereq["id"],
                "is_or":              prereq["is_or"],
            })

        for bundle_id in data.get("bundled_by", []):
            rel_bundled_by_rows.append({"revision_id": rid, "bundle_update_id": bundle_id})

        for sup_id in data.get("superseded_by", []):
            rel_superseded_by_rows.append({"revision_id": rid, "superseding_update_id": sup_id})

        kb_id = x.get("kb_article_id")
        if kb_id:
            if kb_id not in kb_articles or x.get("bulletin_id"):
                kb_articles[kb_id] = x.get("bulletin_id")
            rel_has_kb_rows.append({"revision_id": rid, "kb_article_id": kb_id})

        for cve_id in x.get("cve_ids", []):
            cves.add(cve_id)
            rel_fixes_rows.append({"revision_id": rid, "cve_id": cve_id})

        requires_reacceptance = x.get("requires_reacceptance")
        for eula in eula_list:
            digest = eula["digest"]
            if digest not in eulas:
                eulas[digest] = eula
            rel_has_eula_rows.append({
                "revision_id":           rid,
                "digest":                digest,
                "requires_reacceptance": requires_reacceptance,
            })
            if eula.get("language"):
                languages.add(eula["language"])
                rel_eula_language_rows.append({"digest": digest, "language_code": eula["language"]})

        permanence  = c.get("permanence")
        self_update = c.get("self_update")
        behavior_id = compute_behavior_id(
            x.get("handler"), x.get("reboot_behavior"), x.get("can_request_user_input"),
            x.get("impact"), x.get("requires_network_connectivity"), x.get("patching_type"),
            x.get("reboot_behavior_uninstall"), permanence, self_update
        )
        if behavior_id not in behaviors:
            behaviors[behavior_id] = {
                "behavior_id":                   behavior_id,
                "handler":                       x.get("handler"),
                "reboot_behavior":               x.get("reboot_behavior"),
                "can_request_user_input":        x.get("can_request_user_input"),
                "impact":                        x.get("impact"),
                "requires_network_connectivity": x.get("requires_network_connectivity"),
                "patching_type":                 x.get("patching_type"),
                "reboot_behavior_uninstall":     x.get("reboot_behavior_uninstall"),
                "permanence":                    permanence,
                "self_update":                   self_update,
            }
        rel_has_behavior_rows.append({"revision_id": rid, "behavior_id": behavior_id})

        update_cats = {cat["type"]: cat for cat in data.get("categories", [])}
        company_cat  = update_cats.get("Company")
        family_cat   = update_cats.get("ProductFamily")
        product_cat  = update_cats.get("Product")
        classif_cat  = update_cats.get("UpdateClassification")

        if any([company_cat, family_cat, product_cat, classif_cat]):
            def _name(cat):
                return cat_registry.get(cat["id"], {}).get("name") if cat else None
            def _id(cat):
                return cat["id"] if cat else None

            cat_key = "|".join([
                _id(company_cat)  or "",
                _id(family_cat)   or "",
                _id(product_cat)  or "",
                _id(classif_cat)  or "",
            ])
            if cat_key not in categories:
                categories[cat_key] = {
                    "category_key":             cat_key,
                    "company":                  _name(company_cat),
                    "company_id":               _id(company_cat),
                    "product_family":           _name(family_cat),
                    "product_family_id":        _id(family_cat),
                    "product":                  _name(product_cat),
                    "product_id":               _id(product_cat),
                    "update_classification":    _name(classif_cat),
                    "update_classification_id": _id(classif_cat),
                }
            rel_belongs_to_rows.append({"revision_id": rid, "category_key": cat_key, "complete": True})

        if not any([company_cat, family_cat, product_cat, classif_cat]):
            for cat_id in c.get("at_least_one_categories", []):
                rel_belongs_to_rows.append({"revision_id": rid, "category_key": cat_id, "complete": False})

    return {
        "updates_rows":           updates_rows,
        "kb_articles":            kb_articles,
        "cves":                   cves,
        "eulas":                  eulas,
        "behaviors":              behaviors,
        "languages":              languages,
        "categories":             categories,
        "rel_depends_on_rows":    rel_depends_on_rows,
        "rel_bundled_by_rows":    rel_bundled_by_rows,
        "rel_superseded_by_rows": rel_superseded_by_rows,
        "rel_belongs_to_rows":    rel_belongs_to_rows,
        "rel_has_kb_rows":        rel_has_kb_rows,
        "rel_fixes_rows":         rel_fixes_rows,
        "rel_has_eula_rows":      rel_has_eula_rows,
        "rel_has_behavior_rows":  rel_has_behavior_rows,
        "rel_has_language_rows":  rel_has_language_rows,
        "rel_eula_language_rows": rel_eula_language_rows,
    }


def chunk_updates(updates, n_chunks):
    """Split updates list into n_chunks roughly equal parts, serialized as XML strings."""
    size = len(updates)
    chunk_size = (size + n_chunks - 1) // n_chunks
    chunks = []
    for i in range(0, size, chunk_size):
        xml_strings = [ET.tostring(u, encoding="unicode") for u in updates[i:i+chunk_size]]
        chunks.append((xml_strings, category_id_to_type, category_registry))
    return chunks


def merge_results(results):
    """Merge all worker results into unified accumulators."""
    updates_rows           = []
    kb_articles            = {}
    cves                   = set()
    eulas                  = {}
    behaviors              = {}
    languages              = set()
    categories             = {}
    rel_depends_on_rows    = []
    rel_bundled_by_rows    = []
    rel_superseded_by_rows = []
    rel_belongs_to_rows    = []
    rel_has_kb_rows        = []
    rel_fixes_rows         = []
    rel_has_eula_rows      = []
    rel_has_behavior_rows  = []
    rel_has_language_rows  = []
    rel_eula_language_rows = []

    for r in results:
        updates_rows           += r["updates_rows"]
        rel_depends_on_rows    += r["rel_depends_on_rows"]
        rel_bundled_by_rows    += r["rel_bundled_by_rows"]
        rel_superseded_by_rows += r["rel_superseded_by_rows"]
        rel_belongs_to_rows    += r["rel_belongs_to_rows"]
        rel_has_kb_rows        += r["rel_has_kb_rows"]
        rel_fixes_rows         += r["rel_fixes_rows"]
        rel_has_eula_rows      += r["rel_has_eula_rows"]
        rel_has_behavior_rows  += r["rel_has_behavior_rows"]
        rel_has_language_rows  += r["rel_has_language_rows"]
        rel_eula_language_rows += r["rel_eula_language_rows"]
        cves                   |= r["cves"]
        languages              |= r["languages"]
        kb_articles.update(r["kb_articles"])
        eulas.update(r["eulas"])
        behaviors.update(r["behaviors"])
        categories.update(r["categories"])

    return {
        "updates_rows":           updates_rows,
        "kb_articles":            kb_articles,
        "cves":                   cves,
        "eulas":                  eulas,
        "behaviors":              behaviors,
        "languages":              languages,
        "categories":             categories,
        "rel_depends_on_rows":    rel_depends_on_rows,
        "rel_bundled_by_rows":    rel_bundled_by_rows,
        "rel_superseded_by_rows": rel_superseded_by_rows,
        "rel_belongs_to_rows":    rel_belongs_to_rows,
        "rel_has_kb_rows":        rel_has_kb_rows,
        "rel_fixes_rows":         rel_fixes_rows,
        "rel_has_eula_rows":      rel_has_eula_rows,
        "rel_has_behavior_rows":  rel_has_behavior_rows,
        "rel_has_language_rows":  rel_has_language_rows,
        "rel_eula_language_rows": rel_eula_language_rows,
    }


def write_csv(filename, rows, fieldnames):
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"  {filename} — {len(rows)} rows")


if __name__ == "__main__":
    start_total = time.time()

    chunks = chunk_updates(updates, NUM_WORKERS)
    print(f"Split into {len(chunks)} chunks of ~{len(chunks[0][0])} updates each")

    results = []
    with ProcessPoolExecutor(max_workers=NUM_WORKERS) as executor:
        futures = {executor.submit(process_chunk, chunk): i for i, chunk in enumerate(chunks)}
        for future in as_completed(futures):
            i = futures[future]
            result = future.result()
            results.append(result)
            print(f"  chunk {i+1}/{len(chunks)} done ({len(result['updates_rows'])} updates)")

    print("Merging results...")
    merged = merge_results(results)

    print("Writing CSVs...")
    write_csv("updates.csv", merged["updates_rows"], [
        "revision_id", "update_id", "revision_number", "creation_date",
        "default_language", "is_leaf", "is_bundle", "is_software", "deployment_action",
        "title", "description", "more_info_url", "support_url", "uninstall_notes",
        "msr_severity", "browse_only", "is_beta", "release_version", "release_revision",
        "min_download_size", "max_download_size", "recommended_hard_disk_space",
        "recommended_memory", "recommended_cpu_speed", "can_source_be_required", "product_code",
        "update_type", "explicitly_deployable", "completely_offline_capable", "inf", "auto_select_on_websites",
    ])
    write_csv("categories.csv", list(merged["categories"].values()), [
        "category_key", "company", "company_id", "product_family", "product_family_id",
        "product", "product_id", "update_classification", "update_classification_id",
    ])
    write_csv("kb_articles.csv",
        [{"kb_article_id": k, "bulletin_id": v} for k, v in merged["kb_articles"].items()],
        ["kb_article_id", "bulletin_id"]
    )
    write_csv("cves.csv",
        [{"cve_id": cve} for cve in sorted(merged["cves"])],
        ["cve_id"]
    )
    write_csv("eulas.csv", list(merged["eulas"].values()), [
        "digest", "file_name", "size", "language", "sha256_digest",
    ])
    write_csv("behaviors.csv", list(merged["behaviors"].values()), [
        "behavior_id", "handler", "reboot_behavior", "can_request_user_input", "impact",
        "requires_network_connectivity", "patching_type", "reboot_behavior_uninstall",
        "permanence", "self_update",
    ])
    write_csv("languages.csv",
        [{"language_code": lang} for lang in sorted(merged["languages"])],
        ["language_code"]
    )
    write_csv("rel_belongs_to.csv",    merged["rel_belongs_to_rows"],    ["revision_id", "category_key", "complete"])
    write_csv("rel_has_kb.csv",        merged["rel_has_kb_rows"],        ["revision_id", "kb_article_id"])
    write_csv("rel_fixes.csv",         merged["rel_fixes_rows"],         ["revision_id", "cve_id"])
    write_csv("rel_has_eula.csv",      merged["rel_has_eula_rows"],      ["revision_id", "digest", "requires_reacceptance"])
    write_csv("rel_has_behavior.csv",  merged["rel_has_behavior_rows"],  ["revision_id", "behavior_id"])
    write_csv("rel_has_language.csv",  merged["rel_has_language_rows"],  ["revision_id", "language_code"])
    write_csv("rel_eula_language.csv", merged["rel_eula_language_rows"], ["digest", "language_code"])
    write_csv("rel_depends_on.csv",    merged["rel_depends_on_rows"],    ["source_revision_id", "target_update_id", "is_or"])
    write_csv("rel_bundled_by.csv",    merged["rel_bundled_by_rows"],    ["revision_id", "bundle_update_id"])
    write_csv("rel_superseded_by.csv", merged["rel_superseded_by_rows"], ["revision_id", "superseding_update_id"])

    print(f"Done. Total: {time.time() - start_total:.2f}s")