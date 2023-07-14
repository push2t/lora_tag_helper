import argparse
import json
import pathlib
from PIL import Image
from os.path import isfile, join, splitext

from collections import OrderedDict

def do_folder(path, features_whitelist):
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


        __import__("IPython").embed()
        raise  ValueError("")



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

def index_features(features):
    r = {}
    for cat, featuretxt in features.items():
        if not featuretxt:
            continue
        features = [c.strip() for c in featuretxt.split(",")]
        for f in features:
            r[f] = cat

    return r

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
    features = load_json(args.existing_json_example)["features"]
    features_whitelist = index_features(features)

    do_folder(args.in_folder, features_whitelist)

    pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--existing_json_example",
        required=True,
        help="We read category -> feature from this, so use an existing tagged file"
    )

    parser.add_argument(
        "--in_folder",
        required=True,
        help="We walk this folder looking for .txt captions to promote into features and write to out_folder"
    )

    parser.add_argument(
        "--out_folder",
        help="write our resutls here"
    )

    args = parser.parse_args()
    main(args)