import xml.etree.ElementTree as ET
import os
import json
import time
from lxml import etree

"""This script parses the package.xml file and the corresponding x and l files to extract
relevant information about each update, such as its title, severity, KB article ID, etc. 
It demonstrates how to navigate the XML structure of the package.xml file and how to correlate it 
with the x and l files based on the revision ID.

This script is made to be less complex and more readable than parse_test.py because this one use 
build_index.py which allows it to direclty access de relevant x and l files without having to iterate 
through all the packages for each update."""


# definition of namespaces and paths
NS = "http://schemas.microsoft.com/msus/2004/02/OfflineSync"
# Modify this path to point to your local WSUS directory
WSUS_DIR = os.environ["WSUS_DIR"]
PACKAGE_XML = os.path.join(WSUS_DIR, "package.xml")


# We create the index using build_index.py if it doesn't exists yet
if not os.path.exists("index.json"):
    import build_index

# Then we load the JSON into a index variable to use it for the parsing
with open("index.json") as f:
    index = json.load(f)

#print(index.get("278")) -> {'package': 'package2', 'has_x': True, 'has_l': True}
# Test to check if the index is working



def parse_update(update):
    prerequisites = update.find(f"{{{NS}}}Prerequisites")
    prereq_ids = []
    
    # We extract the UpdateId of each prerequisite if they exist, otherwise we return an empty list
    if prerequisites is not None:
        prereq_ids = [
            uid.get('Id')
            for uid in prerequisites.findall(f"{{{NS}}}UpdateId")
        ]

    categories = update.find(f"{{{NS}}}Categories")
    cats = []

    # Same thing for categories, we extract the Type and Id of each category if they exist, otherwise we return an empty list
    if categories is not None:
        cats = [
            {"type": cat.get('Type'), "id": cat.get('Id')}
            for cat in categories.findall(f"{{{NS}}}Category")
        ]

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



def get_x_data(revision_id, index):
    if revision_id not in index:
        return {}
    if not index[revision_id]["has_x"]:
        return {}
    
    package = index[revision_id]["package"]
    
    candidate = os.path.join(WSUS_DIR, package, "x", revision_id)
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
    return {}



def get_title(revision_id, index):
    if revision_id not in index:
        return None
    if not index[revision_id]["has_l"]:
        return None
    
    package = index[revision_id]["package"]
    
    candidate = os.path.join(WSUS_DIR, package, "l", "en", revision_id)
    if os.path.exists(candidate):
        with open(candidate, 'rb') as f:
            content = f.read()
        l_root = etree.fromstring(b"<root>" + content + b"</root>")
        title = l_root.find(".//Title")
        return title.text if title is not None else None
    return None



# Principal function that builds the full update data by combining the information using the previous functions
def build_full_update(update):
    data = parse_update(update)
    revision_id = data["revision_id"]
    data.update(get_x_data(revision_id, index))
    data["title"] = get_title(revision_id, index)
    return data


# Principal execution of the script, we parse the package.xml file and extract all the updates
tree = ET.parse(PACKAGE_XML)
root = tree.getroot()
updates_node = root.find(f"{{{NS}}}Updates")
updates = updates_node.findall(f"{{{NS}}}Update")

# This is a test on the 5 first updates to check if the full data is correctly built, you can remove the comment to execute it
"""
print(f"Nombre d'updates : {len(updates)}")
# We build the full update data for the first 5 updates to validate the approach
for u in updates[:5]:
    result = build_full_update(u)
    print(f"\n--- {result['revision_id']} ---")
    print(f"Title    : {result.get('title')}")
    print(f"Severity : {result.get('severity')}")
    print(f"KB       : {result.get('kb_article_id')}")
"""

# The output will be a JSON file containing the full data for all the updates
# with 5 different lengths of test : 10, 100, 1000, 10.000 (We will try all of the Update later)
# and we will check the execution time for each of them to see how it scales with the number of updates.

test_lengths = [10, 100, 1000, 10000, 100000, len(updates)]

os.makedirs("data/output", exist_ok=True)

for i in test_lengths:
    results = []
    start = time.time()

    for u in updates[:i]:
        results.append(build_full_update(u))

    end = time.time()
    duration = end - start

    # Output is done in data/output, the JSON's files aren't commited to the repo and can ba created using this script
    with open(f"data/output/output_sample_{i}.json", "w") as f:
        json.dump(results, f, indent=2)

    if duration > 60:
        mins = duration / 60
        print(f"{i} updates : {mins:.2f} min, {duration - mins * 60:.2f}s")
    else:
        print(f"{i} updates : {duration:.2f}s")