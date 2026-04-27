import os
import json

"""This script builds an index of all the revision IDs present in the WSUS directory,
along with the corresponding package and whether the x and l files exist for each 
revision ID to permit a more efficient parsing in the future, as we will be able to 
directly access the relevant files."""


# Modify this path to point to your local WSUS directory
WSUS_DIR = os.environ["WSUS_DIR"]

index = {}

# We iterate through all the packages in the WSUS directory, and for each package we check if the x and l files exist
for package in os.listdir(WSUS_DIR):
    package_path = os.path.join(WSUS_DIR, package)
    if not os.path.isdir(package_path):
        continue
    
    x_path = os.path.join(package_path, "x")
    l_path = os.path.join(package_path, "l", "en")
    e_path = os.path.join(package_path, "e", "en")
    
    # We get the revision IDs from the x and l files names to build the index
    if os.path.exists(x_path):
        for filename in os.listdir(x_path):
            revision_id = filename
            if revision_id not in index:
                index[revision_id] = {"package": package, "has_x": False, "has_l": False, "has_e": False}
            index[revision_id]["has_x"] = True
    
    if os.path.exists(l_path):
        for filename in os.listdir(l_path):
            revision_id = filename
            if revision_id not in index:
                index[revision_id] = {"package": package, "has_x": False, "has_l": False, "has_e": False}
            index[revision_id]["has_l"] = True

    if os.path.exists(e_path):
        for filename in os.listdir(e_path):
            revision_id = filename
            if revision_id not in index:
                index[revision_id] = {"package": package, "has_x": False, "has_l": False, "has_e": False}
            index[revision_id]["has_e"] = True

# We then create a JSON file to store the index
with open("index.json", "w") as f:
    json.dump(index, f, indent=2)

# The JSON file will not be commited to the repository because it can be builded locally using this script

print(f"Index créé : {len(index)} entrées")