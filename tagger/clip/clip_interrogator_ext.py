import csv
import open_clip
import os
import torch

from PIL import Image

import clip_interrogator
from clip_interrogator import Config, Interrogator

#import devices

__version__ = '0.1.4'

ci = None
low_vram = False
cpu = torch.device("cpu")

BATCH_OUTPUT_MODES = [
    'Text file for each image',
    'Single text file with all prompts',
    'csv file with columns for filenames and prompts',
]

class BatchWriter:
    def __init__(self, folder, mode):
        self.folder = folder
        self.mode = mode
        self.csv, self.file = None, None
        if mode == BATCH_OUTPUT_MODES[1]:
            self.file = open(os.path.join(folder, 'batch.txt'), 'w', encoding='utf-8')
        elif mode == BATCH_OUTPUT_MODES[2]:
            self.file = open(os.path.join(folder, 'batch.csv'), 'w', encoding='utf-8', newline='')
            self.csv = csv.writer(self.file, quoting=csv.QUOTE_MINIMAL)
            self.csv.writerow(['filename', 'prompt'])

    def add(self, file, prompt):
        if self.mode == BATCH_OUTPUT_MODES[0]:
            txt_file = os.path.splitext(file)[0] + ".txt"
            with open(os.path.join(self.folder, txt_file), 'w', encoding='utf-8') as f:
                f.write(prompt)
        elif self.mode == BATCH_OUTPUT_MODES[1]:
            self.file.write(f"{prompt}\n")
        elif self.mode == BATCH_OUTPUT_MODES[2]:
            self.csv.writerow([file, prompt])

    def close(self):
        if self.file is not None:
            self.file.close()


def load(clip_model_name,blip_model_name):
    global ci
    if ci is None:
        print(f"Loading CLIP Interrogator {clip_interrogator.__version__}...")

        config = Config(
            device=get_optimal_device(), 
            cache_path = 'models/clip-interrogator',
            clip_model_name=clip_model_name,
            blip_model_type=blip_model_name
        )
        if low_vram:
            config.apply_low_vram_defaults()
        ci = Interrogator(config)

    if clip_model_name != ci.config.clip_model_name:
        ci.config.clip_model_name = clip_model_name
        ci.load_clip_model()

def unload():
    global ci
    if ci is not None:
        print("Offloading CLIP Interrogator...")
        ci.blip_model = ci.blip_model.to(cpu)
        ci.clip_model = ci.clip_model.to(cpu)
        ci.blip_offloaded = True
        ci.clip_offloaded = True
        torch_gc()

def image_analysis(image, clip_model_name,blip_model_name):
    load(clip_model_name,blip_model_name)

    image = image.convert('RGB')
    image_features = ci.image_to_features(image)

    top_mediums = ci.mediums.rank(image_features, 5)
    top_artists = ci.artists.rank(image_features, 5)
    top_movements = ci.movements.rank(image_features, 5)
    top_trendings = ci.trendings.rank(image_features, 5)
    top_flavors = ci.flavors.rank(image_features, 5)

    medium_ranks = {medium: sim for medium, sim in zip(top_mediums, ci.similarities(image_features, top_mediums))}
    artist_ranks = {artist: sim for artist, sim in zip(top_artists, ci.similarities(image_features, top_artists))}
    movement_ranks = {movement: sim for movement, sim in zip(top_movements, ci.similarities(image_features, top_movements))}
    trending_ranks = {trending: sim for trending, sim in zip(top_trendings, ci.similarities(image_features, top_trendings))}
    flavor_ranks = {flavor: sim for flavor, sim in zip(top_flavors, ci.similarities(image_features, top_flavors))}
    
    return medium_ranks, artist_ranks, movement_ranks, trending_ranks, flavor_ranks

def interrogate(image, mode, caption=None):
    if mode == 'best':
        prompt = ci.interrogate(image, caption=caption)
    elif mode == 'caption':
        prompt = ci.generate_caption(image) if caption is None else caption
    elif mode == 'classic':
        prompt = ci.interrogate_classic(image, caption=caption)
    elif mode == 'fast':
        prompt = ci.interrogate_fast(image, caption=caption)
    elif mode == 'negative':
        prompt = ci.interrogate_negative(image)
    else:
        raise Exception(f"Unknown mode {mode}")
    return prompt

def image_to_prompt(image, mode, clip_model_name):

    try: 
        # if shared.cmd_opts.lowvram or shared.cmd_opts.medvram:
        #     lowvram.send_everything_to_cpu()
        #     devices.torch_gc()

        load(clip_model_name)
        image = image.convert('RGB')
        prompt = interrogate(image, mode)
    except RuntimeError as e:
        prompt = f"Exception {type(e)}"
        print(e)

    return prompt

def get_models():
    return ['/'.join(x) for x in open_clip.list_pretrained()]

def torch_gc():
    if torch.cuda.is_available():
        with torch.cuda.device(get_cuda_device_string()):
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()

def get_cuda_device_string():

    return "cuda"
def get_optimal_device_name():
    if torch.cuda.is_available():
        return get_cuda_device_string()

    return "cpu"


def get_optimal_device():
    return torch.device(get_optimal_device_name())

