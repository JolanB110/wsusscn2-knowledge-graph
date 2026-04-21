import xml.etree.ElementTree as ET
import os
from lxml import etree

"""This script parses the package.xml file and the corresponding x and l files to extract
relevant information about each update, such as its title, severity, KB article ID, etc. 
It demonstrates how to navigate the XML structure of the package.xml file and how to correlate it 
with the x and l files based on the revision ID.

This script is only a test, the actual parsing and data extraction logic will be implemented
in parse.py, this is just to validate the approach and the structure of the data."""


# definition of namespaces and paths
NS = "http://schemas.microsoft.com/msus/2004/02/OfflineSync"
# Modify this path to point to your local WSUS directory
WSUS_DIR = os.environ["WSUS_DIR"]
PACKAGE_XML = os.path.join(WSUS_DIR, "package.xml")


def parse_update(update):
    prerequisites = update.find(f"{{{NS}}}Prerequisites")
    prereq_ids = []

    # We extract the UpdateId of each prerequisite if they exist, otherwise we return an empty list
    if prerequisites is not None:
        prereq_ids = [uid.get('Id') for uid in prerequisites.findall(f"{{{NS}}}UpdateId")]

    categories = update.find(f"{{{NS}}}Categories")
    cats = []

    # Same thing for categories, we extract the Type and Id of each category if they exist, otherwise we return an empty list
    if categories is not None:
        cats = [{"type": cat.get('Type'), "id": cat.get('Id')} for cat in categories.findall(f"{{{NS}}}Category")]

    return {
        "update_id": update.get('UpdateId'),
        "revision_id": update.get('RevisionId'),
        "revision_number": update.get('RevisionNumber'),
        "creation_date": update.get('CreationDate'),
        "is_leaf": update.get('IsLeaf'),
        "is_bundle": update.get('IsBundle'),
        "deployment_action": update.get('DeploymentAction'),
        "prerequisites": prereq_ids,
        "categories": cats
    }

# We look for the x and l files corresponding to the given revision_id, and we extract the relevant information if they exist
def get_x_data(revision_id):
    for package in os.listdir(WSUS_DIR):
        package_path = os.path.join(WSUS_DIR, package)
        if os.path.isdir(package_path):
            candidate = os.path.join(package_path, "x", revision_id)
            if os.path.exists(candidate):
                with open(candidate, 'rb') as f:
                    content = f.read()
                x_root = etree.fromstring(b"<root>" + content + b"</root>")
                props = x_root.find("ExtendedProperties")
                if props is not None:
                    kb = props.find("KBArticleID")
                    return {
                        "product_name": props.get('ProductName'),
                        "release_version": props.get('ReleaseVersion'),
                        "severity": props.get('MsrcSeverity'),
                        "kb_article_id": kb.text if kb is not None else None
                    }
    # Otherswise we return an empty dict
    return {}

# Same thing for the l files, we look for the one corresponding to the given revision_id, and we extract the title if it exists
def get_title(revision_id):
    for package in os.listdir(WSUS_DIR):
        package_path = os.path.join(WSUS_DIR, package)
        if os.path.isdir(package_path):
            candidate = os.path.join(package_path, "l", "en", revision_id)
            if os.path.exists(candidate):
                with open(candidate, 'r', encoding='utf-8') as f:
                    content = f.read()
                l_root = etree.fromstring(b"<root>" + content.encode('utf-8') + b"</root>")
                title = l_root.find(".//Title")
                return title.text if title is not None else None
    return None



# Principal function that builds the full update data by combining the information using the previous functions
def build_full_update(update):
    data = parse_update(update)
    revision_id = data["revision_id"]
    data.update(get_x_data(revision_id))
    data["title"] = get_title(revision_id)
    return data



# Principal execution of the script, we parse the package.xml file and extract all the updates
tree = ET.parse(PACKAGE_XML)
root = tree.getroot()
updates_node = root.find(f"{{{NS}}}Updates")
updates = updates_node.findall(f"{{{NS}}}Update")

print(f"Nombre d'updates : {len(updates)}")
# We build the full update data for the first 5 updates to validate the approach
for u in updates[:5]:
    result = build_full_update(u)
    print(f"\n--- {result['revision_id']} ---")
    print(f"Title    : {result.get('title')}")
    print(f"Severity : {result.get('severity')}")
    print(f"KB       : {result.get('kb_article_id')}")