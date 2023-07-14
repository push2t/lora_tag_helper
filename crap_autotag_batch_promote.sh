#!/bin/bash

. ./linux_venv/bin/activate
#pip install -r requirements_promoter.txt

find $1 -mindepth 1 -type d -exec python ./crap_autotag_promoter.py --existing_json_example=/mnt/i/stable_diffusion/lora/promotion_superset.json --in_folder={} --out_folder={}_2 \;