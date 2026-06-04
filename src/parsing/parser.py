import xml.etree.ElementTree as ET
import os
import json
import time
import base64
import hashlib
from lxml import etree

"""This script parses package.xml and the corresponding /x/, /l/en/, /c/ and /e/ files to extract
all information needed to build the V3 knowledge graph model.
It reuses build_index.py to directly access relevant files via revision ID without iterating
through all packages for each update."""


NS = "http://schemas.microsoft.com/msus/2004/02/OfflineSync"
WSUS_DIR = os.environ["WSUS_DIR"]
PACKAGE_XML = os.path.join(WSUS_DIR, "package.xml")
_ASM_NS = "urn:schemas-microsoft-com:asm.v3"

if not os.path.exists("index.json"):
    import build_index

with open("index.json") as f:
    index = json.load(f)


def _read_wrapped(path):
    """Read a file and return its content parsed as XML wrapped in <root>."""
    with open(path, "rb") as f:
        return etree.fromstring(b"<root>" + f.read() + b"</root>")


def _get_path(revision_id, folder, subfolder=None):
    """Return the full path to a revision file if it exists, else None."""
    if revision_id not in index:
        return None
    entry = index[revision_id]
    parts = [WSUS_DIR, entry["package"], folder]
    if subfolder:
        parts.append(subfolder)
    parts.append(revision_id)
    path = os.path.join(*parts)
    return path if os.path.exists(path) else None


_PERMANENCE_RANK = {"permanent": 0, "permanentUntilReset": 1, "temporary": 2}

def _most_restrictive_permanence(values):
    """Return the most restrictive permanence value from a list."""
    ranked = [v for v in values if v in _PERMANENCE_RANK]
    return min(ranked, key=lambda v: _PERMANENCE_RANK[v]) if ranked else None


def parse_update(update):
    """Extract all attributes from a package.xml <Update> element.
    Handles prerequisites with isOr flag, categories, bundled_by, superseded_by and url."""

    # Prerequisites with isOr flag — direct UpdateId children are isOr:false, those inside <Or> are isOr:true
    prerequisites = []
    prereq_node = update.find(f"{{{NS}}}Prerequisites")
    if prereq_node is not None:
        for child in prereq_node:
            tag = child.tag.split("}")[-1]
            if tag == "UpdateId":
                prerequisites.append({"id": child.get("Id"), "is_or": False})
            elif tag == "Or":
                for uid in child.findall(f"{{{NS}}}UpdateId"):
                    prerequisites.append({"id": uid.get("Id"), "is_or": True})

    categories = []
    cats_node = update.find(f"{{{NS}}}Categories")
    if cats_node is not None:
        categories = [
            {"type": cat.get("Type"), "id": cat.get("Id")}
            for cat in cats_node.findall(f"{{{NS}}}Category")
        ]

    bundled_by = []
    bundled_node = update.find(f"{{{NS}}}BundledBy")
    if bundled_node is not None:
        bundled_by = [ref.get("Id") for ref in bundled_node.findall(f"{{{NS}}}Revision")]

    superseded_by = []
    superseded_node = update.find(f"{{{NS}}}SupersededBy")
    if superseded_node is not None:
        superseded_by = [ref.get("Id") for ref in superseded_node.findall(f"{{{NS}}}Revision")]

    # Languages for HAS_LANGUAGE relation
    languages = [
        lang.get("Name")
        for lang in update.findall(f"{{{NS}}}Language")
        if lang.get("Name")
    ]

    return {
        "update_id":         update.get("UpdateId"),
        "revision_id":       update.get("RevisionId"),
        "revision_number":   update.get("RevisionNumber"),
        "creation_date":     update.get("CreationDate"),
        "default_language":  update.get("DefaultLanguage"),
        "is_leaf":           update.get("IsLeaf"),
        "is_bundle":         update.get("IsBundle"),
        "is_software":       update.get("IsSoftware"),
        "deployment_action": update.get("DeploymentAction"),
        "languages":         languages,
        "prerequisites":     prerequisites,
        "categories":        categories,
        "bundled_by":        bundled_by,
        "superseded_by":     superseded_by,
    }


