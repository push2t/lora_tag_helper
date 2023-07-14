import argparse
import json
import pathlib
from PIL import Image
from os import makedirs
from os.path import isfile, join, splitext, exists, split
import shutil

from collections import OrderedDict

def do_folder(path, out_path, features_whitelist):
    #Get supported extensions
    exts = Image.registered_extensions()
    supported_exts = {ex for ex, f in exts.items() if f in Image.OPEN}

    #Get list of filenames matching those extensions
    files = [pathlib.Path(f).absolute()
                for f in pathlib.Path(path).rglob("*")
                if isfile(join(path, f))]

    image_files = [
        f for f in files if splitext(f)[1] in supported_exts]  

    image_files.sort()

    makedirs(out_path, exist_ok=False)

    # for each image file
    # try to load .txt automatic caption  and .json 

    for f in image_files:
        txt_file = splitext(f)[0] + ".txt"
        json_file = splitext(f)[0] + ".json"

        try:
            raw_auto, auto_components = load_automated(txt_file)
        except FileNotFoundError as exc:
            print(exc)
            continue

        json_data = load_json(json_file)
        
        new_features, new_auto_components = promote_features(auto_components, features_whitelist)

        _features = {}
        for (feature,category) in new_features:
            if category not in _features:
                _features[category] = []
            _features[category].append(feature)

        for category, features in _features.items():
            json_data["features"][category] = ", ".join(features)

        json_data["automatic tags"] = ", ".join(new_auto_components)

        print("copying image file %s to %s" % (f, out_path))
        shutil.copy(f, out_path)


        new_txt_path = join(out_path, split(txt_file)[1])
        new_json_path = join(out_path, split(json_file)[1])

        print("writing new .txt to %s" % (new_txt_path))
        with open(new_txt_path, "w") as _f:
            _f.write(json_data["automatic tags"])


        print("writing new .json to %s" % (new_json_path))
        with open(new_json_path, "w") as _f:
            _f.write(json.dumps(json_data))



def load_json(path):
    try:
        with open(path, "r") as fh:
            d = json.load(fh)

            if "artist" not in d:
                d["artist"] = "unknown"
            if "features" not in d:
                d["features"] = {}
            if "automatic tags" not in d:
                d["automatic tags"] = ""
            return d
    except FileNotFoundError:
        return {
            "artist": "unknown",
            "features": {},
            "automatic tags": "",
        }

def index_features(features, wl=None):
    if not wl:
        wl = {}
    for cat, featuretxt in features.items():
        if not featuretxt:
            continue
        features = [c.strip() for c in featuretxt.split(",")]
        for f in features:
            wl[f] = cat

    return wl

def load_automated(path):
    with open(path, "r") as fh:
        raw_txt = fh.read()
        components = [c.strip() for c in raw_txt.split(",")]

        return (raw_txt, components)

def promote_features(auto_components, features_whitelist):

    # if an auto component is in feature whitelist
    # remove it from auto components and add it to features


    new_features = set()
    new_components = OrderedDict()
    for comp in auto_components:
        if comp in features_whitelist:
            new_features.add((comp, features_whitelist[comp]))
        else:
            new_components[comp] = None

    return (list(new_features), list(new_components.keys()))

def main(args):

    features_whitelist = {}
    for ex in args.existing_json_examples:
        features = load_json(ex)["features"]
        features_whitelist = index_features(features)

    if args.features_json_raw:
        features = json.loads(args.features_json_raw)
        features_whitelist = index_features(features)

    if not len(features_whitelist):
        raise ValueError("whitelist empty, something wrong")

    print("Feature promotion whitelist calculated:\n%s" % (features_whitelist))
    do_folder(args.in_folder, args.out_folder, features_whitelist)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--existing_json_examples",
        action="append",
        required=True,
        help="We read category -> feature from this, so use an existing tagged file"
    )

    parser.add_argument(
        "--features_json_raw",
        help='give me a json string that would go under features in a file, i.e. {"category": "feature1, feature2"} and we will include it in whitelist',
    )

    parser.add_argument(
        "--in_folder",
        required=True,
        help="We walk this folder looking for .txt captions to promote into features and write to out_folder"
    )

    parser.add_argument(
        "--out_folder",
        required=True,
        help="write our resutls here"
    )

    args = parser.parse_args()

    if exists(args.out_folder):
        raise ValueError("--out_folder '%s' exists, give me a fresh folder" % (args.out_folder))

    main(args)