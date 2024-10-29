import argparse
import os
import shutil
import time
import sys
import logging
import json
import zlib
import re

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
    for category, feasureset in _superset.items():
        superset[category] = ", ".join(_superset[category])

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

def mutated_filename(filename):
    base, ext = os.path.splitext(filename)
    return f"{base}_cherry_picker{ext}"

def find_and_copy_file(input_dir, output_dir, filename):
    matched = 0
    for root, _, files in os.walk(input_dir):
        base_name, _ = os.path.splitext(filename)
        matched_files = [f for f in files if f.startswith(base_name)]

        if not matched_files:
            continue

        (img_fn, cap_fn, crop_fn, meta_fn) = validate_filenames(matched_files)

        for file in matched_files:
            src_path = os.path.join(root, file)
            relative_path = os.path.relpath(root, input_dir)
            dest_dir = os.path.join(output_dir, relative_path)
            os.makedirs(dest_dir, exist_ok=True)
            dest_path = os.path.join(dest_dir, mutated_filename(file))

            if not os.path.exists(dest_path):
                #shutil.copy2(src_path, dest_path)
                logging.info(f"Copied {src_path} to {dest_path}")
            else:
                logging.error(f"File {dest_path} already exists. Skipping.")
            matched += 1

    if matched == 0:
        logging.error(f"File {filename} not found in {root}.")

def load_superset(input_dataset, output_dataset, use_cache=True):
    input_dataset_hash = zlib.crc32(input_dataset.encode())
    cache_file = os.path.join(output_dataset, ".%s_superset_cache.json" % (input_dataset_hash))

    superset = None
    if use_cache and os.path.exists(cache_file):
        cache_mtime = os.path.getmtime(cache_file)
        if (time.time() - cache_mtime) < 3600:
            with open(cache_file, "r") as f:
                superset = json.load(f)
            logging.info("Loaded superset from cache %s", cache_file)
    
    if not superset:
        logging.info(f"Searching {input_dataset} for .json files")
        jsons = walk_dir_for_json(input_dataset)
        logging.info(f"Found {len(jsons)} .jsons")

        superset = {}
        for _j in jsons:
            logging.debug("loading file %s" % (_j))
            data = load_json(_j)
            if not "features" in data:
                logging.error("invalid json file %s, skipping" % (_j))
                continue

            merge_json_features(superset, data["features"])
        
        superset = collapse_json_superset(superset)
        
        with open(cache_file, "w") as f:
            json.dump(superset, f)
        logging.info("Saved superset to cache %s", cache_file)
    
def supersets_to_metafile(output_dataset):
    superset_files = [f for f in os.listdir(output_dataset) if re.match(r'\.(.*)_superset_cache\.json', f)]
    all_supersets = {}

    for superset_file in superset_files:
        superset_path = os.path.join(output_dataset, superset_file)
        with open(superset_path, 'r') as f:
            superset = json.load(f)
            all_supersets[superset_file] = superset

    __import__("IPython").embed()
    return all_supersets

def main():
    parser = argparse.ArgumentParser(description="Copy files with matching filenames but different extensions.")
    parser.add_argument('--input_dataset', required=True, type=str, help="Input directory containing the files.")
    parser.add_argument('--output_dataset', required=True, type=str, help="Output directory to copy the files to.")
    parser.add_argument('--filename', type=str, help="Text file with one filename per line.")
    parser.add_argument('--verbose', action='store_true', help="Increase output verbosity.")
    parser.add_argument('--skip_caches', action='store_true', help="Skip loading the superset cache from disk.")
    
    args = parser.parse_args()
    setup_logger(args.verbose)

    load_superset(args.input_dataset, args.output_dataset, not args.skip_caches)
    supersets_to_metafile(args.output_dataset)
    raise ValueError("ah")

    for filename in get_filenames(args.filename):
        logging.debug(f"Processing {filename}")
        find_and_copy_file(args.input_dataset, args.output_dataset, filename)
    logging.debug("Done!")

def get_filenames(filename=None):
    if filename:
        with open(filename, 'r') as file:
            for line in file:
                yield line.strip()
    else:
        for line in sys.stdin:
            yield line.strip() 

if __name__ == "__main__":
    main()

