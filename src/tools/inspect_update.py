import json
import os
import sys
from lxml import etree
from random import randint

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "parsing"))
import build_index

"""
This script allows Users to inspect the content of a specific update by providing its revision_id. Can be used to explore and
discover the data or to debug specific updates. It relies on the index built bu build_index.py to access the data more efficiently
(unlike tests/test_parser.py which directly parses the x and l files without using the index).
"""

# Modify this path to point to your local WSUS directory
INDEX_PATH = "index.json"
WSUS_DIR = os.environ.get("WSUS_DIR")

# You need to build the index first if it doesn't exist yet
if not os.path.exists(INDEX_PATH):
    print("index.json not found -> do you want to build it now ? (y/n)")
    user_input = input("> ")
    if user_input.lower() == "y":
        # Call the function to build the index
        build_index()
    else:
        exit(1)

# Load the index from the JSON file
with open(INDEX_PATH, "r", encoding="utf-8") as f:
    index = json.load(f)

# This function get the relevant data from the x file before putting it in a dictionnary
def get_x_data(revision_id):
    entry = index.get(revision_id)
    if not entry or not entry.get("has_x"):
        # We return an empty dict if the revision_id is not in the index
        return {} 

    package = entry["package"]
    path = os.path.join(WSUS_DIR, package, "x", revision_id)

    if not os.path.exists(path):
        return {}

    try:
        with open(path, "rb") as f:
            content = f.read()

        root = etree.fromstring(b"<root>" + content + b"</root>")
        props = root.find("ExtendedProperties")

        if props is None:
            return {}

        kb = props.find("KBArticleID")

        return {
            "product_name": props.get("ProductName"),
            "release_version": props.get("ReleaseVersion"),
            "severity": props.get("MsrcSeverity"),
            "kb_article_id": kb.text if kb is not None else None
        }

    except Exception:
        return {}

# Similarly, this function get the title from the l file and return it (or None if not found)
def get_title(revision_id):
    entry = index.get(revision_id)
    if not entry or not entry.get("has_l"):
        return None

    package = entry["package"]
    path = os.path.join(WSUS_DIR, package, "l", "en", revision_id)

    if not os.path.exists(path):
        return None

    try:
        with open(path, "rb") as f:
            content = f.read()

        root = etree.fromstring(b"<root>" + content + b"</root>")
        title = root.find(".//Title")

        return title.text if title is not None else None

    except Exception:
        return None

# We build the answer with as much data needed
def show_update(revision_id):
    if revision_id not in index:
        print("\n revision_id introuvable")
        return

    entry = index[revision_id]

    print("\n====================================")
    print("UPDATE INSPECTOR")
    print("====================================")

    print("\n[Index]")
    print(f"revision_id : {revision_id}")
    print(f"package     : {entry.get('package')}")
    print(f"has_x       : {entry.get('has_x')}")
    print(f"has_l       : {entry.get('has_l')}")

    print("\n[Content]")

    title = get_title(revision_id)
    x_data = get_x_data(revision_id)

    print(f"title          : {title or 'N/A'}")
    print(f"severity       : {x_data.get('severity', 'N/A')}")
    print(f"kb_article_id  : {x_data.get('kb_article_id', 'N/A')}")
    print(f"product_name   : {x_data.get('product_name', 'N/A')}")
    print(f"release_version: {x_data.get('release_version', 'N/A')}")

    print("\n[Raw X Data]")
    print(x_data)

    print("\n[Status]")

    if title and x_data:
        print("FULL UPDATE")
    elif title:
        print("TITLE ONLY")
    elif x_data:
        print("METADATA ONLY")
    else:
        print("NO DATA AVAILABLE")


all_ids = list(index.keys())

print("\n===== SAMPLE IDS =====")
for i in range(10):
    random_id = all_ids[randint(0, len(all_ids) - 1)]
    print(random_id)

print("\nTape un revision_id (ou 'exit')\n")

while True:
    user_input = input("> ")

    if user_input.lower() == "exit":
        break

    show_update(user_input)