def get_x_data(revision_id):
    """Parse /x/<revision_id> and return ExtendedProperties attributes, KB, CVEs,
    MsiData/productCode, and all UpdateBehavior components."""
    if not index.get(revision_id, {}).get("has_x"):
        return {}

    path = _get_path(revision_id, "x")
    if not path:
        return {}

    root = _read_wrapped(path)
    props = root.find("ExtendedProperties")
    if props is None:
        return {}

    kb_node = props.find("KBArticleID")
    kb_id = f"KB{kb_node.text}" if kb_node is not None and kb_node.text else None

    bulletin_node = props.find("SecurityBulletinID")
    bulletin_id = bulletin_node.text if bulletin_node is not None else None

    cve_ids = [node.text for node in props.findall("CveID") if node.text]

    # productCode — normalized to lowercase
    product_code = None
    msi_node = root.find(".//MsiData")
    if msi_node is not None:
        raw = msi_node.get("ProductCode")
        if raw:
            product_code = raw.lower()

    # Handler — keep only the part after the last /
    handler = None
    handler_raw = props.get("Handler")
    if handler_raw:
        handler = handler_raw.split("/")[-1]

    install = props.find("InstallationBehavior")
    reboot_behavior        = install.get("RebootBehavior")             if install is not None else None
    can_request_user_input = install.get("CanRequestUserInput")        if install is not None else None
    impact                 = install.get("Impact")                     if install is not None else None
    requires_network       = install.get("RequiresNetworkConnectivity") if install is not None else None

    patching_type = None
    file_node = root.find("Files/File")
    if file_node is not None:
        patching_type = file_node.get("PatchingType")

    uninstall = props.find("UninstallationBehavior")
    reboot_behavior_uninstall = uninstall.get("RebootBehavior") if uninstall is not None else None

    return {
        "msr_severity":                props.get("MsrcSeverity"),
        "browse_only":                 props.get("BrowseOnly"),
        "is_beta":                     props.get("IsBeta"),
        "release_version":             props.get("ReleaseVersion"),
        "release_revision":            props.get("ReleaseRevision"),
        "min_download_size":           props.get("MinDownloadSize"),
        "max_download_size":           props.get("MaxDownloadSize"),
        "recommended_hard_disk_space": props.get("RecommendedHardDiskSpace"),
        "recommended_memory":          props.get("RecommendedMemory"),
        "recommended_cpu_speed":       props.get("RecommendedCpuSpeed"),
        "can_source_be_required":      props.get("CanSourceBeRequired"),
        "requires_reacceptance":       props.get("RequiresReacceptanceOfEula"),
        "product_code":                product_code,
        "kb_article_id":               kb_id,
        "bulletin_id":                 bulletin_id,
        "cve_ids":                     cve_ids,
        # UpdateBehavior components (combined with /c/ permanence and selfUpdate in export_csv)
        "handler":                     handler,
        "reboot_behavior":             reboot_behavior,
        "can_request_user_input":      can_request_user_input,
        "impact":                      impact,
        "requires_network_connectivity": requires_network,
        "patching_type":               patching_type,
        "reboot_behavior_uninstall":   reboot_behavior_uninstall,
    }


def get_l_data(revision_id):
    """Parse /l/en/<revision_id> and return all localized text fields.
    Also returns available language codes for the HAS_LANGUAGE relation."""
    if not index.get(revision_id, {}).get("has_l"):
        return {}

    path = _get_path(revision_id, "l", "en")
    if not path:
        return {}

    root = _read_wrapped(path)

    title           = root.find(".//Title")
    description     = root.find(".//Description")
    more_info_url   = root.find(".//MoreInfoUrl")
    support_url     = root.find(".//SupportUrl")
    uninstall_notes = root.find(".//UninstallNotes")

    # Languages pre-computed in build_index.py — avoids 136k × os.listdir() calls
    available_languages = index[revision_id].get("languages", [])

    return {
        "title":               title.text           if title           is not None else None,
        "description":         description.text      if description     is not None else None,
        "more_info_url":       more_info_url.text    if more_info_url   is not None else None,
        "support_url":         support_url.text      if support_url     is not None else None,
        "uninstall_notes":     uninstall_notes.text  if uninstall_notes is not None else None,
        "available_languages": available_languages,
    }


