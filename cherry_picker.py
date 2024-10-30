import argparse
import os
import shutil
import sys
import logging
import json
import zlib
import re

import zzutils

def mutated_filename(filename):
    base, ext = os.path.splitext(filename)
    return f"{base}_cherry_picker{ext}"

def find_and_copy_file(input_dir, output_dir, filename, superset, flat_superset):
    matched = 0
    for root, _, files in os.walk(input_dir):
        base_name, _ = os.path.splitext(filename)
        #matched_files = [f for f in files if f.startswith(base_name)]
        matched_files = [f for f in files if re.match(rf'^{re.escape(base_name)}\.[^.]+$', f)]

        if not matched_files:
            continue

        (img_fn, cap_fn, crop_fn, meta_fn) = zzutils.validate_filenames(matched_files)
        zzutils.validate_caption_to_meta(os.path.join(root, cap_fn), os.path.join(root, meta_fn), flat_superset)

        for file in matched_files:
            src_path = os.path.join(root, file)
            relative_path = os.path.relpath(root, input_dir)
            dest_dir = os.path.join(output_dir, relative_path)
            os.makedirs(dest_dir, exist_ok=True)
            dest_path = os.path.join(dest_dir, mutated_filename(file))

            if not os.path.exists(dest_path):
                shutil.copy2(src_path, dest_path)
                logging.info(f"Copied {src_path} to {dest_path}")
            else:
                logging.error(f"File {dest_path} already exists. Skipping.")
            matched += 1

    if matched == 0:
        logging.error(f"File {filename} not found in {root}.")

def load_superset(input_dataset, output_dataset, use_cache=True):

    superset = {}

    def _merge(s1, s2):
        for c, f in s2.items():
            if not c in s1:
                s1[c] = []
            for _f in f:
                if _f not in s1[c]:
                    s1[c].append(_f)
        return s1

    if use_cache:
        # load all cached supersets
        superset_files = [os.path.join(output_dataset, f) for f in os.listdir(output_dataset) if re.match(r'\.(.*)_superset_cache\.json', f)]
        for cache_file in superset_files:
            with open(cache_file, "r") as f:
                _superset = json.load(f)
            logging.info("Loaded superset from cache %s", cache_file)
            superset = _merge(superset, _superset)
        
    if len(superset.keys()) == 0:
        logging.info(f"Searching {input_dataset} for .json files")
        jsons = zzutils.walk_dir_for_json(input_dataset)
        logging.info(f"Found {len(jsons)} .jsons")

        superset = {}
        for _j in jsons:
            logging.debug("loading file %s" % (_j))
            data = zzutils.load_json(_j)
            if not "features" in data:
                logging.error("invalid json file %s, skipping" % (_j))
                continue

            zzutils.merge_json_features(superset, data["features"])
        
        superset = zzutils.collapse_json_superset(superset)
        
        input_dataset_hash = zlib.crc32(input_dataset.encode())
        cache_file = os.path.join(output_dataset, ".%s_superset_cache.json" % (input_dataset_hash))

        with open(cache_file, "w") as f:
            json.dump(superset, f)
        logging.info("Saved superset to cache %s", cache_file)

    return superset



def main():
    parser = argparse.ArgumentParser(description="Copy files with matching filenames but different extensions.")
    parser.add_argument('--input_dataset', required=True, type=str, help="Input directory containing the files.")
    parser.add_argument('--output_dataset', required=True, type=str, help="Output directory to copy the files to.")
    parser.add_argument('--filename', type=str, help="Text file with one filename per line.")
    parser.add_argument('--verbose', action='store_true', help="Increase output verbosity.")
    parser.add_argument('--skip_caches', action='store_true', help="Skip loading the superset cache from disk.")
    
    args = parser.parse_args()
    zzutils.setup_logger(args.verbose)

    superset = load_superset(
        input_dataset=args.input_dataset,
        output_dataset=args.output_dataset,
        use_cache=not args.skip_caches,
    )
    flat_superset = zzutils.flatten_superset(superset)
    #supersets_to_metafile(args.output_dataset)

    for filename in get_filenames(args.filename):
        logging.info(f"Processing {filename}")
        find_and_copy_file(args.input_dataset, args.output_dataset, filename, superset, flat_superset)
    logging.debug("Done!")

def get_filenames(filename=None):
    def _path_to_filename(path):
        base_name = os.path.basename(path)
        file_name, _ = os.path.splitext(base_name)
        return file_name
    
    if filename:
        with open(filename, 'r') as file:
            for line in file:
                yield _path_to_filename(line.strip())
    else:
        for line in sys.stdin:
            yield _path_to_filename(line.strip()) 



if __name__ == "__main__":
    main()

