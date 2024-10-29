import os
import logging
import json


IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp']
CAPTION_EXTENSIONS = ['.txt']
CROP_EXTENSIONS = ['.npz']
META_EXTENSIONS = ['.json']


def setup_logger(verbose):
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


def walk_dir_for_json(path):
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
            "artist": "build_meta.py",
            "features": {},
            "automatic tags": "",
        }


def merge_json_features(superset, newset):
    for category, featuretxt in newset.items():
        if not featuretxt:
            continue

        if category not in superset:
            superset[category] = set()

        features = [c.strip() for c in featuretxt.split(",")]
        for f in features:
            superset[category].add(f)

def collapse_json_superset(_superset):
    superset = {}
    for category, featureset in _superset.items():
        superset[category] = [f for f in featureset]

    return superset


def validate_filenames(filenames):
    image_files = [f for f in filenames if os.path.splitext(f)[1].lower() in IMAGE_EXTENSIONS]
    caption_files = [f for f in filenames if os.path.splitext(f)[1].lower() in CAPTION_EXTENSIONS]
    crop_extensions = [f for f in filenames if os.path.splitext(f)[1].lower() in CROP_EXTENSIONS]
    meta_extensions = [f for f in filenames if os.path.splitext(f)[1].lower() in META_EXTENSIONS]

    if len(image_files) != 1:
        raise ValueError(f"Expected exactly one image file, found {len(image_files)}.")
    
    if len(caption_files) != 1:
        raise ValueError(f"Expected exactly one caption file, found {len(caption_files)}.")
    
    return (
        image_files[0],
        caption_files[0],
        crop_extensions[0],
        meta_extensions[0]
    )

# this is a bit assbackwards, but the caption files have sometimes been mutated
# without that being reflected in the meta file.
# the most reliable way i can think of is finding where the 'automatic_tags' part from meta file
# starts in the caption file, then anything preceeding that is a feature tag.
def validate_caption_to_meta(caption_file, meta_file, flat_superset):
    logging.debug("validating caption file %s to metadata file %s", caption_file, meta_file)
    with open(caption_file, 'r') as f:
        caption = f.read()
    
    with open(meta_file, 'r') as f:
        meta = json.load(f)
    
    if not 'automatic_tags' in meta:
        raise ValueError("No automatic tags in metadata file, malformed af")
    
    auto_tags = [t.strip() for t in meta['automatic_tags'].split(",")]
    caption_tags = [t.strip() for t in caption.split(",")]

    for tag in caption_tags:
        if tag in flat_superset:
            logging.debug("tag in superset", tag)
        if tag in auto_tags:
            logging.debug("tag in auto tags", tag)
        if tag not in flat_superset and tag not in auto_tags:
            logging.debug("wtf is tag doing here", tag)

def flatten_superset(superset):
    _fs = set()
    for _f in superset.values():
        for f in _f:
            _fs.add(f)
    return _fs