def get_c_data(revision_id):
    """Parse /c/<revision_id> and return Properties, packageExtended and driver attributes.
    Also returns permanence (most restrictive across all package elements), selfUpdate,
    EulaID for HAS_EULA fallback, and AtLeastOne IsCategory entries for BELONGS_TO."""
    if not index.get(revision_id, {}).get("has_c"):
        return {}

    path = _get_path(revision_id, "c")
    if not path:
        return {}

    root = _read_wrapped(path)

    props = root.find("Properties")
    update_type           = props.get("UpdateType")           if props is not None else None
    explicitly_deployable = props.get("ExplicitlyDeployable") if props is not None else None
    eula_id               = props.get("EulaID")               if props is not None else None

    completely_offline = None
    pkg_ext = root.find(f".//{{{_ASM_NS}}}packageExtended")
    if pkg_ext is None:
        pkg_ext = root.find(".//packageExtended")
    if pkg_ext is not None:
        completely_offline = pkg_ext.get("completelyOfflineCapable")

    inf = None
    driver_node = root.find(f".//{{{_ASM_NS}}}driver")
    if driver_node is None:
        driver_node = root.find(".//driver")
    if driver_node is not None:
        inf = driver_node.get("inf")

    # permanence — most restrictive value across all <package> elements
    permanence_values = [
                            pkg.get("permanence")
                            for pkg in root.findall(f".//{{{_ASM_NS}}}package") + root.findall(".//package")
                            if pkg.get("permanence")
                        ]
    permanence = _most_restrictive_permanence(permanence_values)

    auto_select = props.get("AutoSelectOnWebSites") if props is not None else None

    # selfUpdate — true when present on any <package> element
    self_update = None
    for pkg in root.findall(f".//{{{_ASM_NS}}}package") + root.findall(".//package"):
        if pkg.get("selfUpdate") is not None:
            self_update = pkg.get("selfUpdate")
            break

    # AtLeastOne IsCategory="true" — category IDs for BELONGS_TO source:AtLeastOne
    at_least_one_categories = []
    for al in root.findall(".//AtLeastOne"):
        if al.get("IsCategory") == "true":
            for uid in al.findall("UpdateId"):
                cat_id = uid.get("Id")
                if cat_id:
                    at_least_one_categories.append(cat_id)

    return {
        "update_type":               update_type,
        "explicitly_deployable":     explicitly_deployable,
        "eula_id":                   eula_id,
        "completely_offline_capable": completely_offline,
        "inf":                       inf,
        "permanence":                permanence,
        "self_update":               self_update,
        "at_least_one_categories":   at_least_one_categories,
        "auto_select_on_websites":   auto_select,
    }


def get_e_data(revision_id):
    """Parse /e/<revision_id> and return all EulaFile entries as a list.
    digest is converted from base64 SHA1 to uppercase hex as primary key.
    sha256Digest comes from the AdditionalDigest child text (present on ~64.8%)."""
    if not index.get(revision_id, {}).get("has_e"):
        return []

    path = _get_path(revision_id, "e", "en")
    if not path:
        return []

    root = _read_wrapped(path)
    eulas = []

    for eula_file in root.findall("EulaFile"):
        digest_b64 = eula_file.get("Digest")
        if not digest_b64:
            continue
        digest_hex = base64.b64decode(digest_b64).hex().upper()

        additional = eula_file.find("AdditionalDigest")
        sha256_digest = additional.text if additional is not None else None

        eulas.append({
            "digest":        digest_hex,
            "file_name":     eula_file.get("FileName"),
            "size":          eula_file.get("Size"),
            "language":      eula_file.get("Language"),
            "sha256_digest": sha256_digest,
        })

    return eulas


def compute_behavior_id(handler, reboot_behavior, can_request_user_input, impact,
                         requires_network, patching_type, reboot_behavior_uninstall,
                         permanence, self_update):
    """Compute a stable MD5 key for an UpdateBehavior node from its 9 attributes."""
    combo = "|".join([
        handler                   or "",
        reboot_behavior           or "",
        can_request_user_input    or "",
        impact                    or "",
        requires_network          or "",
        patching_type             or "",
        reboot_behavior_uninstall or "",
        permanence                or "",
        self_update               or "",
    ])
    return hashlib.md5(combo.encode()).hexdigest()


if __name__ == "__main__":
    tree = ET.parse(PACKAGE_XML)
    root = tree.getroot()
    updates_node = root.find(f"{{{NS}}}Updates")
    updates = updates_node.findall(f"{{{NS}}}Update")

    test_lengths = [len(updates)]

    for i in test_lengths:
        start = time.time()
        for u in updates[:i]:
            data = parse_update(u)
            rid  = data["revision_id"]
            data.update(get_x_data(rid))
            data.update(get_l_data(rid))
            data.update(get_c_data(rid))
            data["eulas"] = get_e_data(rid)
        duration = time.time() - start
        print(f"{i} updates : {duration:.2f}s")