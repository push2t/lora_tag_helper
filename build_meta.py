
import argparse
import os
import json



def walk_for_json(path):
    jsons = []
    for root, dirs, files in os.walk(path):
        for file in files:
            if file.endswith(".json"):
                jsons.append(os.path.join(root,file))
    return jsons

def load_json(path):
    try:
        with open(path, "r") as fh:
            d = json.load(fh)
            return d
    except FileNotFoundError:
        return {
            "artist": "unknown",
            "features": {},
            "automatic tags": "",
        }


def merge_features(superset, newset):
    for category, featuretxt in newset.items():
        if not featuretxt:
            continue

        if category not in superset:
            superset[category] = set()

        features = [c.strip() for c in featuretxt.split(",")]
        for f in features:
            superset[category].add(f)

def collapse_superset(_superset):
    superset = {}
    for category, feasureset in _superset.items():
        superset[category] = ", ".join(_superset[category])

    return superset


def main(args):

    print("searching %s for .json files" % (args.search_folder))
    jsons = walk_for_json(args.search_folder)
    print("found %d .jsons" % (len(jsons)))
    if not len(jsons):
        raise ValueError("nyet")

    superset = {}
    for _j in jsons:
        print("loading file %s" % (_j))
        data = load_json(_j)
        if not "features" in data:
            print("invalid json file %s, skipping" % (_j))
            continue

        merge_features(superset, data["features"])
    
    superset = collapse_superset(superset)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--search_folder",
        required=True,
        help="recursivce search this folder for any .json files, expect them to contain  'features' key, then make a superfeaturelist"
    )

    parser.add_argument(
        "--out_file",
        required=True,
        help="write our resutls here"
    )

    args = parser.parse_args()

    main(args)