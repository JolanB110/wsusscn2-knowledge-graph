import os
import json

"""This script builds an index of all the revision IDs present in the WSUS directory,
along with the corresponding package and whether the x, l, c and e files exist for each 
revision ID to permit a more efficient parsing in the future, as we will be able to 
directly access the relevant files."""

# set WSUS_DIR from environment variable, with error handling if not set
WSUS_DIR = os.environ.get("WSUS_DIR")
if not WSUS_DIR:
    raise EnvironmentError(
        "The WSUS_DIR environment variable is not set.\n"
        "Run the script via main.py or set WSUS_DIR manually."
    )

index = {}

def _ensure(revision_id, package):
    """Ensure a revision_id entry exists in the index with default values."""

    if revision_id not in index:
        index[revision_id] = {"package": package, "has_x": False, "has_l": False, "has_c": False, "has_e": False, "languages": []}

# We iterate through all the packages in the WSUS directory, and for each package we check if the x and l files exist
for package in os.listdir(WSUS_DIR):
    package_path = os.path.join(WSUS_DIR, package)
    if not os.path.isdir(package_path):
        continue
    
    x_path = os.path.join(package_path, "x")
    l_base = os.path.join(package_path, "l")
    c_path = os.path.join(package_path, "c")
    e_path = os.path.join(package_path, "e", "en")

    # We get the revision IDs from the x and l files names to build the index
    if os.path.exists(x_path):
        for filename in os.listdir(x_path):
            _ensure(filename, package)
            index[filename]["has_x"] = True

    # Traverse all language subdirs at once - build languages list per revision_id
    # This avoids 136k × os.listdir() calls later in get_l_data()
    if os.path.exists(l_base):
        for lang in os.listdir(l_base):
            lang_path = os.path.join(l_base, lang)
            if not os.path.isdir(lang_path):
                continue
            for filename in os.listdir(lang_path):
                _ensure(filename, package)
                if lang == "en":
                    index[filename]["has_l"] = True
                if lang not in index[filename]["languages"]:
                    index[filename]["languages"].append(lang)

    # We do the same for c and e files, but we only care about the existence of the file, not the language
    if os.path.exists(c_path):
        for filename in os.listdir(c_path):
            _ensure(filename, package)
            index[filename]["has_c"] = True

    if os.path.exists(e_path):
        for filename in os.listdir(e_path):
            _ensure(filename, package)
            index[filename]["has_e"] = True

# Sort language lists for deterministic output
for entry in index.values():
    entry["languages"] = sorted(entry["languages"])

# We then create a JSON file to store the index
with open("index.json", "w") as f:
    json.dump(index, f, indent=2)

# The JSON file will not be commited to the repository because it can be builded locally using this script

print(f"Index created : {len(index)} entries")