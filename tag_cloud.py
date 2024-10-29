import argparse
import zzutils
import logging



def count_merge_json_features(superset, newset):
    for category, featuretxt in newset.items():
        if not featuretxt:
            continue

        if category not in superset:
            superset[category] = {}

        features = [c.strip() for c in featuretxt.split(",")]
        for f in features:
            if f in superset[category]:
                superset[category][f] += 1
            else:
                superset[category][f] = 1

    # flatten categories into features with a . separator
    flat_superset = {}
    for category, features in superset.items():
        for f, c in features.items():
            flat_f = f"{category}.{f}"
            if flat_f in flat_superset:
                flat_superset[flat_f] += c
            else:
                flat_superset[flat_f] = c

    return flat_superset

def print_sorted_features(flat_superset):
    sorted_features = sorted(flat_superset.items())
    
    print(f"{'Feature':<30}{'Count':<10}")
    print("-" * 40)
    
    for feature, count in sorted_features:
        print(f"{feature:<30}{count:<10}")

def main():
    parser = argparse.ArgumentParser(description='Process some directories.')
    parser.add_argument('--input_dataset', required=True, type=str, help='The input dataset directory')
    parser.add_argument('--verbose', action='store_true', help="Increase output verbosity.")

    args = parser.parse_args()
    zzutils.setup_logger(args.verbose)
    
    jsons = zzutils.walk_dir_for_json(args.input_dataset)

    logging.info(f"Found {len(jsons)} .jsons")

    superset = {}
    for _j in jsons:
        logging.debug("loading file %s" % (_j))
        data = zzutils.load_json(_j)
        if not "features" in data:
            logging.error("invalid json file %s, skipping" % (_j))
            continue

        flat_superset = count_merge_json_features(superset, data["features"])

    print_sorted_features(flat_superset)

if __name__ == "__main__":
    main()