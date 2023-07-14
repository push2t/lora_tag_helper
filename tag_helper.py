from os import listdir, makedirs, walk, getcwd, utime, remove, sep, scandir
from os.path import isfile, join, splitext, exists, getmtime, relpath, dirname, basename
import time
import threading
import shutil
import pathlib
import re
import traceback
from PIL import ImageTk, Image
import json
import jsonpickle
from events import Events
from tkinterdnd2 import DND_FILES, TkinterDnD
from tkinter.messagebox import askyesno, showinfo, showwarning, showerror
from tkinter import simpledialog, scrolledtext
import tkinter.filedialog
import tkinter.ttk
import tkinter.font
import tkinter as tk
from tkinter import ttk
import pynput
from pprint import pprint, pformat
from functools import partial
import re

import spacy

import tagger

from clip_interrogator import Config, Interrogator
import tagger.clip.clip_interrogator_ext as ci_ext
import logo_removal.Logo_Removal_Tool as Logo_Removal

treeview_separator = "\u2192"

BALLOT_BOX = "\u2610"
BALLOT_BOX_WITH_X = "\u2612"

appdata_path = "./appdata/"
ui_theme = "default"

#TODO:
#Eventually: Batch rename/delete feature...Alt click on feature?
#Eventually: generate output dataset optionally without .jsons, organized in various ways
#Eventually: use PNG info as alternative (read-only) source of data, and allow writing it during LoRA subset generation
#Eventually: search for images with feature (i.e. active filter in main window?)

class TtkCheckList(ttk.Treeview):
    def __init__(self, master=None, width=200, clicked=None, separator='.',
                 unchecked=BALLOT_BOX, checked=BALLOT_BOX_WITH_X, **kwargs):
        """
        :param width: the width of the check list
        :param clicked: the optional function if a checkbox is clicked. Takes a
                        `iid` parameter.
        :param separator: the item separator (default is `'.'`)
        :param unchecked: the character for an unchecked box (default is
                          "\u2610")
        :param unchecked: the character for a checked box (default is "\u2612")

        Other parameters are passed to the `TreeView`.
        """
        if "selectmode" not in kwargs:
            kwargs["selectmode"] = "none"
        if "show" not in kwargs:
            kwargs["show"] = "tree"
        ttk.Treeview.__init__(self, master, **kwargs)
        
        self._separator = separator
        self._unchecked = unchecked
        self._checked = checked
        self._clicked = self.toggle if clicked is None else clicked
        self.parent_frame = master
        self.column('#0', width=width, stretch=tk.YES)
        self.bind("<Button-1>", self._item_click, True)
        self.bind('<<TreeviewOpen>>', self.handle_open_event)
        self.bind('<<TreeviewClose>>', self.handle_close_event)

    def _item_click(self, event):
        assert event.widget == self
        x, y = event.x, event.y
        element = self.identify("element", x, y)
        if element == "text":
            iid = self.identify_row(y)
            self._clicked(iid)
            return "break"

    def add_item(self, item):
        """
        Add an item to the checklist. The item is the list of nodes separated
        by dots: `Item.SubItem.SubSubItem`. **This item is used as `iid`  at
        the underlying `Treeview` level.**
        """
        try:
            parent_iid, text = item.rsplit(self._separator, maxsplit=1)
        except ValueError:
            parent_iid, text = "", item

        def in_tree(item, root = ''):
            children = self.get_children(root)
            if item in children:
                return True
            for child in children:
                if in_tree(item, child):
                    return True
            return False

        if(not in_tree(item)):
            
            new_item = self.insert(parent_iid, index='end', iid=item,
                        text=self._unchecked+" "+text, open=True)
            if new_item in self.parent_frame.master.master.master.treeview_unfold_state:
                self.item(new_item, open= self.parent_frame.master.master.master.treeview_unfold_state[new_item])
            
    def handle_open_event(self,event):
        
        item = self.focus()
        self.parent_frame.master.master.master.treeview_unfold_state[item] = True
        if(self.parent_frame.master.master.master.alt_pressed):
            self.fold_all_items(True)
        print("open pre" + str(item))

    def handle_close_event(self,event):
        
        item = self.focus()
        self.parent_frame.master.master.master.treeview_unfold_state[item] = False
        if(self.parent_frame.master.master.master.alt_pressed):
            self.fold_all_items(False)
        print("open pre" + str(item))

    def fold_all_items(self, fold):
        for item in self.get_children():
            child_count = 0
            for child in self.get_children(item):
                grandchild_count = 0
                if(child_count == 0):
                    self.item(item, open= fold)
                    self.parent_frame.master.master.master.treeview_unfold_state[item] = False
                child_count += 1
                for grandchild in self.get_children(child):
                    if(grandchild_count == 0):
                        self.item(child, open= fold)
                        self.parent_frame.master.master.master.treeview_unfold_state[child] = False
                    grandchild_count += 1      
        
    def autofit(self):
        minwidth = 200
        font = tk.font.nametofont("TkTextFont")
        for item in self.get_children():
            minwidth = max(minwidth, min(400, 40 + font.measure(self.item(item, "text"))))
            for child in self.get_children(item):
                minwidth = max(minwidth, min(400, 60 + font.measure(self.item(child, "text"))))
                for grandchild in self.get_children(child):
                    minwidth = max(minwidth, min(400, 80 + font.measure(self.item(grandchild, "text"))))

        self.parent_frame.columnconfigure(0, minsize=minwidth)

    def toggle(self, iid):
        """
        Toggle the checkbox `iid`
        """
        text = self.item(iid, "text")
        if text[0] == self._checked:
            self.uncheck(iid)
        else:
            self.check(iid)

    def get_component_state(self,iid):
        toggle = 0
        text = self.item(iid, "text")
        if text[0] == self._checked:
            toggle = 0
        else:
            toggle = 1
        return toggle

    def checked(self, iid):
        """
        Return True if checkbox `iid` is checked
        """
        text = self.item(iid, "text")
        return text[0] == self._checked

    def check(self, iid):
        """
        Check the checkbox `iid`
        """
        text = self.item(iid, "text")
        if text[0] == self._unchecked:
            self.item(iid, text=self._checked+text[1:])

        #If an item is checked, all its ancestors should be as well.        
        parent_iid = self.parent(iid)
        if parent_iid:
            self.check(parent_iid)

    def uncheck(self, iid):
        """
        Uncheck the checkbox `iid`
        """
        text = self.item(iid, "text")
        if text[0] == self._checked:
            self.item(iid, text=self._unchecked+text[1:])
        
        #If an item is unchecked, all its descendants should be as well.        
        children = self.get_children(iid)
        for c in children:
            self.uncheck(c)


def get_automatic_tags_from_txt_file(image_file):
    #If .txt available, read into automated caption
    txt_file = splitext(image_file)[0] + ".txt"
    try:
        with open(txt_file) as f:
            return ' '.join(f.read().split())
    except FileNotFoundError:
        pass
    return None

use_clip = True
tokenizer_ready = False
def import_tokenizer_reqs():
    global tokenizer_ready
    try:
        try:
            global torch, open_clip, Image, model, preprocess, tokenizer, use_clip
            print("Importing Tokenizer...")
            import torch
            import open_clip
            from PIL import Image

            model, _, preprocess = open_clip.create_model_and_transforms('ViT-L-14', pretrained='laion400m_e32')
            tokenizer = open_clip.get_tokenizer('ViT-L-14')

            use_clip = True
            print("Done!")

        except:
            print("Done!")
            print(traceback.format_exc())
            print("Couldn't load torch or clip, falling back to tiktoken. Token count will be less accurate.")
            import tiktoken
    except:
        print(traceback.format_exc())
    tokenizer_ready = True

nlp = None
def do_get_pos(string):
    global nlp
    if not nlp:
        print("Loading natural language processing model...")
        nlp = spacy.load("en_core_web_sm")        
    return nlp(string)

#Return approximate number of tokens in string (seems to err on the high side)
def num_tokens_from_string(string: str, encoding_name: str= None) -> int:
    """Returns the number of tokens in a text string."""
    if use_clip:
        def raw_get_tokens(strings):
            token_list = [list(x) for x in list(tokenizer(strings))]
            for tl in token_list:
                while tl[-1] == 0:
                    tl.pop()
            return token_list

        #The tokenizer saturates at 77 tokens. Therefore, split the string
        #until each returned value is less than 77 tokens to get a valid answer.
        chunks = [string]
        token_chunks = raw_get_tokens(chunks)
        found_77 = len(token_chunks[0]) == 77

        while found_77:
            new_chunks = []
            for s in chunks:
                split_s = s.split()
                joiner = " "
                if len(split_s) == 1:
                    split_s = s
                    joiner = ""
                left_s = joiner.join(split_s[:int(len(split_s) / 2)])
                right_s =joiner.join(split_s[int(len(split_s) / 2):])
                new_chunks.append(left_s)
                new_chunks.append(right_s)
            chunks = new_chunks

            new_token_chunks = raw_get_tokens(chunks)
            token_chunks = new_token_chunks
            found_77 = False
            for t in token_chunks:
                if len(t) == 77:
                    found_77 = True

        sum_tokens = 0
        for t in token_chunks:
            sum_tokens += len(t) - 2 #Each chunk has a start/end token.

        return sum_tokens
    else:
        encoding = tiktoken.get_encoding(encoding_name)
        num_tokens = len(encoding.encode(string))
        return num_tokens


def import_interrogators():
    try:
        try:
            global tagger, utils, interrogator, use_interrogate, interrogator_ready
            print("Importing automatic caption interrogators...")
            import tagger
            from tagger import utils
            from tagger import interrogator
            tagger.utils.refresh_interrogators()
            print("Done!")

        except:
            print(traceback.format_exc())
            print("Couldn't load clip interrogator. Won't interrogate images for automatic tags, only TXT.")
            use_interrogate = False
    except:
        print(traceback.format_exc())
    interrogator_ready = True
    
def do_interrogate(
        image: Image,

        interrogator: str,
        threshold: float,
        additional_tags: str,
        exclude_tags: str,
        sort_by_alphabetical_order: bool,
        add_confident_as_weight: bool,
        replace_underscore: bool,
        replace_underscore_excludes: str):
    
    if interrogator not in tagger.utils.interrogators:
        return ['', None, None, f"'{interrogator}' is not a valid interrogator"]

    interrogator: tagger.Interrogator = tagger.utils.interrogators[interrogator]

    postprocess_opts = (
        threshold,
        tagger.utils.split_str(additional_tags),
        tagger.utils.split_str(exclude_tags),
        sort_by_alphabetical_order,
        add_confident_as_weight,
        replace_underscore,
        tagger.utils.split_str(replace_underscore_excludes)
    )

    # single process
    if image is not None:
        ratings, tags = interrogator.interrogate(image)
        processed_tags = tagger.Interrogator.postprocess_tags(
            tags,
            *postprocess_opts
        )

        return [
            ', '.join(processed_tags),
            ratings,
            tags,
            ''
        ]
    return ['', None, None, '']
    
use_interrogate = True
interrogator_ready = False
def interrogate_automatic_tags(image_file,settings):
    use_ci = False
    print("model pick " + str(settings.interrogator_options_pick)) 
    if(use_interrogate):
        image = Image.open(image_file).convert('RGB')
        if settings.interrogator_options_pick == 0:
            print("wd14") 
            try:
                wd14_settings = settings.wd14_settings
                caption = do_interrogate(image, wd14_settings.model_wd14_pick, wd14_settings.general_threshold, "", "", False, False, True, "0_0, (o)_(o), +_+, +_-, ._., <o>_<o>, <|>_<|>, =_=, >_<, 3_3, 6_9, >_o, @_@, ^_^, o_o, u_u, x_x, |_|, ||_||")[0]
                return caption
            except:
                print(traceback.format_exc())            
                return get_automatic_tags_from_txt_file(image_file)
        elif settings.interrogator_options_pick == 1:
            print("clip") 
            try:
                clip_settings = settings.clip_settings
                # analysis = ci_ext.image_analysis(image,clip_settings.model_clip_pick,"base")
                # for rank in analysis:
                #     print(str(rank))
                ci_ext.load(clip_settings.model_clip_pick,"base")
                #ci = Interrogator(Config(clip_model_name=clip_settings.model_clip_pick, blip_model_type= clip_settings.model_blip_pick))
                caption = ci_ext.interrogate(image,clip_settings.mode)
                return caption
            except:
                print(traceback.format_exc())            
                return get_automatic_tags_from_txt_file(image_file)
    else:
       return get_automatic_tags_from_txt_file(image_file)
    

def truncate_string_to_max_tokens(string : str, max_tokens):
    while num_tokens_from_string(string.strip(), "gpt2") > max_tokens:
        string = " ".join(string.split()[:-1])

    while string.endswith(","):
        string = string[:-1]
    return string


class save_defaults_popup(object):
    def __init__(self, parent):
        self.parent = parent

        self.create_ui()

    def create_ui(self):
        self.top = tk.Toplevel(self.parent)
        self.top.title("Save defaults for path in dataset...")
        self.top.wait_visibility()
        self.top.grab_set()
        self.top.rowconfigure(0, weight=1)
        self.top.columnconfigure(0, weight=1)
        self.top.minsize(600, 400)
        self.top.transient(self.parent)

        self.form_frame = tk.Frame(self.top, 
                                   borderwidth=2,
                                   relief='raised',)
        
        self.form_frame.columnconfigure(1, weight=1)
        self.form_frame.rowconfigure(5, weight=1)

        #Defaults output location
        output_path_label = tk.Label(self.form_frame, text="Path: ")
        output_path_label.grid(row=0, column=0, padx=(5, 0), pady=5, sticky="e")

        self.output_path = tk.StringVar(None)
        self.output_path.set(relpath(pathlib.Path(self.parent.image_files[self.parent.file_index]).parent, self.parent.path))
        set_output_path_entry = tk.Entry(self.form_frame,
                                     textvariable=self.output_path, 
                                     justify="left")
        set_output_path_entry.grid(row=0, column=1, 
                               padx=(0, 5), pady=5, 
                               sticky="ew")
        set_output_path_entry.bind('<Control-a>', self.select_all)

        #Browse button
        browse_btn = tk.Button(self.form_frame, text='Browse...', 
                               command=self.browse)
        browse_btn.grid(row=0, column=2, padx=4, pady=4, sticky="sew")
        self.top.bind("<Control-b>", self.browse)


        #Labeled group for options
        settings_group = tk.LabelFrame(self.form_frame, 
                                    text="Copy & Paste Settings")
        settings_group.grid(row=2, column=0, 
                            columnspan=3, 
                            padx=5, pady=5,
                            sticky="nsew")

        settings_group.columnconfigure(1, weight=1)
        defaults = self.parent.get_defaults()
        #Checkbox for inclusion of artist
        self.set_artist = tk.BooleanVar(None)
        self.set_artist.set(self.parent.artist_name.get() != defaults["artist"])
        set_artist_chk = tk.Checkbutton(
            settings_group,
            var=self.set_artist,
            text=f"Set artist:")
        set_artist_chk.grid(row=0, column=0, padx=5, pady=5, sticky="w")

        self.artist = tk.StringVar(None)
        self.artist.set(self.parent.artist_name.get())
        
        set_artist_entry = tk.Entry(settings_group,
                                    textvariable=self.artist, 
                                    justify="left")
        set_artist_entry.grid(row=0, column=1, 
                               padx=(0, 5), pady=5, 
                               sticky="ew")
        set_artist_entry.bind('<Control-a>', self.select_all)
        self.artist.trace("w", lambda name, index, mode: 
                                self.set_artist.set(True))


        #Checkbox for inclusion of style
        self.set_style = tk.BooleanVar(None)
        self.set_style.set(self.parent.style.get() != defaults["style"])
        set_style_chk = tk.Checkbutton(
            settings_group,
            var=self.set_style,
            text=f"Set style:")
        set_style_chk.grid(row=1, column=0, padx=5, pady=5, sticky="w")

        self.style = tk.StringVar(None)
        self.style.set(self.parent.style.get())
        
        set_style_entry = tk.Entry(settings_group,
                                    textvariable=self.style, 
                                    justify="left")
        self.style.trace("w", lambda name, index, mode: 
                                self.set_style.set(True))
        set_style_entry.grid(row=1, column=1, 
                               padx=(0, 5), pady=5, 
                               sticky="ew")
        set_style_entry.bind('<Control-a>', self.select_all)

        #Checkbox for inclusion of features
        self.set_features = tk.BooleanVar(None)
        self.set_features.set(False)
        set_features_chk = tk.Checkbutton(
            settings_group,
            var=self.set_features,
            text=f"Set features:")
        set_features_chk.grid(row=2, column=0, padx=5, pady=5, sticky="w")

        self.features = tk.StringVar(None)
        self.features.set(json.dumps({f[0]["var"].get(): "" for f in self.parent.features if f[0]["var"].get()}))
        
        set_features_entry = tk.Entry(settings_group,
                                    textvariable=self.features, 
                                    justify="left")
        set_features_entry.grid(row=2, column=1, 
                               padx=(0, 5), pady=5, 
                               sticky="ew")
        self.features.trace("w", lambda name, index, mode: 
                                self.set_features.set(True))
        set_features_entry.bind('<Control-a>', self.select_all)

        self.include_feature_descriptions = tk.BooleanVar(None)
        self.include_feature_descriptions.set(False)
        self.include_feature_descriptions.trace("w", lambda name, index, mode: 
                                self.toggle_feature_descs())
        include_feature_descriptions_chk = tk.Checkbutton(
            settings_group,
            var=self.include_feature_descriptions,
            text=f"Include feature descriptions")
        include_feature_descriptions_chk.grid(row=3, column=1, padx=5, pady=5, sticky="w")


        #Labeled group for rating
        self.set_rating = tk.BooleanVar(None)
        self.set_rating.set(False)
        set_rating_chk = tk.Checkbutton(
            settings_group,
            var=self.set_rating,
            text=f"Set quality:")
        set_rating_chk.grid(row=4, column=0, padx=5, pady=5, sticky="w")

        rating_group = tk.LabelFrame(settings_group, 
                                    text="Quality for Training")
        rating_group.grid(row=4, column=1, 
                          padx=5, pady=5,
                          sticky="nsew")

        self.rating = tk.IntVar()
        self.rating.set(False)
        tk.Radiobutton(rating_group, 
           text=f"Not rated",
           variable=self.rating, 
           value=0).grid(row=0, column=0, padx=5, pady=5, sticky="w")

        for i in range(1, 6):
            tk.Radiobutton(rating_group, 
               text=f"{i}",
               variable=self.rating, 
               value=i).grid(row=0, column=i, sticky="w")

        self.rating.trace("w", lambda name, index, mode: 
                                self.set_rating.set(True))

        # Cancel button
        cancel_btn = tk.Button(self.form_frame, text='Cancel', 
                               command=self.cancel)
        cancel_btn.grid(row=6, column=0, padx=4, pady=4, sticky="sew")
        self.top.bind("<Escape>", self.cancel)
        self.top.bind("<Control-s>", self.save)

        # Save button
        save_btn = tk.Button(self.form_frame, text='Save (Ctrl+S)', 
                               command=self.save)
        save_btn.grid(row=6, column=1,
                          columnspan=2,
                          padx=4, pady=4, 
                          sticky="sew")

        self.form_frame.grid(row=0, column=0, 
                        padx=0, pady=0, 
                        sticky="nsew")


    def toggle_feature_descs(self):
        if self.include_feature_descriptions.get():
            self.features.set(json.dumps({f[0]["var"].get(): f[1]["var"].get() for f in self.parent.features if f[0]["var"].get()}))
        else:
            self.features.set(json.dumps({f[0]["var"].get(): "" for f in self.parent.features if f[0]["var"].get()}))

    def select_all(self, event):
        # select text
        try:
            event.widget.select_range(0, 'end')
        except:
            print(traceback.format_exc())
            event.widget.tag_add("sel", "1.0", "end")

        # move cursor to the end
        try:
            event.widget.icursor('end')
        except:
            print(traceback.format_exc())
            event.widget.mark_set("insert", "end")

        #stop propagation
        return 'break'

    def get_defaults_from_ui(self):
        defaults = {}
        if self.set_artist.get():
            defaults["artist"] = self.artist.get()
        if self.set_style.get():
            defaults["style"] = self.style.get()
        if self.set_features.get():
            try:
                defaults["features"] = json.loads(self.features.get())
            except:
                print(traceback.format_exc())
                showerror(parent=self.top, title="Error", message="Features must be valid json dict.")
                return
        if self.set_rating.get():
            defaults["rating"] = self.rating.get()
        return defaults           

    def save(self, event = None):
        dataset_path = self.parent.path
        path= self.output_path.get()
        if path.startswith('/'):
            path = relpath(path, dataset_path)

        if path.startswith('..'):
            showerror(parent=self.top, title="Error", message="Output path must be in dataset")
            return

        abs_path = pathlib.Path(dataset_path) / path
        if not exists(abs_path):
            showerror(parent=self.top, title="Error", message="Output path must exist")
            return

        with open(abs_path / "defaults.json", "w") as f:
            json.dump(self.get_defaults_from_ui(), f, indent=4)
        self.close()

    def cancel(self, event = None):
        self.close()
        return "break"

    def close(self):
        self.top.grab_release()
        self.top.destroy()
        return "break"

    def browse(self, event = None):
        #Popup folder selection dialog
        default_dir = self.parent.image_files[self.parent.file_index].parent
        try:
            path = tk.filedialog.askdirectory(
                parent=self.top, 
                initialdir=default_dir,
                title="Select a location for subset output")
        except:
            print(traceback.format_exc())
            return

        if path:
            pl_path = pathlib.Path(relpath(path, self.parent.path))
            if str(pl_path).startswith(".."):
                showerror(message=
                          "Output path must be in dataset")
                self.output_path.set(relpath(default_dir, self.parent.path))
            else:
                self.output_path.set(str(pl_path))
        return "break"


class manually_review_subset_popup(object):
    def __init__(self, parent, subset_path, image_files, review_all, max_tokens):
        try:
            if not tokenizer_ready:
                showerror(parent=parent.top,
                            title="Not ready",
                            message="The tokenizer is not yet ready.")
                self.top = tk.Toplevel(self.parent.top)
                self.close()
                return
            self.parent = parent
            self.dataset_path = self.parent.parent.path
            self.subset_path = subset_path
            self.max_tokens = max_tokens
            self.file_index = 0
            self.image_files = image_files.copy()
            self.icon_image = Image.open("icon.png")
            if not review_all:
                for f in reversed(image_files):
                    caption_file = "".join(splitext(f)[:-1]) + ".txt"
                    caption = self.get_caption_from_file(caption_file)
                    if num_tokens_from_string(caption, "gpt2") <= self.max_tokens:
                        self.image_files.remove(f)

            if len(self.image_files) == 0:
                showinfo(parent=parent.top,
                         title="No such files",
                         message="No images had more than " + str(self.max_tokens) +  " tokens.")
                self.top = tk.Toplevel(self.parent.top)
                self.close()
                return

            self.icon_image = Image.open("icon.png")

            self.create_ui()
        except:
            print(traceback.format_exc())
           
    def create_ui(self):
        self.top = tk.Toplevel(self.parent.top)
        self.top.title("Manually review captions")
        self.create_primary_frame()
        self.set_ui(self.file_index)

 
    #Create primary frame
    def create_primary_frame(self):
        self.root_frame = tk.Frame(self.top)
        self.top.rowconfigure(0, weight=1)
        self.top.columnconfigure(0, weight=1)
        self.top.minsize(700, 400)

        self.top.wait_visibility()
        self.top.grab_set()
        self.top.transient(self.parent.top)

        self.root_frame.grid(padx=0, pady=0, sticky="nsew")
        self.root_frame.rowconfigure(0, weight = 1)
        self.root_frame.columnconfigure(0, weight = 2)
        self.root_frame.columnconfigure(1, weight = 0)
        self.root_frame.columnconfigure(1, minsize=400)

        self.create_image_frame()
        self.create_form_frame()
        self.statusbar_text = tk.StringVar()
        self.statusbar = tk.Label(self.top, 
                                  textvar=self.statusbar_text, 
                                  bd=1, 
                                  relief=tk.RAISED, 
                                  anchor=tk.W)
        self.statusbar.grid(row=1, column=0, sticky="ew")

    #Create the frame for image display
    def create_image_frame(self):
        self.image_frame = tk.Frame(self.root_frame, 
                              width=400, height=400, 
                              bd=2, 
                              relief=tk.SUNKEN)
        self.image_frame.grid(row=0, column=0, padx=0, pady=0, sticky="nsew")
        self.image_frame.rowconfigure(0, weight=1)
        self.image_frame.columnconfigure(0, weight=1)

        # Display image in image_frame
        self.image = self.icon_image
        self.framed_image = ImageTk.PhotoImage(self.image)
        self.sizer_frame = tk.Frame(self.image_frame,
                                    width=400, height=400,
                                    bd=0)
        self.sizer_frame.grid(row=0, column=0, sticky="nsew")
        self.sizer_frame.rowconfigure(0, weight=1)
        self.sizer_frame.columnconfigure(0, weight=1)

        self.image_label = tk.Label(self.sizer_frame, 
                                    image=self.framed_image, 
                                    bd=0)
        self.image_label.grid(row=0, column=0, sticky="nsew")
        self.sizer_frame.bind("<Configure>", self.image_resizer)

    #Create the frame for form display
    def create_form_frame(self):
        self.form_frame = tk.Frame(self.root_frame,
                               width=300, height=400, 
                               bd=1,
                               relief=tk.RAISED)
        self.form_frame.grid(row=0, column=1, 
                              padx=0, pady=0, 
                              sticky="nsew")
        
        self.form_frame.columnconfigure(1, weight = 1)

        caption_label = tk.Label(self.form_frame, text="Caption: ")
        caption_label.grid(row=4, column=0, padx=5, pady=(5,0), sticky="sw")

        self.token_count_label = tk.Label(self.form_frame, text="Tokens: 0 / " + str(self.max_tokens))
        self.token_count_label.grid(row=4, column=1, padx=5, pady=(5,0), sticky="se")

        self.caption_textbox = tk.Text(self.form_frame, width=30, height=12, wrap=tk.WORD, spacing2=2, spacing3=2)

        self.caption_textbox.grid(row=5, column=0, 
                             columnspan=2, 
                             padx=5, pady=(0,5), 
                             sticky="ew")
        self.caption_textbox.bind("<Tab>", self.focus_next_widget)
        self.caption_textbox.bind('<Control-a>', self.select_all)
        self.caption_textbox.focus_set()
        self.caption_textbox.bind('<KeyRelease>', self.update_token_count)

        save_txt_btn = tk.Button(self.form_frame, 
                                  text="Auto truncate (Ctrl+T)", 
                                  command=self.auto_truncate)
        save_txt_btn.grid(row=12, column=0, 
                           columnspan=2, 
                           padx=5, pady=5, 
                           sticky="ew")
        self.caption_textbox.bind('<Control-t>', self.auto_truncate)


        save_txt_btn = tk.Button(self.form_frame, 
                                  text="Confirm file (Ctrl+S)", 
                                  command=self.save_txt)
        save_txt_btn.grid(row=13, column=0, 
                           columnspan=2, 
                           padx=5, pady=5, 
                           sticky="ew")
        self.top.bind("<Control-s>", self.save_txt)

        self.prev_file_btn = tk.Button(self.form_frame, 
                                  text="Previous (Ctrl+P/B)", 
                                  command=self.prev_file)
        self.prev_file_btn.grid(row=14, column=0, 
                           padx=5, pady=5, 
                           sticky="ew")
        self.top.bind("<Control-p>", self.prev_file)
        self.top.bind("<Control-b>", self.prev_file)

        self.next_file_btn = tk.Button(self.form_frame, 
                                  text="Next (Ctrl+N/F)", 
                                  command=self.next_file)
        self.next_file_btn.grid(row=14, column=1, 
                           padx=5, pady=5, 
                           sticky="ew")
        self.top.bind("<Control-n>", self.next_file)
        self.top.bind("<Control-f>", self.next_file)   
        self.top.bind("<Control-Home>", self.first_file )
        self.top.bind("<Control-End>", self.last_file)   


    #Create open dataset action
    def open_dataset(self, event = None):
        self.clear_ui()

        #Clear the UI and associated variables
        self.file_index = 0
        self.image_files = []


        #Get supported extensions
        exts = Image.registered_extensions()
        supported_exts = {ex for ex, f in exts.items() if f in Image.OPEN}

        #Get list of filenames matching those extensions
        files = [pathlib.Path(f).absolute()
                 for f in pathlib.Path(self.path).rglob("*")
                  if isfile(join(self.path, f))]
        
        self.image_files = [
            f for f in files if splitext(f)[1] in supported_exts]  

        self.image_files.sort()

        #Point UI to beginning of queue
        if(len(self.image_files) > 0):
            self.file_index = 0
            self.set_ui(self.file_index)

    #Ask user if they want to save if needed
    def save_unsaved_popup(self):
        if(len(self.image_files) == 0 or self.file_index >= len(self.image_files)):
            return False

        index = self.file_index
        caption_file = "".join(splitext(self.image_files[index])[:-1]) + ".txt"
        caption = self.get_caption_from_file(caption_file)

        if(self.get_caption_from_ui() != caption):
            answer = askyesno(parent=self.top,
                              title='Confirm image?',
                            message='You have changed the caption. Confirm now?')
            if answer:
                self.save_txt()
                return True
        return False

    def load_image(self, f):
        self.image = Image.open(f)
        self.image_resizer()

    #Resize image to fit resized window
    def image_resizer(self, e = None):
        tgt_width = self.image_frame.winfo_width() - 4
        tgt_height = self.image_frame.winfo_height() - 4

        if tgt_width < 1:
            tgt_width = 1
        if tgt_height < 1:
            tgt_height = 1

        new_width = int(tgt_height * self.image.width / self.image.height)
        new_height = int(tgt_width * self.image.height / self.image.width)

        if new_width < 1:
            new_width = 1
        if new_height < 1:
            new_height = 1

        if new_width <= tgt_width:
            resized_image = self.image.resize(
                (new_width, tgt_height), 
                Image.LANCZOS)
        else:
            resized_image = self.image.resize(
                (tgt_width, new_height), 
                Image.LANCZOS)
        self.framed_image = ImageTk.PhotoImage(resized_image)
        self.image_label.configure(image=self.framed_image)

    #Move the focus to the prev item in the form
    def focus_prev_widget(self, event):
        event.widget.tk_focusPrev().focus()
        return("break")


    #Move the focus to the next item in the form
    def focus_next_widget(self, event):
        event.widget.tk_focusNext().focus()
        return("break")


    #Add UI elements for prev file button
    def prev_file(self, event = None):
        if self.file_index <= 0:
            self.file_index = 0
            return #Nothing to do if we're at first index.
        
        #Pop up unsaved data dialog if needed
        if self.save_unsaved_popup():
            self.file_index -= 1
            self.set_ui(self.file_index)
            return

        #Point UI to previous item in queue
        self.clear_ui()
        self.file_index -= 1
        self.set_ui(self.file_index)



    #Add UI elements for next file button
    def next_file(self, event = None):
        if self.file_index >= len(self.image_files) - 1:
            self.file_index = len(self.image_files) - 1
            return #Nothing to do if we're at first index.
                
        #Pop up unsaved data dialog if needed
        if self.save_unsaved_popup():
            return

        #Point UI to next item in queue
        self.clear_ui()
        self.file_index += 1
        self.set_ui(self.file_index)


    #Add UI elements for next file button
    def first_file(self, event = None):
        #Pop up unsaved data dialog if needed
        if self.save_unsaved_popup():
            return

        #Point UI to next item in queue
        self.clear_ui()
        self.file_index = 0
        self.set_ui(self.file_index)


    #Add UI elements for next file button
    def last_file(self, event = None):
        #Pop up unsaved data dialog if needed
        if self.save_unsaved_popup():
            return

        #Point UI to next item in queue
        self.clear_ui()
        self.file_index = len(self.image_files) - 1
        self.set_ui(self.file_index)


    #Clear the UI
    def clear_ui(self):
        if len(self.image_files) == 0:
            self.close()
            return
        self.image = self.icon_image
        self.framed_image = ImageTk.PhotoImage(self.image)
        self.image_label.configure(image=self.framed_image)
        self.caption_textbox.delete("1.0", "end")
        self.statusbar_text.set("")

    def update_token_count(self, event = None):
        count = num_tokens_from_string(self.get_caption_from_ui(), "gpt2")
        self.token_count_label.configure(text=f"Tokens: {count} / " + str(self.max_tokens))


    #Set the UI to the given item's values
    def set_ui(self, index: int):
        self.clear_ui()
        
        if(len(self.image_files) == 0 or self.file_index >= len(self.image_files)):
            return False


        caption_file = "".join(splitext(self.image_files[index])[:-1]) + ".txt"
        try:
            self.caption_textbox.insert(
                "1.0", 
                self.get_caption_from_file(caption_file))
        except:
            print(traceback.format_exc())


        f = self.image_files[index]        
        self.load_image(f)
        self.statusbar_text.set(
            f"Image {1 + self.file_index}/{len(self.image_files)}: "
            f"{relpath(pathlib.Path(self.image_files[self.file_index]), self.parent.parent.path)}")
        
        #Enable/disable buttons as appropriate
        if self.file_index > 0:
            self.prev_file_btn["state"] = "normal"
        else:
            self.prev_file_btn["state"] = "disabled"

        if self.file_index < len(self.image_files) - 1:
            self.next_file_btn["state"] = "normal"
        else:
            self.next_file_btn["state"] = "disabled"
            
        self.update_token_count()
        self.top.update_idletasks()


    def select_all(self, event):
        # select text
        try:
            event.widget.select_range(0, 'end')
        except:
            print(traceback.format_exc())
            event.widget.tag_add("sel", "1.0", "end")

        # move cursor to the end
        try:
            event.widget.icursor('end')
        except:
            print(traceback.format_exc())
            event.widget.mark_set("insert", "end")

        #stop propagation
        return 'break'


    def get_caption_from_ui(self):
        return ' '.join(self.caption_textbox.get("1.0", "end").split())

    def get_caption_from_file(self, caption_file):
        caption = ""
        try:
            with open(caption_file) as f:
                caption = f.read()
        except:
            showwarning(parent=self.top,
                      title="Couldn't read caption",
                      message=f"Could not read TXT file {caption_file}")
            print(traceback.format_exc())

        return caption


    def write_caption_to_file(self, caption, caption_file):
        try:
            with open(caption_file, "w") as f:
                f.write(caption)
        except:
            showerror(parent=self,
                      title="Couldn't save caption",
                      message=f"Could not save TXT file {caption_file}")
            print(traceback.format_exc())

    def auto_truncate(self, event = None):
        caption = self.get_caption_from_ui()

        truncated = truncate_string_to_max_tokens(caption,self.max_tokens)
        self.caption_textbox.delete("1.0", "end")
        self.caption_textbox.insert("1.0", truncated)
        return "break"
        
    #Add UI elements for save JSON button
    def save_txt(self, event = None):
        self.write_caption_to_file(
            self.get_caption_from_ui(),
            "".join(splitext(self.image_files[self.file_index])[:-1]) + ".txt")
        del self.image_files[self.file_index]
        if self.file_index >= len(self.image_files):
            self.file_index -= 1
        if self.file_index < 0:
            self.close()
        self.set_ui(self.file_index)

    def close(self, event = None):
        self.top.grab_release()
        self.top.destroy()

class NumericEntry(tk.Entry):
    def __init__(self, master=None, **kwargs):
        self.var = tk.StringVar()
        tk.Entry.__init__(self, master, textvariable=self.var, **kwargs)
        self.old_value = ''
        self.var.trace_add('write', self.check)
        self.get, self.set = self.var.get, self.var.set

    def check(self, *args):
        if self.get().isdigit() or self.get() == "": 
            # the current value is only digits; allow this
            self.old_value = self.get()
        else:
            # there's non-digit characters in the input; reject this 
            self.set(self.old_value)

class generate_lora_subset_popup(object):
    def __init__(self, parent):
        self.parent = parent

        self.create_ui()

    def create_ui(self):
        self.top = tk.Toplevel(self.parent)
        self.top.title("Generate LoRA subset...")
        self.top.wait_visibility()
        self.top.grab_set()
        self.top.rowconfigure(0, weight=1)
        self.top.columnconfigure(0, weight=1)
        self.top.minsize(600, 400)
        self.top.transient(self.parent)

        self.form_frame = tk.Frame(self.top, 
                                   borderwidth=2,
                                   relief='raised',)
        self.form_frame.grid(row=0, column=0, 
                        padx=0, pady=0, 
                        sticky="nsew")
        
        self.form_frame.columnconfigure(1, weight=1)
        self.form_frame.rowconfigure(9, weight=1)

        #LoRA Output location
        output_path_label = tk.Label(self.form_frame, text="Output path: ")
        output_path_label.grid(row=0, column=0, padx=(5, 0), pady=5, sticky="e")

        self.output_path = tk.StringVar(None)
        self.output_path.set(pathlib.Path().absolute() / "lora_subsets")
        self.output_path.trace("w", lambda name, index, mode: 
                                self.populate_from_newest_subset())
        output_path_entry = tk.Entry(self.form_frame,
                                     textvariable=self.output_path, 
                                     justify="left")
        output_path_entry.grid(row=0, column=1, 
                               padx=(0, 5), pady=5, 
                               sticky="ew")
        output_path_entry.bind('<Control-a>', self.select_all)

        #Browse button
        browse_btn = tk.Button(self.form_frame, text='Browse...', 
                               command=self.browse)
        browse_btn.grid(row=0, column=2, padx=4, pady=4, sticky="sew")
        self.top.bind("<Control-b>", self.browse)

        #LoRA name
        lora_name_label = tk.Label(self.form_frame, text="LoRA name: ")
        lora_name_label.grid(row=1, column=0,
                             padx=(5, 0), pady=5, 
                             sticky="e")

        self.lora_name = tk.StringVar(None)
        self.lora_name.set("_".join(self.find_newest_subset("").split("_")[1:]))
        self.nametracer = self.lora_name.trace("w", lambda name, index, mode: 
                                self.populate_from_newest_subset())
        lora_name_entry = tk.Entry(self.form_frame,
                                     textvariable=self.lora_name, 
                                     justify="left")
        lora_name_entry.grid(row=1, column=1, 
                             columnspan=2,
                             padx=(0, 5), pady=5, 
                             sticky="ew")
        lora_name_entry.bind('<Control-a>', self.select_all)
        lora_name_entry.focus_set()
        lora_name_entry.select_range(0, 'end')


        #Labeled group for options
        settings_group = tk.LabelFrame(self.form_frame, 
                                    text="Settings")
        settings_group.grid(row=2, column=0, 
                            columnspan=3, 
                            padx=5, pady=5,
                            sticky="nsew")

        #Checkbox for inclusion of trigger word
        self.include_lora_name = tk.BooleanVar(None)
        self.include_lora_name.set(True)
        include_lora_name_chk = tk.Checkbutton(
            settings_group,
            var=self.include_lora_name,
            text="LoRA name included as trigger")
        include_lora_name_chk.grid(row=0, column=0, padx=5, pady=5, sticky="w")

        #Checkbox for inclusion of artist
        self.include_artist = tk.BooleanVar(None)
        self.include_artist.set(False)
        include_artist_chk = tk.Checkbutton(
            settings_group,
            var=self.include_artist,
            text="Artist included as trigger")
        include_artist_chk.grid(row=1, column=0, padx=5, pady=5, sticky="w")

        #Checkbox for inclusion of style
        self.include_style = tk.BooleanVar(None)
        self.include_style.set(False)
        include_style_chk = tk.Checkbutton(
            settings_group,
            var=self.include_style,
            text="Style included in caption")
        include_style_chk.grid(row=2, column=0, padx=5, pady=5, sticky="w")

        #Checkbox for inclusion of summary
        self.include_summary = tk.BooleanVar(None)
        self.include_summary.set(True)
        include_summary_chk = tk.Checkbutton(
            settings_group,
            var=self.include_summary,
            text="Summary included in caption")
        include_summary_chk.grid(row=3, column=0, padx=5, pady=5, sticky="w")

        #Checkbox for inclusion of this LoRA's associated description
        self.include_feature = tk.BooleanVar(None)
        self.include_feature.set(True)
        include_feature_chk = tk.Checkbutton(
            settings_group,
            var=self.include_feature,
            text="Feature for LoRA name included")
        include_feature_chk.grid(row=4, column=0, padx=5, pady=5, sticky="w")

        #Checkbox for inclusion of other feature descriptions
        self.include_other_features = tk.BooleanVar(None)
        self.include_other_features.set(True)
        include_other_features_chk = tk.Checkbutton(
            settings_group,
            var=self.include_other_features,
            text="Other features included")
        include_other_features_chk.grid(row=5, column=0, padx=5, pady=5, sticky="w")

        #Checkbox for inclusion of this LoRA's associated description
        self.include_automatic_tags = tk.BooleanVar(None)
        self.include_automatic_tags.set(True)
        include_automatic_tags_chk = tk.Checkbutton(
            settings_group,
            var=self.include_automatic_tags,
            text="Automatic tags included in caption")
        include_automatic_tags_chk.grid(row=6, column=0, padx=5, pady=5, sticky="w")

        #Checkbox to ask if captions should be manually reviewed if over token max
        review_group = tk.LabelFrame(settings_group, 
                                    text="Manual review options")
        review_group.grid(row=0, column=1, rowspan=3, columnspan=2,
                          sticky="ew")

        self.review_option = tk.IntVar()

        self.review_option.set(1)
        tk.Radiobutton(review_group, 
           text=f"None",
           variable=self.review_option, 
           value=0).grid(row=0, column=0, sticky="w")
        tk.Radiobutton(review_group, 
           text=f"Auto-truncate to max tokens",
           variable=self.review_option, 
           value=1).grid(row=1, column=0, sticky="w")
        tk.Radiobutton(review_group, 
           text=f"Review if over max tokens",
           variable=self.review_option, 
           value=2).grid(row=2, column=0, sticky="w")
        tk.Radiobutton(review_group, 
           text=f"Review all",
           variable=self.review_option, 
           value=3).grid(row=3, column=0, sticky="w")


        #max Tokens
        max_tokens_label = tk.Label(settings_group, text="Max Tokens: ")
        max_tokens_label.grid(row=3, column=1,
                             padx=(10, 0), pady=5, 
                             sticky="w")


        self.max_tokens = NumericEntry(settings_group,
                                     justify="left")
        self.max_tokens.set(75)
        self.max_tokens.grid(row=3, column=2, 
                             padx=(0, 5), pady=5, 
                             sticky="ew")
        self.max_tokens.bind('<Control-a>', self.select_all)

        #Steps per image
        steps_per_image_label = tk.Label(settings_group, text="Steps per image: ")
        steps_per_image_label.grid(row=4, column=1,
                             padx=(10, 0), pady=5, 
                             sticky="w")

        self.steps_per_image_entry = NumericEntry(settings_group,
                                     justify="left")
        self.steps_per_image_entry.set(100)
        self.steps_per_image_entry.grid(row=4, column=2, 
                             padx=(0, 5), pady=5, 
                             sticky="ew")
        self.steps_per_image_entry.bind('<Control-a>', self.select_all)


        #Checkbox to enable filtering
        self.enable_filtering = tk.BooleanVar(None)
        self.enable_filtering.set(False)
        enable_filtering_chk = tk.Checkbutton(
            settings_group,
            var=self.enable_filtering,
            text="Enable filtering")        
        enable_filtering_chk.grid(row=5, column=1, padx=5, pady=5, sticky="w")

        self.filter = tk.StringVar(None)
        self.filter.set("")
        self.filter_entry = tk.Entry(settings_group,
                                     textvariable=self.filter,
                                     justify="left")
        self.filter_entry.grid(row=5, column=2, 
                             padx=(0, 5), pady=5, 
                             sticky="ew")
        self.filter_entry.bind('<Control-a>', self.select_all)        

        self.enable_filtering.trace("w", 
                lambda name, index, mode: self.on_enable_filtering_modified())

        #Labeled group for rating
        self.filter_rating = tk.BooleanVar(None)
        self.filter_rating.set(False)
        filter_rating_chk = tk.Checkbutton(
            settings_group,
            var=self.filter_rating,
            text=f"Filter quality >= ")
        filter_rating_chk.grid(row=6, column=1, padx=5, pady=5, sticky="w")

        rating_group = tk.LabelFrame(settings_group, 
                                    text="Minimum Quality")
        rating_group.grid(row=6, column=2, 
                          padx=5, pady=1,
                          sticky="nsew")

        self.minimum_rating = tk.IntVar()
        self.minimum_rating.set(False)
        tk.Radiobutton(rating_group, 
           text=f"Not rated",
           variable=self.minimum_rating, 
           value=0).grid(row=0, column=0, padx=5, pady=1, sticky="w")

        for i in range(1, 6):
            tk.Radiobutton(rating_group, 
               text=f"{i}",
               variable=self.minimum_rating, 
               value=i).grid(row=0, column=i, pady=1, sticky="w")
        self.minimum_rating.trace("w", lambda name, index, mode: 
                        self.filter_rating.set(True))

        #Checkbox for fetching automatic tags if empty
        self.interrogate_automatic_tags = tk.BooleanVar(None)
        self.interrogate_automatic_tags.set(True)
        interrogate_automatic_tags_chk = tk.Checkbutton(
            settings_group,
            var=self.interrogate_automatic_tags,
            text="Interrogate image if automatic tags empty")
        interrogate_automatic_tags_chk.grid(row=6, column=1, columnspan=2, padx=5, pady=5, sticky="w")

        # Cancel button
        cancel_btn = tk.Button(self.form_frame, text='Cancel', 
                               command=self.cancel)
        cancel_btn.grid(row=10, column=0, padx=4, pady=4, sticky="sew")
        self.top.bind("<Escape>", self.cancel)
        self.top.bind("<Control-g>", self.generate)

        # Generate button
        generate_btn = tk.Button(self.form_frame, text='Generate (Ctrl+G)', 
                               command=self.generate)
        generate_btn.grid(row=10, column=1,
                          columnspan=2,
                          padx=4, pady=4, 
                          sticky="sew")
        
        self.populate_from_newest_subset()

    def select_all(self, event):
        # select text
        try:
            event.widget.select_range(0, 'end')
        except:
            print(traceback.format_exc())
            event.widget.tag_add("sel", "1.0", "end")

        # move cursor to the end
        try:
            event.widget.icursor('end')
        except:
            print(traceback.format_exc())
            event.widget.mark_set("insert", "end")

        #stop propagation
        return 'break'


    def close(self):
        self.top.grab_release()
        self.top.destroy()

    def browse(self, event = None):
        #Popup folder selection dialog
        default_dir = pathlib.Path().absolute() / "lora_subsets"
        try:
            path = tk.filedialog.askdirectory(
                parent=self.top, 
                initialdir=default_dir,
                title="Select a location for subset output")
        except:
            print(traceback.format_exc())
            return

        if path:
            pl_path = pathlib.Path(path)
            pl_parent_path = pathlib.Path(self.parent.path)
            if(pl_path in pl_parent_path.parents 
               or pl_parent_path in pl_path.parents
               or pl_path == pl_parent_path):
                showerror(message=
                          "Output path may not be an ancestor of dataset path, "
                          "nor may it be within the dataset tree. This is to "
                          "reduce the chances of clobbering the dataset with "
                          "the subset.")
                self.output_path.set(default_dir)
            else:
                self.output_path.set(path)

    def on_enable_filtering_modified(self):
        if self.enable_filtering.get():
            self.filter_entry.config(state="normal")
        else:
            self.filter_entry.config(state="disabled")

    def cancel(self, event = None):
        self.close()

    #Save an info JSON for this subset to identify it as ours
    def save_subset_info(self, path):
        info_path = path / "LoRA_info.json"
        info = {
            "lora_tag_helper_version": 1,
            "name": self.lora_name.get(),
            "include_lora_name": self.include_lora_name.get(),
            "include_artist": self.include_artist.get(),
            "include_style": self.include_style.get(),
            "include_summary": self.include_summary.get(),
            "include_feature": self.include_feature.get(),
            "include_other_features": self.include_other_features.get(),
            "include_automatic_tags": self.include_automatic_tags.get(),
            "interrogate_automatic_tags": False,
            "review_option": self.review_option.get(),
            "steps_per_image": self.steps_per_image_entry.get(),
            "enable_filtering": self.enable_filtering.get(),
            "filter": self.filter.get(),
            "filter_rating": self.filter_rating.get(),
            "minimum_rating": self.minimum_rating.get()
        }
        with open(info_path, "w") as f:
            json.dump(info, f, indent=4)
        utime(path)

    #Load info JSON from a subset
    def load_subset_info(self, path):
        info_path = pathlib.Path(path) / "LoRA_info.json"
        try:
            with open(info_path) as f:
                info = json.load(f)
            return info
        except:
            print(traceback.format_exc())
            return None
        

    def find_newest_subset(self, lora_name):
        #Find the newest subset matching the current lora name.
        try:
            dirs = [x for x in next(walk(self.output_path.get()))[1]]
            matching_dirs = [pathlib.Path(self.output_path.get()) / x 
                             for x in dirs if x.endswith(lora_name)]
            
            ordered_dirs = sorted(matching_dirs, key=getmtime)

            ordered_info = [self.load_subset_info(x) for x in ordered_dirs]

            for dir, info in zip(reversed(ordered_dirs), reversed(ordered_info)):
                if info:
                    try:
                        if("name" in info
                           and "include_lora_name" in info
                           and "include_artist" in info
                           and "include_style" in info
                           and "include_summary" in info
                           and "include_feature" in info
                           and "include_other_features" in info
                           and "include_automatic_tags" in info
                           and "review_option" in info
                           and "steps_per_image" in info):
                            return pathlib.Path(dir).name
                    except:
                        print(traceback.format_exc())
        except:
            print(traceback.format_exc())
        return "100_default"
        
    #Find the newest appropriate subset in the path and populate info from it
    def populate_from_newest_subset(self):
        #Find the newest subset matching the current lora name.
        try:
            subset = self.find_newest_subset(self.lora_name.get())
            subset_path = pathlib.Path(self.output_path.get()) / subset
            info = self.load_subset_info(subset_path)
            if info:
                if(self.lora_name.get() == ""
                   or self.lora_name.get() == "default"):
                    self.lora_name.set(info["name"])
                self.include_lora_name.set(info["include_lora_name"])
                self.include_artist.set(info["include_artist"])
                self.include_style.set(info["include_style"])
                self.include_summary.set(info["include_summary"])
                self.include_feature.set(info["include_feature"])
                self.include_other_features.set(info["include_other_features"])
                self.include_automatic_tags.set(info["include_automatic_tags"])
                self.review_option.set(info["review_option"])
                self.steps_per_image_entry.set(info["steps_per_image"])
                try:
                    self.enable_filtering.set(info["enable_filtering"])
                except KeyError:
                    pass
                try:
                    self.filter.set(info["filter"])
                except KeyError:
                    pass
                try:
                    self.filter_rating.set(info["filter_rating"])
                except KeyError:
                    pass
                try:
                    self.minimum_rating.set(info["minimum_rating"])
                except KeyError:
                    pass
                try:
                    self.interrogate_automatic_tags.set(info["interrogate_automatic_tags"])
                except KeyError:
                    pass

        except:
            print(traceback.format_exc())
        

    def generate(self, event = None):
        #Validate output path
        default_dir = pathlib.Path().absolute() / "lora_subsets"
        output_path = pathlib.Path(self.output_path.get())
        dataset_path = pathlib.Path(self.parent.path)        
        if(output_path in dataset_path.parents 
           or dataset_path in output_path.parents
           or output_path == dataset_path):
            showerror(message=
                  "Output path must not be an ancestor of dataset path, "
                  "nor may it be within the dataset tree. This is to "
                  "reduce the chances of clobbering the dataset with "
                  "the subset.")
            self.output_path.set(default_dir)
            return

        #Validate LoRA name
        self.lora_name.trace_vdelete("w", self.nametracer)
        self.lora_name.set('_'.join(self.lora_name.get().split()))
        self.nametracer = self.lora_name.trace("w", lambda name, index, mode: 
                                self.populate_from_newest_subset())

        #  Make num_name folder or error if it already exists and isn't labeled
        #  as LoRA subset
        subset_path = (pathlib.Path(self.output_path.get())
                         / '_'.join([self.steps_per_image_entry.get(),
                                    self.lora_name.get()]))
        
        if not exists(subset_path):
            makedirs(subset_path)
        else:
            info = self.load_subset_info(subset_path)
            if not info:
                showerror(message=
                          "The output directory exists, but does not have "
                          "valid subset information. Aborting to avoid "
                          "clobbering non-subset directory.")                
                return
            else:
                exts = Image.registered_extensions()
                supported_exts = {ex for ex, f in exts.items() if f in Image.OPEN}
                supported_exts.update({".txt", ".json"})
                stale_files = [pathlib.Path(f).absolute()
                         for f in pathlib.Path(subset_path).rglob("*")
                          if isfile(join(subset_path, f))]
                msg_box = tk.messagebox.askyesnocancel('Existing Subset', f"{len(stale_files)} files already exist in '{subset_path}'." 
                                                    "\nDelete them?",
                                                    parent=self.top,
                                                    icon='warning')
                if msg_box is not None:
                    if msg_box == True:
                        for f in stale_files:
                            remove(f)
                else:
                    showinfo(parent=self.top,
                             title="Generation canceled",
                             message=f"Generation canceled.")
                    return
                        
                
        

        self.save_subset_info(subset_path)

        popup = tk.Toplevel(self.top)
        tk.Label(popup, text="Processing subset images...").grid(row=0,column=0)
        progress_var = tk.DoubleVar()
        progress_var.set(0)
        progress_bar = tk.ttk.Progressbar(popup, variable=progress_var, maximum=100)
        progress_bar.grid(row=1, column=0)#.pack(fill=tk.X, expand=1, side=tk.BOTTOM)
        popup.pack_slaves()
        current_image_index = 0
        output_images = []
        #For each image
        for path in self.parent.image_files:
            #Update progress bar
            progress_var.set(100 * current_image_index / len(self.parent.image_files))
            popup.update()
            current_image_index += 1

            #Load associated JSON and/or TXT as normal
            self.parent.prompt = ""
            item = self.parent.get_item_from_file(path)

            #Get unique flat name for file
            tgt_image = relpath(pathlib.Path(path), self.parent.path)
            tgt_parent= relpath(pathlib.Path(tgt_image).parent)
            tgt_basename = relpath(pathlib.Path(tgt_image).name)
            tgt_image = tgt_basename
            tgt_name = "".join(tgt_basename)[:-1]
            tgt_ext = splitext(tgt_image)[-1]

            if(tgt_name != item["title"] and item["title"]):
                tgt_image = str(pathlib.Path(tgt_parent) / item["title"]) + tgt_ext

            tgt_image = tgt_image.replace(sep, "_")
            i = 2
            while exists(tgt_image):
                tgt_image = splitext(tgt_image)[0] + f"_{i}" + tgt_ext

            tgt_prefix = splitext(tgt_image)[0]
            

            #Save .txt to subset folder
            caption = ""
            if self.include_lora_name.get():
                caption += self.lora_name.get() + ", "
            
            if self.include_style.get() and item["style"]:
                caption += item["style"]

                if self.include_artist.get():
                    caption += " by "
                else:
                    caption += ", "

            if(self.include_artist.get()
               and item["artist"]):
                caption += item["artist"] + ", "
            
            if self.include_summary.get() and item["summary"]:
                caption += item["summary"] + ", "
            
            if(self.include_feature.get()
               and self.lora_name.get() in item["features"]):
                feature = item["features"][self.lora_name.get()]
                if feature == "":
                    feature = self.lora_name.get()
                caption += feature + ", "

            if self.include_other_features.get():
                for f in item["features"]:
                    if f != self.lora_name.get() and item["features"][f]:
                        feature = item["features"][f]
                        if feature == "":
                            feature = f
                        caption += feature + ", "

            try:
                if self.interrogate_automatic_tags.get() and not item["automatic_tags"]:
                    item["automatic_tags"] = interrogate_automatic_tags(path,self.parent.interrogator_settings)
            except:
                print(traceback.format_exc())
            
            if self.include_automatic_tags.get() and item["automatic_tags"]:
                caption += item["automatic_tags"]
            
            if caption.endswith(", "):
                caption = caption[:-2]


            components = caption.split(",")

            unique_components_forward = []
            for c in components:
                found = False
                for u_c in unique_components_forward:
                    if c.strip().lower() in u_c.strip().lower():
                        found = True
                if not found:
                    unique_components_forward.append(c.strip())

            unique_components = []
            for c in reversed(unique_components_forward):
                found = False
                for u_c in unique_components:
                    if c.strip().lower() in u_c.strip().lower():
                        found = True
                if not found:
                    unique_components.append(c.strip())

            unique_caption = ", ".join(reversed(unique_components))

            if self.enable_filtering.get():
                filtered_components_or = re.split(",| OR ", self.filter.get())
                match = False

                for c in filtered_components_or:
                    #Handle the AND operator
                    match_and = True
                    component_and = c.split(" AND ")
                    for c_and in component_and:
                        invert = False
                        while c_and.strip().startswith("NOT "):
                            c_and = c_and[4:]
                            invert = not invert

                        start_index = 1 if c_and in self.lora_name.get() and self.include_lora_name.get() else 0
                        filter_caption = ",".join(caption.split(",")[start_index:])

                        #Handle the NOT operator
                        cur_match_and = c_and.strip().lower() in filter_caption.lower()
                        if invert:
                            cur_match_and = not cur_match_and
                        match_and &= cur_match_and

                    #Handle the OR operator or comma (treated equivalently)
                    match |= match_and

                #If this item doesn't match the filter, skip it.
                if not match:
                    continue

            caption = bytes(unique_caption, 'utf-8').decode('utf-8', 'ignore')
            #codecs.encode(unique_caption,'UTF-8',"ignore")

            if self.filter_rating.get() and item["rating"] < self.minimum_rating.get():
                continue

            if self.review_option.get() == 1: #Auto-truncate
                caption = truncate_string_to_max_tokens(caption,int(self.max_tokens.get()))
            with open(str(subset_path / tgt_prefix) + ".txt", "w",encoding='utf-8') as f:
                f.write(" ".join(caption.split()))

            #Crop image and output to subset folder
            crop = item["crop"]
            if crop != [0, 0, 1, 1]:            
                with Image.open(path) as cropped_img:
                    cropped_img = cropped_img.crop(
                        (crop[0] * cropped_img.width,
                         crop[1] * cropped_img.height,
                         crop[2] * cropped_img.width, 
                         crop[3] * cropped_img.height))
                    cropped_img.save(subset_path / tgt_image)
            else:
                shutil.copy2(path, subset_path / tgt_image)

            output_images.append(subset_path / tgt_image)

            #Copy JSON to subset folder
            json_file = "".join(splitext(path)[:-1]) + ".json"
            target_json = str(subset_path / tgt_prefix) + ".json"
            if isfile(json_file):
                shutil.copy2(json_file, target_json)
            else:
                self.parent.prompt = ""
                self.parent.write_item_to_file(
                    self.parent.get_item_from_file(path),
                    target_json
                    )


        popup.destroy()

        if len(output_images) == 0:
            showwarning(parent=self.top,
                        title="Empty Dataset",
                        message="No images matched filter.")
            return
            

        #Pop up box for manual review
        try:
            print(f"About to wait for window: {self.review_option.get()}")
            if self.review_option.get() > 1: 
                self.top.wait_window(manually_review_subset_popup(
                        self,
                        subset_path,
                        output_images.copy(),
                        self.review_option.get() > 2).top,
                        int(self.max_tokens.get()))

        except:
            print(traceback.format_exc())

        #Message showing stats of created subset
        try:
            showinfo(parent=self.top,
                     title="Subset written",
                     message=f"Wrote {len(output_images)} images+jsons+captions "
                              "to subset folder.")

            self.close()
        except:
            print(traceback.format_exc())

class paste_settings(object):
    def __init__(self):
        self.con_title = False
        self.con_title_text = ""
        self.con_resolution = False

        self.set_artist = False
        self.set_style = False
        self.set_features = True
        self.set_summary = False
        self.set_rating = False
        self.set_autotags = False
        self.set_cropping = False

        self.c_width = 0
        self.c_height = 0

class paste_settings_popup(object):
    def __init__(self, parent):
        self.parent = parent
        self.create_ui()
        self.stay_on_top_and_follow()

    def create_ui(self):
        self.height = 520
        self.top = tk.Toplevel(self.parent)
        self.top.overrideredirect(1)
        self.top.minsize(200, self.height)
        self.top.maxsize(200, self.height)
        self.set_position()
        self.top.title("Set items to get pasted...")
        self.top.wait_visibility()
        self.top.grab_set()
        self.top.rowconfigure(0, weight=1)
        self.top.columnconfigure(0, weight=1)
        self.top.resizable(False,False)
        self.top.transient(self.parent)
        #abs_coord_x = self.parent.winfo_pointerx() - self.parent.winfo_rootx()
        #abs_coord_y = self.parent.winfo_pointery() - self.parent.winfo_rooty()


        self.form_frame = tk.Frame(self.top, 
                                   borderwidth=4,
                                   relief='raised',)
        
        self.form_frame.columnconfigure(0, weight=1)
        self.form_frame.rowconfigure(5, weight=1)

        #Conditions LabelFrame
        conditions_group = tk.LabelFrame(self.form_frame, text="Conditions")
        conditions_group.grid(row=0, column=0, 
                            columnspan=3, 
                            padx=5, pady=2,
                            sticky="nsew")

        conditions_group.columnconfigure(1, weight=1)
        conditions_group.rowconfigure(0, weight=1)

        self.title_sub_group = tk.Frame(conditions_group, 
                                   borderwidth=1,
                                   relief="flat")
        self.title_sub_group.grid(row=1, column=0, 
                columnspan=3, 
                padx=2, pady=2,
                sticky="nsew")
        self.title_sub_group.columnconfigure(1, weight=1)
        #self.title_sub_group.configure(relief="groove")

        #title_sub_group.rowconfigure(0, weight=1)

        # con_title_label = tk.Label(self.title_sub_group, text="Title: ")
        # con_title_label.grid(row=1, column=0,
        #                      padx=5, pady=2, 
        #                      sticky="w")
        
        self.con_title_text = tk.StringVar(None)
        self.con_title_text.set(self.parent.stored_item["title"] if self.parent.stored_item else "")

        self.con_title_entry = tk.Entry(self.title_sub_group,
                                     textvariable=self.con_title_text, 
                                     justify="left")
        self.con_title_entry.grid(row=1, column=0,
                               padx=10, pady=2, 
                               sticky="ew")

        #self.con_title_entry.bind('<Control-a>', self.select_all)

        self.con_title = tk.BooleanVar(None)
        self.con_title.set(self.parent.paste_set.con_title)
        con_title_chk = tk.Checkbutton(
            conditions_group,
            var=self.con_title,
            command=self.title_condition_toggled,
            text=f"Title contains")
        con_title_chk.grid(row=0, column=0, padx=5, pady=2, sticky="w")
        #self.con_title.trace_add('write',self.title_condition_toggled)
        self.title_condition_toggled()


        self.con_resolution = tk.BooleanVar(None)
        self.con_resolution.set(self.parent.paste_set.con_resolution)
        con_resolution_chk = tk.Checkbutton(
            conditions_group,
            var=self.con_resolution,
            text=f"Same size")
        con_resolution_chk.grid(row=2, column=0, padx=5, pady=2, sticky="w")


        #Settings LabelFrame
        settings_group = tk.LabelFrame(self.form_frame, text="Select items to paste")
        settings_group.grid(row=1, column=0, 
                            columnspan=3, 
                            padx=5, pady=2,
                            sticky="nsew")

        settings_group.columnconfigure(1, weight=1)

        #Checkbox for inclusion of artist
        self.set_artist = tk.BooleanVar(None)
        self.set_artist.set(self.parent.paste_set.set_artist)
        set_artist_chk = tk.Checkbutton(
            settings_group,
            var=self.set_artist,
            text=f"Artist")
        set_artist_chk.grid(row=0, column=0, padx=5, pady=2, sticky="w")

        #Checkbox for inclusion of style
        self.set_style = tk.BooleanVar(None)
        self.set_style.set(self.parent.paste_set.set_style)
        set_style_chk = tk.Checkbutton(
            settings_group,
            var=self.set_style,
            text=f"Style")
        set_style_chk.grid(row=1, column=0, padx=5, pady=2, sticky="w")


        #Checkbox for inclusion of features
        self.set_features = tk.BooleanVar(None)
        self.set_features.set(self.parent.paste_set.set_features)
        set_features_chk = tk.Checkbutton(
            settings_group,
            var=self.set_features,
            text=f"Features")
        set_features_chk.grid(row=2, column=0, padx=5, pady=2, sticky="w")


        self.set_summary = tk.BooleanVar(None)
        self.set_summary.set(self.parent.paste_set.set_summary)
        include_feature_descriptions_chk = tk.Checkbutton(
            settings_group,
            var=self.set_summary,
            text=f"Summary")
        include_feature_descriptions_chk.grid(row=3, column=0, padx=5, pady=2, sticky="w")


        #Checkbox for rating
        self.set_rating = tk.BooleanVar(None)
        self.set_rating.set(self.parent.paste_set.set_rating)
        set_rating_chk = tk.Checkbutton(
            settings_group,
            var=self.set_rating,
            text=f"Quality")
        set_rating_chk.grid(row=4, column=0, padx=5, pady=2, sticky="w")

        #Checkbox for auto tags
        self.set_autotags = tk.BooleanVar(None)
        self.set_autotags.set(self.parent.paste_set.set_autotags)
        set_rating_chk = tk.Checkbutton(
            settings_group,
            var=self.set_autotags,
            text=f"Auto tags")
        set_rating_chk.grid(row=5, column=0, padx=5, pady=2, sticky="w")

        #Checkbox for cropping
        self.set_cropping = tk.BooleanVar(None)
        self.set_cropping.set(self.parent.paste_set.set_cropping)
        set_cropping_chk = tk.Checkbutton(
            settings_group,
            var=self.set_cropping,
            text=f"Cropping")
        set_cropping_chk.grid(row=6, column=0, padx=5, pady=2, sticky="w")

        # Cancel button
        cancel_btn = tk.Button(self.form_frame, text='Cancel', 
                               command=self.cancel)
        cancel_btn.grid(row=6, column=0, padx=4, pady=4, sticky="sew")
        self.top.bind("<Escape>", self.cancel)


        # Accept button
        save_btn = tk.Button(self.form_frame, text='Accept', 
                               command=self.accept)
        save_btn.grid(row=6, column=1,
                          columnspan=2,
                          padx=4, pady=4, 
                          sticky="sew")

        self.form_frame.grid(row=0, column=0, 
                        padx=0, pady=0, 
                        sticky="nsew")

    def title_condition_toggled(self):
        if(self.con_title.get()):
            self.con_title_entry.configure(state="normal")
        else:
            self.con_title_entry.configure(state="disabled")


    def stay_on_top_and_follow(self):
        self.top.lift()
        self.top.after(1, self.stay_on_top_and_follow)
        self.set_position()
    
    def set_position(self):

        abs_coord_x = self.parent.paste_settings_btn.winfo_rootx() - 178
        abs_coord_y = self.parent.paste_settings_btn.winfo_rooty() - (self.height + 10)
        self.top.geometry('%dx%d+%d+%d' % (self.top.winfo_width(), self.top.winfo_height(), abs_coord_x, abs_coord_y))

    def accept(self, event = None):

        self.parent.paste_set.con_resolution = self.con_resolution.get()
        self.parent.paste_set.con_title = self.con_title.get()
        self.parent.paste_set.con_title_text = self.con_title_text.get()
        self.parent.paste_set.set_artist = self.set_artist.get()
        self.parent.paste_set.set_style = self.set_style.get()
        self.parent.paste_set.set_features = self.set_features.get()
        self.parent.paste_set.set_summary = self.set_summary.get()
        self.parent.paste_set.set_rating = self.set_rating.get()
        self.parent.paste_set.set_autotags = self.set_autotags.get()
        self.parent.paste_set.set_cropping = self.set_cropping.get()

        self.close()

    def cancel(self, event = None):
        self.close()
        return "break"

    def close(self):
        self.top.grab_release()
        self.top.destroy()
        return "break"

class rename_feature_popup(object):
    def __init__(self, parent, iid):
        self.parent = parent
        print("parent: " + str(parent))
        self.create_ui(iid)

    def create_ui(self,iid):
        print("iid: " + str(iid))
        feature_branch = iid.split(treeview_separator)
        print("fb: "+ str(feature_branch) + " iid: " + iid)
        feature_branch.reverse()
        self.target_branch = feature_branch
        self.top = tk.Toplevel(self.parent)
        self.top.title("Edit feature")
        self.top.wait_visibility()
        self.top.grab_set()
        self.top.rowconfigure(0, weight=1)
        self.top.columnconfigure(0, weight=1)
        self.top.minsize(300, 100)
        self.top.transient(self.parent)

        self.form_frame = tk.Frame(self.top, 
                                   borderwidth=2,
                                   relief='raised',)
        
        self.form_frame.columnconfigure(2, weight=1)
        self.form_frame.rowconfigure(5, weight=1)

        
        from_label = tk.Label(self.form_frame, text="From: ")
        from_label.grid(row=0, column=0, padx=(5, 0), pady=5, sticky="e")
        old_text_label = tk.Label(self.form_frame, text=feature_branch[0])
        old_text_label.grid(row=0, column=1, padx=(0, 0), pady=5, sticky="w")
        to_label = tk.Label(self.form_frame, text="To: ")
        to_label.grid(row=1, column=0, padx=(5, 0), pady=5, sticky="e")


        self.changed_text = tk.StringVar(None)
        self.changed_text.set(feature_branch[0])

        new_text_entry = tk.Entry(self.form_frame,
                                     textvariable=self.changed_text, 
                                     justify="left")
        new_text_entry.grid(row=1, column=1, 
                               padx=(2, 5), pady=5, 
                               sticky="ew")
        new_text_entry.bind('<Control-a>', self.select_all)


        # Cancel button
        cancel_btn = tk.Button(self.form_frame, text='Cancel', 
                               command=self.cancel)
        cancel_btn.grid(row=6, column=0, padx=4, pady=4, sticky="sew")
        self.top.bind("<Escape>", self.cancel)

        # Save button
        save_btn = tk.Button(self.form_frame, text='Rename Entry', 
                               command=self.rename_feature)
        save_btn.grid(row=6, column=1,
                          columnspan=1,
                          padx=4, pady=4, 
                          sticky="sew")
        # Delete button
        delete_btn = tk.Button(self.form_frame, text='Delete Entry', 
                               command=self.remove_feature)
        delete_btn.grid(row=6, column=2,
                          columnspan=1,
                          padx=4, pady=4, 
                          sticky="sew")
        self.form_frame.grid(row=0, column=0, 
                        padx=0, pady=0, 
                        sticky="nsew")

    def select_all(self, event):
        # select text
        try:
            event.widget.select_range(0, 'end')
        except:
            print(traceback.format_exc())
            event.widget.tag_add("sel", "1.0", "end")

        # move cursor to the end
        try:
            event.widget.icursor('end')
        except:
            print(traceback.format_exc())
            event.widget.mark_set("insert", "end")

        #stop propagation
        return 'break'
        
    def rename_feature(self):
        self.parent.modify_feature_across_dataset(self.target_branch, self.changed_text.get(), False)
        self.close()
        
    def remove_feature(self):
        answer = askyesno(title='confirmation',
        message='Are you sure that you want to delete "' + self.target_branch[0] + '" ?')
        if not answer:
            return
        self.parent.modify_feature_across_dataset(self.target_branch, self.changed_text.get(), True)
        self.close()

    def cancel(self, event = None):
        self.close()
        return "break"

    def close(self):
        self.top.grab_release()
        self.top.destroy()
        return "break"

class interrogator_settings(object):
    def __init__(self,io_pick,wd14_set, clip_set):
        self.interrogator_options_pick = 0

        self.wd14_settings = wd14_set
        self.clip_settings = clip_set
        
class interrogator_wd14_settings(object):
    def __init__(self, jsondata = None):
        self.model_wd14_pick = ""
        self.general_threshold = 0.35
        if(jsondata):
            for key in jsondata:
                setattr(self, key, jsondata[key])
        

class interrogator_clip_settings(object):
    def __init__(self, jsondata = None):

        self.model_clip_pick = "ViT-L-14/openai"
        self.model_blip_pick = "base"
        self.mode = "best"
        if(jsondata):
            for key in jsondata:
                setattr(self, key, jsondata[key])

class interrogator_window(object):
    def __init__(self, parent):

        self.correction_presets_path = "./appdata/"
        self.interrogator_options = ["WD14", "Clip"]
        self.models_wd14 = ["wd14-convnextv2-v2",
                                "wd14-vit-v2-git",
                                "wd14-swinv2-v2"]
        self.models_clip = ci_ext.get_models()
        self.models_blip = ["base","large"]
        self.clip_modes = ["best","caption","classic","fast","negative"]
        self.parent = parent
        self.settings = parent.settings.interrogator_settings
        self.create_ui()

    def create_ui(self):
        self.top = tk.Toplevel(self.parent)
        self.top.title("Generate Automatic Tags...")
        self.top.wait_visibility()
        self.top.grab_set()
        self.top.rowconfigure(0, weight=1)
        self.top.columnconfigure(0, weight=1)
        self.top.minsize(600, 400)
        self.top.transient(self.parent)

        self.form_frame = tk.Frame(self.top, 
                                   borderwidth=2,
                                   relief='raised',)
        self.form_frame.grid(row=0, column=0, 
                        padx=0, pady=0, 
                        sticky="nsew")
        
        self.form_frame.rowconfigure(1, weight=1)
        self.form_frame.columnconfigure(0, weight=1)

        self.controls_box_top = tk.Frame(self.form_frame, borderwidth=2,relief='flat')#,text="controls")
        #self.controls_box.grid(row=0,column=0, padx=2, pady=1, sticky="nsew")
        self.controls_box_top.grid(row=0,column=0, padx=5, pady=0, sticky="nsew")

        self.controls_box_top.columnconfigure(0, minsize=10)


        interrogator_label = tk.Label(self.controls_box_top,text= "Interrogator:",justify="right")
        interrogator_label.grid(row=0, column= 1, padx=5, pady=2, sticky="nsew")

        self.interrogator_option_text = tk.StringVar(self.controls_box_top)
        self.interrogator_option_text.set("") # default value
        self.interrogator_option_text.trace_add('write',self.change_interrogator)

        self.interrogator_options_dropdown = ttk.Combobox(self.controls_box_top, textvariable= self.interrogator_option_text,width=10)
        self.interrogator_options_dropdown.grid(row=0, column=2, padx=4, pady=4, sticky="nsew")
        self.interrogator_options_dropdown ['values']= self.interrogator_options
        self.interrogator_options_dropdown ['state']= 'readonly'
        self.interrogator_options_dropdown.current(self.settings.interrogator_options_pick)

        self.create_clip_panel()
        self.create_wd_panel()

        self.controls_box_bottom = tk.Frame(self.form_frame, borderwidth=2,relief='groove')#,text="controls")
        #self.controls_box.grid(row=0,column=0, padx=2, pady=1, sticky="nsew")
        self.controls_box_bottom.grid(row=2,column=0, padx=0, pady=0, sticky="nsew")
        self.controls_box_item_count = 0
        #self.controls_box_bottom.rowconfigure(1, weight=1)

        # Cancel button
        cancel_btn = tk.Button(self.controls_box_bottom, text='Cancel', command=self.cancel)
        #cancel_btn.grid(row=0, column=0, padx=4, pady=4, sticky="sew")
        cancel_btn.pack(fill= "x", side= "left",expand= False,anchor= "w")
        # Accept button
        accept_btn = tk.Button(self.controls_box_bottom, text='Accept', command=self.cancel)
        accept_btn.pack(fill= "x", side= "left",expand= False,anchor= "w")
        #accept_btn.grid(row=0, column=1, padx=4, pady=4, sticky="sew")
        # Import button
        import_btn = tk.Button(self.controls_box_bottom, text='Import Automatic Tags', command=self.parent.update_ui_automatic_tags)
        import_btn.pack(fill= "x", side= "right",expand= False,anchor= "e")
        #cancel_btn.grid(row=0, column=3, padx=4, pady=4, sticky="sew")
        # Import to set button
        import_all_btn = tk.Button(self.controls_box_bottom, text='Import Automatic Tags to Dataset', command=self.cancel)
        import_all_btn.pack(fill= "x", side= "right",expand= False,anchor= "e")
        #accept_btn.grid(row=0, column=4, padx=4, pady=4, sticky="sew")

        self.change_interrogator()

    def create_clip_panel(self):
        self.clip_settings_box = tk.LabelFrame(self.form_frame, 
                        text= "Clip settings",
                        borderwidth=4,
                        relief='sunken',)
        self.clip_settings_box.grid(row=1, column=0, 
                        padx=0, pady=2, 
                        sticky="nsew")
        self.clip_settings_box.columnconfigure(0, minsize=15)
        self.clip_settings_box.rowconfigure(0, minsize=15)

        rowcount = 1

        model_label = tk.Label(self.clip_settings_box,text= "Model:",justify="left")
        model_label.grid(row=rowcount, column=1, padx=5, pady=5, sticky="nsew")

        self.ci_model_text = tk.StringVar(self.clip_settings_box)
        self.ci_model_text.set(str(self.settings.clip_settings.model_clip_pick)) # default value
        self.ci_model_text.trace_add('write',self.change_model)

        self.ci_model_dropdown = ttk.Combobox(self.clip_settings_box, textvariable= self.ci_model_text,width=50)
        self.ci_model_dropdown.grid(row=rowcount, column=2, padx=5, pady=5, sticky="nsew")
        self.ci_model_dropdown ['values']= self.models_clip
        self.ci_model_dropdown ['state']= 'readonly'
        self.ci_model_dropdown.set(self.settings.clip_settings.model_clip_pick)
        rowcount+=1

        blip_model_label = tk.Label(self.clip_settings_box,text= "Blip Model Type:",justify="left")
        blip_model_label.grid(row=rowcount, column=1, padx=5, pady=5, sticky="nsew")

        self.blip_model_text = tk.StringVar(self.clip_settings_box)
        self.blip_model_text.set(str(self.settings.clip_settings.model_blip_pick)) # default value
        self.blip_model_text.trace_add('write',self.change_model)

        self.blip_model_dropdown = ttk.Combobox(self.clip_settings_box, textvariable= self.blip_model_text,width=50)
        self.blip_model_dropdown.grid(row=rowcount, column=2, padx=5, pady=5, sticky="nsew")
        self.blip_model_dropdown ['values']= self.models_blip
        self.blip_model_dropdown ['state']= 'readonly'
        self.blip_model_dropdown.set(self.settings.clip_settings.model_blip_pick)
        rowcount+=1

        mode_label = tk.Label(self.clip_settings_box,text= "Mode:",justify="left")
        mode_label.grid(row=rowcount, column=1, padx=5, pady=5, sticky="nsew")

        self.ci_mode_text = tk.StringVar(self.clip_settings_box)
        self.ci_mode_text.set(str(self.settings.clip_settings.mode)) # default value
        self.ci_mode_text.trace_add('write',self.change_clip_mode)

        self.ci_mode_dropdown = ttk.Combobox(self.clip_settings_box, textvariable= self.ci_mode_text,width=50)
        self.ci_mode_dropdown.grid(row=rowcount, column=2, padx=5, pady=5, sticky="nsew")
        self.ci_mode_dropdown ['values']= self.clip_modes
        self.ci_mode_dropdown ['state']= 'readonly'
        self.ci_mode_dropdown.set(self.settings.clip_settings.mode)
    
    def create_wd_panel(self):
        self.wd14_settings_box = tk.LabelFrame(self.form_frame, 
                        text= "WD14 settings",
                        borderwidth=4,
                        relief='sunken',)
        self.wd14_settings_box.grid(row=1, column=0, padx=5, pady=5,sticky="nsew")
        self.wd14_settings_box.columnconfigure(0, minsize=15)
        
        model_label = tk.Label(self.wd14_settings_box,text= "Model:",justify="left")
        model_label.grid(row=0, column=1, padx=5, pady=20, sticky="nsew")

        self.wd_model_text = tk.StringVar(self.wd14_settings_box)
        self.wd_model_text.set(str(self.settings.wd14_settings.model_wd14_pick)) # default value
        self.wd_model_text.trace_add('write',self.change_model)

        self.wd_model_dropdown = ttk.Combobox(self.wd14_settings_box, textvariable= self.wd_model_text,width=25)
        self.wd_model_dropdown.grid(row=0, column=2, padx=5, pady=20, sticky="nsew")
        self.wd_model_dropdown ['values']= self.models_wd14
        self.wd_model_dropdown ['state']= 'readonly'
        self.wd_model_dropdown.set(self.settings.wd14_settings.model_wd14_pick)

    def change_interrogator(self,*arg):
        print("change inter " + str(self.interrogator_options_dropdown.current()))
        self.settings.interrogator_options_pick = self.interrogator_options_dropdown.current()
        
        if(self.settings.interrogator_options_pick == 0):
            print("change inter 0")
            self.wd14_settings_box.grid(row=1, column=0, padx=5, pady=5,sticky="nsew")
            self.clip_settings_box.grid_forget()
        elif(self.settings.interrogator_options_pick == 1):
            print("change inter 1")
            self.clip_settings_box.grid(row=1, column=0, padx=5, pady=5,sticky="nsew")
            self.wd14_settings_box.grid_forget()
       # self.interrogator_model_text.set(str(self.settings.interrogator_model_pick))

    def change_model(self,*arg):
        if(self.settings.interrogator_options_pick == 0):
            self.settings.wd14_settings.model_wd14_pick = self.wd_model_text.get()
        elif(self.settings.interrogator_options_pick == 1):
            self.settings.clip_settings.model_clip_pick = self.ci_model_text.get()

    def change_blip_model(self,*arg):
            self.settings.clip_settings.model_blip_pick = self.blip_model_text.get()

    def change_clip_mode(self,*arg):
        self.settings.clip_settings.mode = self.ci_mode_text.get()
        print("changed clip mode to: " + str(self.settings.clip_settings.mode))

    def cancel(self, event = None):
        self.close()
        return "break"

    def close(self):
        self.top.grab_release()
        self.top.destroy()
        return "break"
    

class automatic_tags_editor(object):
    def __init__(self, main_editor):
        self.correction_presets_path = "./appdata/atc_presets"
        self.correction_presets =  ["default"]
        self.selected_preset = "None"
        self.correction_entries = []
        self.main_editor = main_editor
        self.load_correction_presets()

    def load_correction_presets(self):
        files = list(pathlib.Path(dirname(__file__) + self.correction_presets_path).rglob("*"))
        self.correction_presets = [
            f for f in files if splitext(f)[1] == ".json"]
        if (len(self.correction_presets) == 0):
            self.correction_presets =  ["default"]

    def apply_corrections(self, file):

        item = self.main_editor.get_item_from_file(file)
        auto_tags = item["automatic_tags"].split(", ")
        altered = False
        to_ui = False
        for correction in self.correction_entries:
            if(correction.condition.get() == "" or correction.condition.get() in auto_tags):
                replace = correction.replacement_text.get()
                for i in range(0,len(auto_tags)):
                    if(correction.target_tag.get() == auto_tags[i]):
                        auto_tags[i] = auto_tags[i].replace(correction.target_tag.get(), replace)
                        altered = True
                        #print(correction.target_tag.get() + " replaced in " + basename(file))
        if(altered):
            item["automatic_tags"] = ", ".join([x for x in auto_tags if x])
            self.main_editor.write_item_to_file(
            item,
            splitext(file)[0] + ".json")
            print("Modified " + basename(file))
            if(self.main_editor.file_index == self.main_editor.image_files.index(file)):
                to_ui = True
        if(to_ui):
                self.main_editor.automatic_tags_textbox.delete("1.0", "end")
                self.main_editor.automatic_tags_textbox.insert("end",", ".join([x for x in auto_tags if x]))


    def apply_corrections_to_set(self):

        for file in self.main_editor.image_files:
            self.apply_corrections(file)
            
class tag_replacement_entry(object):
    def __init__(self, target_tag,replacement_text,condition = ""):
        self.target_tag = tk.StringVar(None,target_tag)
        self.replacement_text = tk.StringVar(None,replacement_text)
        self.condition = tk.StringVar(None,condition)

class automatic_tags_editor_window(object):
    def __init__(self, parent, auto_tags_editor):
        self.parent = parent
        self.auto_tags_editor = auto_tags_editor
        self.create_ui()
    
    def create_ui(self):

        self.ui_entries = []
        self.entries_startRow = 1
        self.top = tk.Toplevel(self.parent)
        self.top.title("Automated Tags Editor")
        self.top.wm_minsize(418, 500)
        self.top.wm_maxsize(418,800)
        self.top.wm_resizable(False,True)
        self.top.transient(self.parent)
        self.top.wm_protocol("WM_DELETE_WINDOW", self.on_close)
        self.form_frame = tk.Frame(self.top, 
                                   borderwidth=2,
                                   relief='flat',)   
        self.form_frame.rowconfigure(1, weight=1)


        self.controls_box = tk.Frame(self.form_frame, 
                                   borderwidth=2,
                                   relief='flat',)
        self.controls_box.grid(row=0,column=0, padx=(5, 5), pady=5, sticky="nsew")
        self.controls_box.columnconfigure(tuple(range(10)), weight=0)
        self.controls_box.columnconfigure(tuple(range(3)), weight=1)


        self.selected_preset_name = tk.StringVar(self.controls_box)
        self.selected_preset_name.set(splitext(basename(self.auto_tags_editor.selected_preset))[0]) # default value
        self.selected_preset_name.trace_add('write',self.preset_changed_callback)
        self.preset_dropdown = tk.OptionMenu(self.controls_box, self.selected_preset_name, *self.auto_tags_editor.correction_presets, command = self.preset_changed_callback)
        self.preset_dropdown.grid(row=0, column=0, padx=4, pady=4, sticky="nsew")
        self.load_presets_options()


        new_preset_btn = tk.Button(self.controls_box, text='New Preset', 
                               command=self.create_preset)
        new_preset_btn.grid(row=0, column=1, padx=4, pady=4, sticky="nsew")

        save_btn = tk.Button(self.controls_box, text='Save', 
                               command=self.save_preset)
        save_btn.grid(row=1, column=0, padx=4, pady=4, sticky="nsew")


        self.add_entry_btn = tk.Button(self.controls_box, text='Add Entry', 
                               command=self.add_entry)
        self.add_entry_btn.grid(row=1, column=1, padx=4, pady=4, sticky="nsew")

        self.entries_box = tk.Frame(self.form_frame, 
                                   borderwidth=2,
                                   relief='sunken',)
        self.entries_box.grid(row=1, column=0, padx=(5, 5), pady=5, sticky="nsew")


        self.controls_box_bottom = tk.Frame(self.form_frame, 
                                   borderwidth=2,
                                   relief='flat',)
        self.controls_box_bottom.grid(row=2, column=0, padx=(5, 5), pady=5, sticky="nsew")


        apply_btn = tk.Button(self.controls_box_bottom, text='Apply', 
                               command=self.apply_corrections)
        apply_btn.grid(row=0, column=0, padx=4, pady=4, sticky="nsew")
        apply_btn = tk.Button(self.controls_box_bottom, text='Apply to dataset', 
                               command=self.apply_corrections_to_set)
        apply_btn.grid(row=0, column=1, padx=4, pady=4, sticky="nsew")

        self.scroll_frame = ScrollableFrame(self.entries_box)

        for entry in self.auto_tags_editor.correction_entries:
            self.add_ui_entry(entry)

        self.scroll_frame.pack(expand=True, fill="both")
        self.form_frame.pack(expand=True, fill="both")

    def apply_corrections(self):
        self.auto_tags_editor.apply_corrections(self.parent.image_files[self.parent.file_index])
    def apply_corrections_to_set(self):
        self.auto_tags_editor.apply_corrections_to_set()
    def add_entry(self,tag = "tag", replacement = "", condition = ""):
        entry = tag_replacement_entry(tag,replacement,condition)
        self.auto_tags_editor.correction_entries.append(entry)
        self.add_ui_entry(entry)

    def add_ui_entry(self, entry):
        ui_entry = tag_replacement_ui_entry(entry,self.scroll_frame.scrollable_frame,self,self.entries_startRow + len(self.ui_entries))
        self.ui_entries.append(ui_entry)


    def remove_entry(self, ui_entry, order = True):
        self.auto_tags_editor.correction_entries.remove(ui_entry.target_entry)
        self.ui_entries.remove(ui_entry)
        ui_entry.delete_entry()
        if(order):
            self.order_entries()

    def clear_entries(self):
        for i in range(0, len(self.ui_entries)):
            self.ui_entries[i].delete_entry()
        self.auto_tags_editor.correction_entries.clear()
        self.ui_entries.clear()

    def order_entries(self):
        count = 0
        for entry in self.ui_entries:
            entry.set_row_index(self.entries_startRow + self.ui_entries.index(entry))



    def load_presets_options(self):
        self.preset_dropdown['menu'].delete(0, 'end')

        for opt in self.auto_tags_editor.correction_presets: 
            self.preset_dropdown['menu'].add_command(label=splitext(basename(opt))[0], command=tk._setit(self.selected_preset_name,splitext(basename(opt))[0]))

    def preset_changed_callback(self,*args):
        for preset_file in self.auto_tags_editor.correction_presets:
            if(splitext(basename(preset_file))[0] == self.selected_preset_name.get()):
                self.auto_tags_editor.selected_preset = preset_file
                self.load_preset(preset_file)
        
    def load_preset(self, preset_file):
        self.clear_entries()
        try:
            with open(preset_file) as f:
                json_item = json.load(f)
                for t in range(0,len(json_item["target_tags"])):
                    self.add_entry(json_item["target_tags"][t], json_item["replacements"][t], json_item["conditions"][t] if "conditions" in json_item else None)
        except FileNotFoundError:
            pass

    def create_preset(self):

        answer = simpledialog.askstring("Input", "Type preset name.",
                                parent=self.top)
        if answer is not None and len(answer) > 2:
            self.clear_entries()
            self.auto_tags_editor.selected_preset = "./appdata/atc_presets/" + answer + ".json"
            self.auto_tags_editor.correction_presets.append(self.auto_tags_editor.selected_preset)
            self.selected_preset_name.set(splitext(basename(self.auto_tags_editor.selected_preset))[0])
        else:
            print("Preset name needs at least 3 characters")

        self.load_presets_options()

        
    def save_preset(self):
        try:
            with open(self.auto_tags_editor.selected_preset, "w+") as f:

                tags = []
                replacements = []
                conditions = []
                for entry in self.auto_tags_editor.correction_entries:
                    tags.append(entry.target_tag.get())
                    replacements.append(entry.replacement_text.get())
                    conditions.append(entry.condition.get())
                dictionary = {
                    "target_tags": tags,
                    "replacements": replacements,
                    "conditions": conditions,
                }
                f.write(json.dumps(dictionary, indent=4,))
        except:
            showerror(parent=self.parent,
                      title="Couldn't save JSON",
                      message="Could not save JSON file")
            print(traceback.format_exc())

    def select_all(self, event):
        # select text
        try:
            event.widget.select_range(0, 'end')
        except:
            print(traceback.format_exc())
            event.widget.tag_add("sel", "1.0", "end")

        # move cursor to the end
        try:
            event.widget.icursor('end')
        except:
            print(traceback.format_exc())
            event.widget.mark_set("insert", "end")

        #stop propagation
        return 'break'
        

    def cancel(self, event = None):
        self.close()
        return "break"

    def close(self):
        self.on_close()
        #self.top.grab_release()
        self.top.destroy()
        return "break"
    def on_close(self):
        self.top.destroy()
        self.auto_tags_editor.main_editor.auto_tags_window = None

class tag_replacement_ui_entry(object):
    def __init__(self, entry,parent,parent_class,row):
        self.target_entry = entry
        self.parent_class = parent_class
        self.parent = parent
        self.row_index = row
        self.condition_visible = True
        self.create_ui()

    def create_ui(self):

        self.entry_frame = tk.Frame(self.parent, 
                                   borderwidth=2,
                                   relief='raised',)
        
        self.entry_frame.grid(row=self.row_index, column=0,padx=(1, 1), pady=2, sticky="nsew")


        self.count_label = tk.Label(self.entry_frame,text= "#" + str(self.row_index), width=4, font=('Calibri 10'))
        self.count_label.grid(row=0, column=0, 
                               padx=(1, 1), pady=2, 
                               sticky="nsew")
        self.target_tag_input = tk.Entry(self.entry_frame,
                                     textvariable= self.target_entry.target_tag, 
                                     justify="left")
        self.target_tag_input.grid(row=0, column=1, 
                               padx=(2, 2), pady=2, 
                               sticky="nsew")
        
        self.arrow = tk.Button(self.entry_frame, text= "←", 
                               command=self.toggle_condition, width=3, font=('Calibri 10'),relief = "raised")             
        self.arrow.grid(row=0, column=2, 
                               padx=(2, 2), pady=2, 
                               sticky="nsew")

        self.replace_with_input = tk.Entry(self.entry_frame,
                                     textvariable= self.target_entry.replacement_text, 
                                     justify="left")
        self.replace_with_input.grid(row=0, column=3, 
                               padx=(2, 2), pady=2, 
                               sticky="nsew")
        self.remove_btn = tk.Button(self.entry_frame, text= "🗑", 
                               command=self.delete_btn_callback, width=3, font=('Calibri 10'))
        self.remove_btn.grid(row=0, column=4, padx=4, pady=2, sticky="nsew")

        self.condition_text = tk.Label(self.entry_frame,
                                     text= "Condition:", 
                                     justify="left")
        self.condition_text.grid(row=1, column=1, 
                               padx=(2, 2), pady=2, 
                               sticky="nsew")

        self.condition_input = tk.Entry(self.entry_frame,
                                     textvariable= self.target_entry.condition, 
                                     justify="left")
        self.condition_input.grid(row=1, column=3, 
                               padx=(2, 2), pady=2, 
                               sticky="nsew") 
        
        if(self.target_entry.condition.get() == ""):
            self.condition_input.grid_forget()
            self.condition_text.grid_forget()
            self.arrow.configure(relief = "groove") 
            self.condition_visible = False

    def set_row_index(self, row):
        self.row_index = row
        self.entry_frame.grid(row=self.row_index)
        self.count_label.config(text= "#" + str(self.row_index))
    def delete_btn_callback(self):
        self.parent_class.remove_entry(self)
    def delete_entry(self):
        self.entry_frame.destroy()
    def toggle_condition(self):
        self.condition_visible = not self.condition_visible
        if(self.condition_visible):
            self.condition_input.grid(row=1, column=3, 
                               padx=(2, 2), pady=2, 
                               sticky="nsew")   
            self.condition_text.grid(row=1, column=1, 
                               padx=(2, 2), pady=2, 
                               sticky="nsew") 
            self.arrow.configure(relief = "raised")
        else:
            self.condition_input.grid_forget()
            self.condition_text.grid_forget()
            self.arrow.configure(relief = "groove") 

class title_feature_extractor(object):
    def __init__(self, main_editor):
        self.extraction_presets_path = "./appdata/tfe_presets"
        self.extraction_presets =  ["default"]
        self.selected_preset = "None"
        self.extraction_entries = []
        self.main_editor = main_editor
        self.load_extraction_presets()
    def load_extraction_presets(self):

        files = list(pathlib.Path(dirname(__file__) + self.extraction_presets_path).rglob("*"))
        self.extraction_presets = [
            f for f in files if splitext(f)[1] == ".json"]
        if (len(self.extraction_presets) == 0):
            self.extraction_presets =  ["default"]

    def apply_extractions_to_set(self):

        selected_entry = self.main_editor.file_index
        for file in self.main_editor.image_files:

            file_index = self.main_editor.image_files.index(file)
            self.main_editor.file_index = file_index
            self.main_editor.set_ui(file_index,None,True)
            self.apply_extraction(file)


                        
    def apply_extraction(self,file,set_ui = False):
        for extraction in self.extraction_entries:
            split_titles = list(filter(None, extraction.target_titles.get().split("\n")))
            for title in split_titles:
                if title in self.main_editor.get_item_from_ui()["title"]:
                    self.main_editor.feature_clicked(extraction.target_tag.get(),1)
                    self.main_editor.save_json()
                    print(extraction.target_tag.get() + " added to " + basename(file))
        if(set_ui):
            print("set ui")
            self.main_editor.build_checklist_from_features()

class title_feature_entry(object):
    def __init__(self, target_tag,target_titles = ""):
        self.target_tag = tk.StringVar(None,target_tag)
        self.target_titles = tk.StringVar(None,target_titles)

class title_feature_extractor_window(object):
    def __init__(self, parent, feature_extractor):
        self.parent = parent
        self.feature_extractor = feature_extractor
        self.create_ui()
    
    def create_ui(self):

        self.ui_entries = []
        self.entries_startRow = 1
        self.top = tk.Toplevel(self.parent)
        self.top.title("Title Feature Extraction")
        self.top.wm_minsize(420, 500)
        self.top.wm_maxsize(420,800)
        self.top.wm_resizable(True,True)
        self.top.transient(self.parent)
        self.top.wm_protocol("WM_DELETE_WINDOW", self.on_close)
        self.form_frame = tk.Frame(self.top, 
                                   borderwidth=2,
                                   relief='flat',)   
        self.form_frame.rowconfigure(1, weight=1)


        self.controls_box = tk.Frame(self.form_frame, 
                                   borderwidth=2,
                                   relief='flat',)
        self.controls_box.grid(row=0,column=0, padx=(5, 5), pady=5, sticky="nsew")
        self.controls_box.columnconfigure(tuple(range(5)), weight=0)
        self.controls_box.columnconfigure(tuple(range(3)), weight=1)


        self.selected_preset_name = tk.StringVar(self.controls_box)
        self.selected_preset_name.set(splitext(basename(self.feature_extractor.selected_preset))[0]) # default value
        self.selected_preset_name.trace_add('write',self.preset_changed_callback)
        self.preset_dropdown = tk.OptionMenu(self.controls_box, self.selected_preset_name, *self.feature_extractor.extraction_presets, command = self.preset_changed_callback)
        self.preset_dropdown.grid(row=0, column=0, padx=4, pady=4, sticky="nsew")
        self.load_presets_options()


        new_preset_btn = tk.Button(self.controls_box, text='New Preset', 
                               command=self.create_preset)
        
        new_preset_btn.grid(row=0, column=1, padx=4, pady=4, sticky="nsew")
        save_btn = tk.Button(self.controls_box, text='Save', 
                               command=self.save_preset)
        
        save_btn.grid(row=1, column=0, padx=4, pady=4, sticky="nsew")


        self.entries_box = tk.Frame(self.form_frame, 
                                   borderwidth=2,
                                   relief='sunken',)
        self.entries_box.grid(row=1, column=0, padx=(5, 5), pady=5, sticky="nsew")


        self.controls_box_bottom = tk.Frame(self.form_frame, 
                                   borderwidth=2,
                                   relief='flat',)
        self.controls_box_bottom.grid(row=2, column=0, padx=(5, 5), pady=5, sticky="nsew")


        apply_btn = tk.Button(self.controls_box_bottom, text='Apply', 
                               command=self.apply_extraction)
        apply_btn.grid(row=0, column=0, padx=4, pady=4, sticky="nsew")
        apply_btn = tk.Button(self.controls_box_bottom, text='Apply to dataset', 
                               command=self.apply_extractions_to_set)
        apply_btn.grid(row=0, column=1, padx=4, pady=4, sticky="nsew")

        self.scroll_frame = ScrollableFrame(self.entries_box)

        for entry in self.feature_extractor.extraction_entries:
            self.add_ui_entry(entry)

        self.scroll_frame.pack(expand=True, fill="both")
        self.form_frame.pack(expand=True, fill="both")

    def apply_extraction(self):
        self.feature_extractor.apply_extraction(self.parent.image_files[self.parent.file_index],True)
    def apply_extractions_to_set(self):
        self.feature_extractor.apply_extractions_to_set()
    def add_entry(self,feature,titles = ""):
        print(f"Add feature to title extractor {feature}")
        entry = title_feature_entry(feature,titles)
        self.feature_extractor.extraction_entries.append(entry)
        self.add_ui_entry(entry)

    def add_ui_entry(self, entry):
        ui_entry = title_feature_ui_entry(entry,self.scroll_frame.scrollable_frame,self,self.entries_startRow + len(self.ui_entries))
        self.ui_entries.append(ui_entry)


    def remove_entry(self, ui_entry, order = True):
        self.feature_extractor.extraction_entries.remove(ui_entry.target_entry)
        self.ui_entries.remove(ui_entry)
        ui_entry.delete_entry()


        if(order):
            self.order_entries()

    def clear_entries(self):
        for i in range(0, len(self.ui_entries)):
            self.ui_entries[i].delete_entry()
        self.feature_extractor.extraction_entries.clear()
        self.ui_entries.clear()

    def order_entries(self):
        count = 0
        for entry in self.ui_entries:
            entry.set_row_index(self.entries_startRow + self.ui_entries.index(entry))
            count += 1


    def load_presets_options(self):
        self.preset_dropdown['menu'].delete(0, 'end')

        for opt in self.feature_extractor.extraction_presets: 
            self.preset_dropdown['menu'].add_command(label=splitext(basename(opt))[0], command=tk._setit(self.selected_preset_name,splitext(basename(opt))[0]))

    def preset_changed_callback(self,*args):
        for preset_file in self.feature_extractor.extraction_presets:
            if(splitext(basename(preset_file))[0] == self.selected_preset_name.get()):
                self.feature_extractor.selected_preset = preset_file
                self.load_preset(preset_file)
        
    def load_preset(self, preset_file):
        self.clear_entries()
        #If available, parse JSON into fields
        try:
            with open(preset_file) as f:
                json_item = json.load(f)
                for t in range(0,len(json_item["features"])):

                    self.add_entry(json_item["features"][t], "\n".join(json_item["titles"][t]))
        except FileNotFoundError:
            pass

    def create_preset(self):

        answer = simpledialog.askstring("Input", "Type preset name.",
                                parent=self.top)
        if answer is not None and len(answer) > 2:
            self.clear_entries()
            self.feature_extractor.selected_preset = "./appdata/tfe_presets/" + answer + ".json"
            self.feature_extractor.extraction_presets.append(self.feature_extractor.selected_preset)
            self.selected_preset_name.set(splitext(basename(self.feature_extractor.selected_preset))[0])
        else:
            print("Preset name needs at least 3 characters")

        self.load_presets_options()

        
    def save_preset(self):
        try:
            with open(self.feature_extractor.selected_preset, "w+") as f:

                tags = []
                titles = []
                for entry in self.feature_extractor.extraction_entries:
                    #target_titles = entry.target_titles.get().split("\n")
                    target_titles = [term for term in  entry.target_titles.get().split('\n') if '\n' not in term and not len(term) == 0]
                    #target_titles = (x.replace("\n","") for x in entry.target_titles.get().split("\n"))
                    print(str(target_titles))
                    tags.append(entry.target_tag.get())
                    titles.append(target_titles)
                dictionary = {
                    "features": tags,
                    "titles": titles,
                }
                f.write(json.dumps(dictionary, indent=4,))
        except:
            showerror(parent=self.parent,
                      title="Couldn't save JSON",
                      message="Could not save JSON file")
            print(traceback.format_exc())

    def select_all(self, event):
        # select text
        try:
            event.widget.select_range(0, 'end')
        except:
            print(traceback.format_exc())
            event.widget.tag_add("sel", "1.0", "end")

        # move cursor to the end
        try:
            event.widget.icursor('end')
        except:
            print(traceback.format_exc())
            event.widget.mark_set("insert", "end")

        #stop propagation
        return 'break'
        

    def cancel(self, event = None):
        self.close()
        return "break"

    def close(self):
        self.on_close()
        #self.top.grab_release()
        return "break"
    def on_close(self):
        self.top.destroy()
        self.feature_extractor.main_editor.feature_extractor_window = None

class title_feature_ui_entry(object):
    def __init__(self, entry,parent,parent_class,row):
        self.target_entry = entry
        self.parent_class = parent_class
        self.parent = parent
        self.row_index = row
        self.condition_visible = True
        self.create_ui()

    def create_ui(self):

        self.entry_frame = tk.Frame(self.parent, 
                                   borderwidth=2,
                                   relief='raised',)
        
        self.entry_frame.grid(row=self.row_index, column=0,padx=(1, 1), pady=2, sticky="nsew")

        self.count_label = tk.Label(self.entry_frame,text= "#" + str(self.row_index), width=4, font=('Calibri 10'))
        self.count_label.grid(row=0, column=0, padx=(1, 1), pady=2, sticky="nsew")

        self.entry_count = tk.IntVar(self.entry_frame,0,"entries")
        self.entry_count_label = tk.Label(self.entry_frame,textvariable= self.entry_count, width=4, font=('Calibri 10'))
        self.entry_count_label.grid(row=1, column=0, padx=(1, 1), pady=2, sticky="nsew")

        self.target_tag = tk.Label(self.entry_frame,
                                     textvariable= self.target_entry.target_tag, 
                                     justify="left")
        self.target_tag.grid(row=0, column=1, 
                               padx=(4, 4), pady=2, 
                               sticky="nsw")
          
        self.arrow = tk.Button(self.entry_frame, text= "←⎘", 
                               command=self.get_title, width=3, font=('Calibri 10'),relief = "raised")             
        self.arrow.grid(row=1, column=4, 
                               padx=(2, 2), pady=2, 
                               sticky="nsew")
        

        self.text_area = scrolledtext.ScrolledText(self.entry_frame,wrap=tk.WORD,width=34, height=4)
        self.text_area.grid(row=1, column=1, pady=10, padx=2,columnspan= 3)

        self.text_area.insert(tk.INSERT,self.target_entry.target_titles.get())
        self.text_area.bind('<<Modified>>', self.title_input_modified) 
                      
        self.remove_btn = tk.Button(self.entry_frame, text= "🗑", 
                               command=self.delete_btn_callback, width=3, font=('Calibri 10'))
        self.remove_btn.grid(row=0, column=4, padx=4, pady=2, sticky="nsew")

    def title_input_modified(self, event): 

        input_text = event.widget.get("1.0", "end")
        event.widget.edit_modified(False)
        self.target_entry.target_titles.set(input_text)
        split_titles = list(filter(None, input_text.split("\n")))
        titles_count = len(split_titles)
        self.entry_count.set(titles_count)
        


    def set_row_index(self, row):
        self.row_index = row
        self.entry_frame.grid(row=self.row_index)
        self.count_label.config(text= "#" + str(self.row_index))
    def delete_btn_callback(self):
        self.parent_class.remove_entry(self)
    def delete_entry(self):
        self.entry_frame.destroy()
    def toggle_condition(self):
        self.condition_visible = not self.condition_visible
        if(self.condition_visible):
            self.condition_input.grid(row=1, column=3, 
                               padx=(2, 2), pady=2, 
                               sticky="nsew")   
            self.condition_text.grid(row=1, column=1, 
                               padx=(2, 2), pady=2, 
                               sticky="nsew") 
            self.arrow.configure(relief = "raised")
        else:
            self.condition_input.grid_forget()
            self.condition_text.grid_forget()
            self.arrow.configure(relief = "groove")  
    def get_title(self):
        grabbed_title = self.parent_class.feature_extractor.main_editor.title_var.get()
        if(not self.text_area.get("1.0", "end") == "\n"):
           grabbed_title = "\n" + grabbed_title
        self.text_area.insert(tk.INSERT,grabbed_title)

class ScrollableFrame(ttk.Frame):
    def __init__(self, container, *args, **kwargs):
        super().__init__(container, *args, **kwargs)
        canvas = tk.Canvas(self)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.scrollable_frame = ttk.Frame(canvas)
        self.scrollable_frame.columnconfigure(0, weight=1)
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )
        self.scrollable_frame.grid(row=0, column=0, padx=2, pady=2, sticky="nsew")

        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        #self.scrollable_frame.pack(side="top", fill="x")

class dataset_viewer(object):
    def __init__(self, parent):
        self.parent = parent
        self.selected_entries = []
        self.last_selected_entry = None
        self.thumb_resolution_choices_named = ["small","medium","large","xxl"]
        self.thumb_resolution_choices = [133,198,258,364]
        self.thumb_font_sizes = [9,10,11,12]
        self.thumb_resolution_pick = 0
        self.create_ui()

    def create_ui(self):
        
        
        self.ui_entries = []
        self.entries_startRow = 1
        self.top = tk.Toplevel(self.parent)
        self.top.title("Dataset Browser")
        self.top.wm_minsize(800, 600)
        self.top.wm_resizable(True,True)
        self.top.wm_protocol("WM_DELETE_WINDOW", self.on_close)
        self.form_frame = tk.Frame(self.top, 
                                   borderwidth=2,
                                   relief='flat',)   
        self.form_frame.rowconfigure(1, weight=1)
        self.form_frame.columnconfigure(0, weight=1)
        self.task_bar = tk.Frame(self.form_frame, borderwidth=2,relief='flat')#,text="controls")
        self.task_bar.grid(row=0,column=0, padx=2, pady=1, sticky="nsew")

        self.controls_box = tk.Frame(self.task_bar, borderwidth=2,relief='groove')#,text="controls")
        #self.controls_box.grid(row=0,column=0, padx=2, pady=1, sticky="nsew")
        self.controls_box.pack(side="left")
        self.controls_box_item_count = 0


        self.thumb_res_text = tk.StringVar(self.controls_box)
        self.thumb_res_text.set(str(self.thumb_resolution_choices_named[0])) # default value
        self.thumb_res_text.trace_add('write',self.change_tumb_resolution)

        self.target_tag = tk.Label(self.controls_box,
                                   text= "Thumbnail Size:",
                                    justify="right")
        self.target_tag.grid(row=0, column= self.controls_box_item_count, padx=4, pady=2, sticky="nsew")
        self.controls_box_item_count += 1

        self.thumb_res_dropdown = ttk.Combobox(self.controls_box, textvariable= self.thumb_res_text,width=8)
        self.thumb_res_dropdown.grid(row=0, column=self.controls_box_item_count, padx=4, pady=4, sticky="nsew")
        self.thumb_res_dropdown ['values']= self.thumb_resolution_choices_named
        self.thumb_res_dropdown ['state']= 'readonly'
        self.controls_box_item_count += 1

        # Button to hide selected images
        self.hide_selection_btn = tk.Button(self.controls_box, text= "Hide", 
                               command=self.hide_selection,
                               )
        self.hide_selection_btn.grid(row=0, column=self.controls_box_item_count, padx=4, pady=2, sticky="nsew")
        self.controls_box_item_count += 1
        self.form_frame.bind_all("<Control-h>", self.hide_selection)

        # Button to show all hidden images.
        self.show_hidden_btn = tk.Button(self.controls_box, text= "Show All", 
                               command=self.show_hidden,
                               )
        self.show_hidden_btn.grid(row=0, column=self.controls_box_item_count, padx=4, pady=2, sticky="nsew")
        self.form_frame.bind_all("<Alt-h>", self.show_hidden)
        self.controls_box_item_count += 1
        #self.search_text = tk.StringVar(None)
        #self.search_text.set("🔍")
        #self.search_bar = tk.Entry(self.controls_box,textvariable=self.search_text, justify="left")
        #self.search_bar.grid(row=0, column=0, padx=(0, 5), pady=5, sticky="ew")

        # checkbox to enable deselection guard
        self.controls_box_item_count += 1
        self.deselect_guard_var = tk.IntVar()
        self.deselect_guard_var.set(1)
        self.deselect_guard_checkbox = tk.Checkbutton(self.controls_box, text="Guard De-selection", variable=self.deselect_guard_var)
        self.deselect_guard_checkbox.grid(row=0, column=self.controls_box_item_count, padx=4, pady=2, sticky="nsew")

        self.controls_box_item_count += 1
        self.feature_filter_box = tk.Listbox(self.controls_box, selectmode=tk.MULTIPLE, width=40)
        filters, filter_hit_count = self.feature_index_filter()
        for _i, _filter in enumerate(filters):
            self.feature_filter_box.insert(_i, "%s (%d)" % (_filter, filter_hit_count[_filter]))
        self.feature_filter_box.grid(row=0, column=self.controls_box_item_count, padx=4, pady=2, sticky="nsew")

        self.controls_box_item_count += 1

        # when press feature filter apply button, capture current multi selection
        # and save its stringy form into self.feature_filter_selections list
        # then apply that to the dv
        def _capture_feature_filters_selection():
            # init this as empty, we'll write over it.
            self.feature_filter_selections = []

            selection = self.feature_filter_box.curselection()
            for _i in selection:
                selected_item = self.feature_filter_box.get(_i)
                self.feature_filter_selections.append(selected_item)

            self.apply_feature_filters(self.feature_filter_selections)

        self.feature_filter_apply = tk.Button(
            self.controls_box,
            text="Apply feature filters",
            command=_capture_feature_filters_selection
        )

        self.feature_filter_apply.grid(row=0, column=self.controls_box_item_count, padx=4, pady=2, sticky="nsew")

        self.controls_box_item_count += 1
        def _clear_feature_filters_selection():
            self.feature_filter_selections = []
            self.feature_filter_box.selection_clear(0, tk.END)

        self.feature_filter_clear = tk.Button(
            self.controls_box,
            text="Clear feature filters",
            command=_clear_feature_filters_selection,
        )
        self.feature_filter_clear.grid(row=0, column=self.controls_box_item_count, padx=4, pady=2, sticky="nsew")


        self.info_box = tk.Frame(self.task_bar, borderwidth=2,relief='groove')#,text="controls")
        #self.info_box.grid(row=0,column=1, padx=2, pady=1, sticky="nsew")
        self.info_box.pack(side="right")#,anchor= "e")

        self.info_box_item_count = 0

        self.selected_count_text = tk.StringVar(None)
        self.selected_count_text.set("Selected: 0/0")
        self.target_tag = tk.Label(self.info_box,
                                   #text= "Selected: 1/34",
                                    textvariable= self.selected_count_text, 
                                    justify="right")
        self.target_tag.grid(row=0, column= self.info_box_item_count, padx=4, pady=2, sticky="nsew")

        self.info_box_item_count += 1
        self.visible_count_text = tk.StringVar(None)
        self.visible_count_text.set("Visible: 0/0")
        self.visible_target_tag = tk.Label(self.info_box,
                                    textvariable= self.visible_count_text, 
                                    justify="right")
        self.visible_target_tag.grid(row=0, column=self.info_box_item_count, padx=4, pady=2, sticky="nsew")

        
        self.directory_frame = DynamicGrid(self.form_frame, width=500, height=200)
        self.directory_frame.grid(row=1, column=0, padx= 2, pady=2, sticky="nsew")
        self.open_dataset()
        self.directory_frame.text.bind("<Control-a>", self.toggle_select_all)

        self.form_frame.pack(expand=True, fill="both")


    def open_dataset(self):
        self.clear_entries()
        for index, file in enumerate(self.parent.image_files):
            self.add_ui_entry(file, index)

        self.update_selection_info()
        self.update_visible_info()

    def close_dataset(self):
        self.clear_entries()
        self.update_selection_info()

    def apply_feature_to_selection(self,iid,remove):
        selected_entry = self.parent.file_index
        for entry in self.selected_entries:
            self.apply_feature(iid,remove,entry)
        self.parent.set_ui(selected_entry)
        self.parent.file_index = selected_entry

    def apply_feature(self,iid,remove,entry):

        file_index = self.parent.image_files.index(entry.file)
        self.parent.file_index = file_index
        self.parent.set_ui(file_index,None,True)
        self.parent.feature_clicked(iid,remove)
        self.parent.save_json()
        print(iid + " {action} ".format(action="added to" if remove else "removed from")
               + basename(entry.file))

    def update_visible_info(self):
        visible_count = len(list(filter(lambda e: not e.hidden, self.ui_entries)))

        self.visible_count_text.set( "Visible: " +
            str(visible_count) +
            "/" +
            str(len(self.ui_entries))
        )

    def update_selection_info(self):
        self.selected_count_text.set( "Selected: " +
            str(len(self.selected_entries)) +
            "/" +
            str(len(self.ui_entries))
        )

    #region entry functions
    # awas: i'm not sure under what circumstances file parameter is optional to this method
    # can it ever be none?
    def add_ui_entry(self, file = None, index = None):
        box = self.directory_frame.add_box()
        ui_entry = dv_file_entry(box, self, file, index, self.thumb_resolution_choices[self.thumb_resolution_pick])
        self.ui_entries.append(ui_entry)

    def remove_entry(self, ui_entry, order = True):
        self.ui_entries.remove(ui_entry)
        ui_entry.delete_entry()

    def clear_entries(self):
        for i in range(0, len(self.ui_entries)):
            self.ui_entries[i].delete_entry()
        self.ui_entries.clear()

    def entry_right_clicked(self,entry):

        menu_options = []
        menu_options.append(context_menu_option_data("Delete", self.delete_file))
        menu_options.append(context_menu_option_data("Rename", self.rename_file))
        menu_options.append(context_menu_option_data("Debug State", partial(self.popup_registry_debug, entry)))
        menu_options.append(context_menu_option_data("test2", self.rename_file))
        menu_options.append(context_menu_option_data("test2", self.rename_file))
        menu_options.append(context_menu_option_data("test2", self.rename_file))
        menu_options.append(context_menu_option_data("test2", self.rename_file))
        menu_options.append(context_menu_option_data("test2", self.rename_file))
        menu_options.append(context_menu_option_data("test2", self.rename_file))
        menu_options.append(context_menu_option_data("test2", self.rename_file))
        menu_options.append(context_menu_option_data("test2", self.rename_file))
        menu_options.append(context_menu_option_data("test2", self.rename_file))

        self.parent.open_context_menu(self.top,menu_options)

    def entry_middle_clicked(self,entry):
        self.parent.save_unsaved_popup()
        file_index = self.parent.image_files.index(entry.file)
        self.parent.file_index = file_index
        self.parent.set_ui(file_index)
    
    def entry_clicked(self,entry):
        self.ctrl_pressed = False
        self.alt_pressed = False
        self.shift_pressed = False

        if(len(self.selected_entries) > 0):
            if(self.parent.ctrl_pressed):              
                if(entry.selected):
                    self.deselect_entry(entry)
                else:
                    self.select_entry(entry)
            elif(self.parent.shift_pressed and not self.last_selected_entry == None):
                self.shift_select(entry)
            else:

                # guard against clearing a large selection set if option selected
                # with dialogue confirmation, save misclick
                # from erroneously clearing a manually curated selectio set!
                answer_can_clear = True

                if self.deselect_guard_var.get():
                    if(len(self.selected_entries) > 1):
                        answer_can_clear = askyesno(
                            parent=self.top,
                            title='Replace multi-selection',
                            message='Multiple entries selected will be cleared by this action, Continue?'
                        )

                if answer_can_clear:
                    # todo: im not sure what this branch is for but harmless
                    if(entry.selected):
                        self.deselect_all_entries()
                        self.select_entry(entry)
                    else:
                        self.deselect_all_entries()
                        self.select_entry(entry)
        else:
            self.select_entry(entry)

        self.update_selection_info()

    def select_entry(self,entry):

        # do not select an entry if its image is hidden
        if entry.hidden:
            return

        self.last_selected_entry = entry
        self.selected_entries.append(entry)
        entry.select()

    def deselect_entry(self,entry):
        self.selected_entries.remove(entry)
        entry.deselect()

    def deselect_all_entries(self):
        print("deselect all")
        for entry in self.selected_entries:
            entry.deselect()
        self.selected_entries.clear()

    def select_all_entries(self):
        print("select all")
        #self.selected_entries.clear()
        for entry in self.ui_entries:
            if entry not in self.selected_entries:
                self.select_entry(entry)

    def toggle_select_all(self,event):
        print("toggle select all " +
              str(len(self.selected_entries)) +
               "/" + str(len(self.ui_entries)))
        
        if(len(self.selected_entries) == len(self.ui_entries)):
            self.deselect_all_entries()
        else:
            self.select_all_entries()
        self.update_selection_info()


    # walk feature_index to see what our unique category -> feature combinations are
    # then render them as a filtering thingy? think this through ok
    def feature_index_filter(self):

        _hit_count = {}
        filters = []
        for cat, descs in self.parent.feature_index.items():
            for desc in descs.keys():
                _key = "→".join((cat, desc))

                # track how many files match this permutation
                if _key not in _hit_count:
                    _hit_count[_key] = set()
                _hit_count[_key].update(descs[desc])

                filters.append(_key)

        # aggregate hit_counts
        hit_count = {}
        for _key in _hit_count:
            hit_count[_key] = len(_hit_count[_key])

        return filters, hit_count

    def popup_registry_debug(self, entry):

        #__import__("IPython").embed()

        popup = tk.Tk()
        popup.wm_title("debug state view")
        popup.geometry("500x300")
        _msg = pformat(json.dumps(self.parent.shadow_registry[entry.index]), width=80, sort_dicts=False)
        label = ttk.Label(popup, text=_msg)
        label.place(relx=.5, rely=.5, anchor="center")

    
    def shift_select(self,entry):
        if(self.ui_entries.index(self.last_selected_entry) < self.ui_entries.index(entry)):
            from_index = self.ui_entries.index(self.last_selected_entry)
            to_index = self.ui_entries.index(entry) + 1
        else:
            from_index = self.ui_entries.index(entry)
            to_index = self.ui_entries.index(self.last_selected_entry)

        for i in range(from_index, to_index):
            self.select_entry(self.ui_entries[i])

    def delete_file(self):
        print("delete file test")
    def rename_file(self):
        print("rename file test")
    def update_entry_file(self, source_file, target_file):
        for entry in self.ui_entries:
            if(entry.file == source_file):
                entry.update_file(target_file)
    #endregion

    #region Controls

    def change_tumb_resolution(self,*arg):
        self.thumb_resolution_pick = self.thumb_res_dropdown.current()
        if self.thumb_resolution_pick > len(self.thumb_resolution_choices) - 1: self.thumb_resolution_pick = 0
        print("Tumbnail resoluton set to " + self.thumb_resolution_choices_named[self.thumb_resolution_pick])
        for entry in self.ui_entries:
            entry.set_thumb_size(self.thumb_resolution_choices[self.thumb_resolution_pick])
        #self.directory_frame.update_grid()

    def apply_feature_filters(self, filters_stringy):

        if not len(filters_stringy):
            return

        AND_entries = {}
        entries_to_display = set()
        for _sel in filters_stringy:

            # remove the hit count from the filter.
            # this is highly questionable design but eh.
            sel = re.sub('\s+\(\d+\)$', '', _sel)

            # track which entries passed for this filter
            AND_entries[sel] = set()

            cat, feature = sel.split("→")
            if not cat in self.parent.feature_index or not feature in self.parent.feature_index[cat]:
                raise ValueError("wtf, tried to filter on feature that isnt in index: cat %s feature %s" % (cat,feature))
            for entry in self.parent.feature_index[cat][feature]:

                # add to set of entries that passed *this* filter
                AND_entries[sel].add(entry)

                # add to set of entries that passed *any* filter
                entries_to_display.add(entry)


        # filter entries_to_display (which contains *all* matches currently) down 
        # to only entries that matched in every individual filter.
        # so an AND logic
        for ss in AND_entries.values():
            entries_to_display.intersection_update(ss)

        # walk every entry and hide those that arent in entries_to_display
        for entry in self.ui_entries:
            if entry.index not in entries_to_display:
                entry.hide_image(True)

        self.update_visible_info()

    def hide_selection(self,event=None):    
        for entry in self.selected_entries:
            entry.hide_image(True)

        self.update_visible_info()

    def show_hidden(self,event=None):    
        for entry in self.ui_entries:
            entry.hide_image(False)
        
        self.update_visible_info()

    #endregion
    def on_close(self):
        self.top.destroy()
        self.parent.dataset_viewer_window = None
          
class dv_file_entry(object):
    def __init__(self, container, dv, file, index, size):
        self.parent = container
        self.dv = dv
        self.file = file
        self.index = index
        self.selected = False
        self.hidden = False
        self.size = size
        self.border = 2
        self.pad = 8
        self.create_image_frame()

    def create_image_frame(self):
        self.canvas = tk.Canvas(self.parent,bd= self.border,background= theme.color("entry"), relief="flat")
        self.canvas.grid(row=0,column=0,sticky="nswe")
        self.canvas.bind( "<ButtonRelease-1>", self.lm_button_Pressed )
        self.canvas.bind( "<ButtonRelease-2>", self.mm_button_Pressed )
        self.canvas.bind( "<ButtonRelease-3>", self.rm_button_pressed )

        # Display image in image_frame
        self.image = Image.open(self.file)
        self.framed_image = ImageTk.PhotoImage(self.image)


        self.canvas_image = self.canvas.create_image(self.size / 2, self.size, anchor="center",image=self.framed_image)
        self.canvas_text = self.canvas.create_text(self.size / 2 , self.size,  anchor= "n",text= splitext(basename(self.file))[0], width= 114,font=("Segoe_UI_Semibold 9"))

        self.set_thumb_size(self.size)
    
    def set_thumb_size(self,size):
        self.parent.configure(width = size + self.pad + (self.border * 2),height = size + 42 + self.pad + (self.border * 2))
        self.size = size
        self.image = Image.open(self.file)
        self.image.thumbnail((self.size,self.size), Image.LANCZOS)
        self.framed_image = ImageTk.PhotoImage(self.image)
        self.canvas.itemconfigure(self.canvas_image, image=self.framed_image)
        self.canvas.itemconfigure(self.canvas_text, width= self.size - 14,
                                   font=("Segoe_UI_Semibold " + str(self.dv.thumb_font_sizes[self.dv.thumb_resolution_pick])))
        self.canvas.coords(self.canvas_image, self.size / 2 + self.pad / 4,self.size / 2 + self.pad / 4)
        self.canvas.coords(self.canvas_text, self.size / 2 + self.pad / 4 ,self.size + self.pad / 4 + 5)
       #self.canvas.grid(row=0,column=0,sticky="nswe")
        self.canvas.configure(width = size,height = size + 42)

    def lm_button_Pressed( self, event ):
        self.dv.entry_clicked(self)
    def mm_button_Pressed( self, event ):
        self.dv.entry_middle_clicked(self)
    def rm_button_pressed( self, event ):
        self.dv.entry_right_clicked(self)
    def select(self):
        self.selected = True
        self.canvas.configure(background=theme.color("entry_selected"))#, relief="raised")

    def deselect(self):
        self.selected = False
        self.canvas.configure(background=theme.color("entry"))#,relief="flat")

    def hide_image(self, hide):
        self.hidden = hide
        if(not self.hidden):
            self.canvas.itemconfigure(self.canvas_image, state = "normal")
        else:
            self.canvas.itemconfigure(self.canvas_image, state = "hidden")

    def update_file(self,file):
        self.file = file
        self.image = Image.open(self.file)
        self.image.thumbnail((self.size,self.size), Image.LANCZOS)
        self.framed_image = ImageTk.PhotoImage(self.image)
        self.canvas.itemconfigure(self.canvas_image,  image=self.framed_image)

    def delete_btn_callback(self):
        self.dv.remove_entry(self)

    def delete_entry(self):
        self.parent.destroy()

class DynamicGrid(tk.Frame):
    def __init__(self, parent, *args, **kwargs):
        tk.Frame.__init__(self, parent, *args, **kwargs)

        self.mouse_in_frame = False

        self.text = tk.Text(self, wrap="word", borderwidth=0, highlightthickness=0,relief="flat",
                            state="disabled",cursor= "arrow",background= theme.color("background"),blockcursor= False,highlightcolor= theme.color("background"),highlightbackground=theme.color("background"))
        self.text.pack(side="left",fill="both", expand=True)
        self.boxes = []

        self.text.tag_unbind("SEL","<<Selection>>")
        self.text.bind_all("<MouseWheel>", self.on_mousewheel)
        self.text.bind("<Enter>", self.on_mouse_enter)
        self.text.bind("<Leave>", self.on_mouse_exit)
        self.text.bind("<<Selection>>", self.text_highlight_hack)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        scrollbar.pack(side="right", fill="y")
        #scrollbar.grid(row=1, column=1, padx=0, pady=0, sticky="nsw")
        self.text.configure(yscrollcommand=scrollbar.set)

        #Ugly workaround that deselects all highlighted chars in a text widget, which in this case are the file entries, so we don't want text highlighting...
    def text_highlight_hack(self, event = None):
        self.text.tag_remove("sel","1.0","end")

    def add_box(self, color=None):
        box = tk.Frame(self.text, bd=0, relief="flat",
                       width=256, height=256 + 42,background= theme.color("background")) #padx=20, pady=20)
        box.grid_propagate(False)
        self.boxes.append(box)
        self.text.configure(state="normal")
        self.text.window_create("end", window=box)
        self.text.configure(state="disabled")
        return box
    
    def update_grid(self):
        self.text.configure(state="normal")
        
        for box in self.boxes:
          self.text.window_configure(self.boxes.index(box) + 1, window=box)
          #self.text.window_create("end", window=box)
        self.text.configure(state="disabled")

    def on_mousewheel(self, event):
        if(self.mouse_in_frame):
            self.text.yview_scroll(int(-1*(event.delta/120)), "units")

    def on_mouse_enter(self,event):
        #print("mouse entered")
        self.mouse_in_frame = True
    def on_mouse_exit(self,event):
        #print("mouse exited")
        self.mouse_in_frame = False
    
class context_menu(object):
    def __init__(self,root,parent, menu_options):
        self.root = root
        self.parent = parent
        self.bind_id_focus = self.parent.bind("<FocusOut>", self.on_focus_out)
        self.menu_options = menu_options
        self.create_ui()

    def create_ui(self):
        self.height = 320
        self.entry_height = 24
        self.top = tk.Toplevel(self.parent)
        self.top.overrideredirect(1)
        self.top.minsize(200, self.height)
        self.top.maxsize(200, self.height)
        self.set_position()
        #self.top.title("Set items to get pasted...")
        self.top.wait_visibility()
        #self.top.grab_set()
        self.top.rowconfigure(0, weight=1)
        self.top.columnconfigure(0, weight=1)
        self.top.resizable(False,False)
        self.bind_id_focus_self = self.top.bind("<FocusOut>", self.on_focus_out_self)
        #self.top.transient(self.parent)
        #self.top.wm_protocol("WM_DELETE_WINDOW", self.on_close)

        self.form_frame = tk.Frame(self.top, 
                                   borderwidth=2,
                                   relief='flat',)   
        #self.form_frame.rowconfigure(0, weight=1)
        self.form_frame.columnconfigure(0, weight=1)
        
        self.option_entries = []
        self.option_count = 0
        #pixel = tk.PhotoImage(width=1, height=1)
        for option in self.menu_options:
            print("option added: " + option.text)
            option_btn = hla_button(self.form_frame, 
                            text= option.text, 
                            #image = pixel,
                            command= self.combineFunc(self.on_option_clicked,option.callback),
                            highlightbackground= "Grey28",
                            highlightcolor= "Grey28",
                            #height= self.entry_height,
                            #width= 200,
                            border= 0,
                            pady=2,
                            padx=5,
                            anchor= "w",
                            justify="left"
                            )
            option_btn.pack(fill= "x", side= "top",expand= False,anchor= "w")

            self.option_entries.append(option_btn)
            self.option_count +=1
        
        self.form_frame.pack(expand=False, fill="x")
        self.set_frame_height()

    def set_frame_height(self):
        self.height = 24 * len(self.option_entries) + 5
        self.top.minsize(200, self.height)
        self.top.maxsize(200, self.height)
        
    def set_position(self):
        x = self.parent.winfo_pointerx()
        y = self.parent.winfo_pointery()
        # abs_coord_x = self.parent.winfo_pointerx() - self.parent.winfo_rootx()
        # abs_coord_y = self.parent.winfo_pointery() - self.parent.winfo_rooty()
        self.top.geometry('%dx%d+%d+%d' % (self.top.winfo_width(), self.top.winfo_height(), x, y))

    def on_option_clicked(self):
        #caller = event.widget
        print("option clicked ")
        self.close()

    def combineFunc(self, *funcs):
       def combinedFunc(*args, **kwargs):
            for f in funcs:
                f(*args, **kwargs)
       return combinedFunc

    def pointer_inside_frame(self):
        frame_x = self.top.winfo_x()
        frame_y = self.top.winfo_y()
        frame_width = self.top.winfo_width()
        frame_height = self.top.winfo_height()

        pointer_x = self.top.winfo_pointerx()
        pointer_y = self.top.winfo_pointery()

        if frame_x <= pointer_x <= frame_x + frame_width and \
                frame_y <= pointer_y <= frame_y + frame_height:
            print("Pointer is inside the frame!")
            return True
        else:
            print("Pointer is outside the frame!")
            return False
    def handle_click(self):
        if(not self.pointer_inside_frame()):
            self.close()
    def on_focus_out(self, event = None):
        if(not self.pointer_inside_frame()):
            print("Parent out of focus")
            self.close()
    def on_focus_out_self(self, event = None):
        print("Context menu out of focus")
        self.close()
    def close(self):
        self.parent.unbind("<FocusOut>",self.bind_id_focus)
        self.root.context_menu = None
        self.top.destroy()
    
class context_menu_option_data(object):
    def __init__(self, text, callback ):
        self.text = text
        self.callback = callback

#Highlightable Button
class hla_button(tk.Button):
    def __init__(self, *args, **kwargs):
        tk.Button.__init__(self, *args, **kwargs)
        self.bind("<Enter>", self.on_mouse_enter)
        self.bind("<Leave>", self.on_mouse_exit)
    def on_mouse_enter(self,event):
        #print("mouse entered")
        self.configure(background= theme.color("entry_selected"))
        self.mouse_in_frame = True
    def on_mouse_exit(self,event):
        #print("mouse exited")
        self.configure(background= theme.color("entry"))
        self.mouse_in_frame = False

class ui_theme_manager(object):
    def __init__(self):
        #self.themes = {}
        self.current_theme = "dark"
        self.themes = {
            "default": { "background": "Grey75", "entry": "Grey75"},
             "dark": { "background": "Grey22", "entry": "Grey26","entry_selected": "chartreuse4","text": "Grey90","text_disabled": "Grey42"}
        }
        
        # self.themes.append(
        #     ui_theme("default",
        #     theme_entries = {
        #     "bg": "Grey75",
        #     "entry": "Grey75"
        # }))

        # self.themes.append(
        #     ui_theme("dark",
        #     theme_entries = {
        #     "bg": "Grey20",
        #     "entry": "Grey30"
        # }))
    def color(self,id):
        return self.themes[self.current_theme][id]

theme = ui_theme_manager()
    

class ui_theme(object):
    def __init__(self,name,theme_entries):
        self.name = name
        self.theme_entries = theme_entries


class window_save_state(object):
    def __init__(self,id,x,y,max = False):
        self.window_id = id
        self.pos_x = x
        self.pos_y = y
        self.maximized = max
        
    def to_json(self):
        return {
            'window_id': self.window_id,
            'pos_x': self.pos_x,
            'pos_y': self.pos_y,
            'maximized':  self.maximized
        }
        
class app_settings(object):
    def __init__(self,w_states: list[window_save_state],interrogator_set: interrogator_settings):
        self.window_states = w_states
        self.interrogator_settings = interrogator_set

    def to_json(self):
        return {
            'window_save_states': self.window_states,
            'interrogator_settings': jsonpickle.encode(self.interrogator_settings)
        }

    def from_json(self):
        print(self.interrogator_settings)
        self.interrogator_settings = jsonpickle.decode(self.interrogator_settings)
        print(self.interrogator_settings)
        return self

# the given message with a bouncing progress bar will appear for as long as func is running, returns same as if func was run normally
# a pb_length of None will result in the progress bar filling the window whose width is set by the length of msg
# Ex:  run_func_with_loading_popup(lambda: task('joe'), photo_img)  
def run_func_with_loading_popup(parent, func, msg, window_title = None, bounce_speed = 8, pb_length = None):
    func_return_l = []
    top = tk.Toplevel(parent)

    if isinstance(parent, lora_tag_helper):
        x = parent.winfo_x() + 50
        y = parent.winfo_y() + 50
    
        top.geometry(f"+{x}+{y}")

    
    
    class _main_frame(object):
        def __init__(self, top, window_title, bounce_speed, pb_length):
            self.done = False
            self.func = func
            # save root reference
            self.top = top
            # set title bar
            self.top.title(window_title)

            self.bounce_speed = bounce_speed
            self.pb_length = pb_length

            self.msg_lbl = tk.Label(top, text=msg)
            self.msg_lbl.pack(padx = 10, pady = 5)

            # the progress bar will be referenced in the "bar handling" and "work" threads
            self.load_bar = tk.ttk.Progressbar(top)
            self.load_bar.pack(padx = 10, pady = (0,10))
            
            self.bar_init()


        def bar_init(self):
            # first layer of isolation, note var being passed along to the self.start_bar function
            # target is the function being started on a new thread, so the "bar handler" thread
            self.start_bar_thread = threading.Thread(target=self.start_bar, args=())
            # start the bar handling thread
            self.start_bar_thread.start()

        def start_bar(self):
            try:
                # the load_bar needs to be configured for indeterminate amount of bouncing
                self.load_bar.config(mode='indeterminate', maximum=100, value=0, length = self.pb_length)
                # 8 here is for speed of bounce
                self.load_bar.start(self.bounce_speed)            
    #             self.load_bar.start(8)            

                self.work_thread = threading.Thread(target=self.work_task, args=())
                self.work_thread.start()

                # close the work thread
                self.work_thread.join()

                self.done = True
                self.top.destroy()
    #             # stop the indeterminate bouncing
    #             self.load_bar.stop()
    #             # reconfigure the bar so it appears reset
    #             self.load_bar.config(value=0, maximum=0)
            except:
                print(traceback.format_exc())
        def work_task(self):
            func_return_l.append(func())

    # call Main_Frame class with reference to root as top
    frame = _main_frame(top, window_title, bounce_speed, pb_length)
    parent.update()
    if not frame.done:
        parent.wait_window(top)
    parent.update()
    if len(func_return_l) == 1:
        return func_return_l[0]
    else:
        return func_return_l


#Application class
class lora_tag_helper(TkinterDnD.Tk):

    #Constructor
    def __init__(self):
        super().__init__()

        self.image_width = 1
        self.image_height = 1
        self.image_handle = None
        self.crop_left_area = None
        self.crop_top_area = None
        self.crop_right_area = None
        self.crop_bottom_area = None
        self.already_initialized = False
        self.image_files = []
        self.file_index = 0
        self.stored_item = []
        self.l_pct = 0
        self.t_pct = 0
        self.r_pct = 1
        self.b_pct = 1
        self.feature_count = 0
        self.features = []
        self.icon_image = Image.open("icon.png")
        self.ctrl_pressed = False
        self.alt_pressed = False
        self.shift_pressed = False
        self.prompt = ""
        self.feature_checklist = []
        self.use_full_checklist = False
        self.treeview_unfold_state = {}
        self.geometry("1200x600")
        self.auto_tags_editor = automatic_tags_editor(self)
        self.auto_tags_window = None
        self.interrogator_win = None
        self.feature_extractor = title_feature_extractor(self)
        self.feature_extractor_window = None
        self.dataset_viewer_window = None
        self.context_menu = None
        self.paste_set = paste_settings()
        self.logo_remover = Logo_Removal.logo_removal_tool()
        self.settings = self.load_app_settings()
        self.events = Events()
        self.create_ui()
        self.wm_protocol("WM_DELETE_WINDOW", self.quit)
        self.listener = pynput.keyboard.Listener(
            on_press=self.on_press,
            on_release=self.on_release)
        self.listener.start()
        self.update()
        self.after(1000, self.import_reqs)

        # awas
        # prototype of shadow copy of data contained in each image_files json
        # this will need synchronisation and such, think about that.
        self.shadow_registry = []
        self.feature_index = {}

    def import_reqs(self, event = None):
        try:
            if not self.already_initialized and (event is None or event.widget is not self):
                self.already_initialized = True
                run_func_with_loading_popup(
                        self,
                        lambda: import_interrogators(), 
                        "Importing Interrogator Requirements...", 
                        "Importing Interrogator Requirements...")
                run_func_with_loading_popup(
                        self,
                        lambda: import_tokenizer_reqs(),
                        "Importing Tokenizer Requirements...", 
                        "Importing Tokenizer Requirements...")
        except:
            print(traceback.format_exc())
    #Create all UI elements
    def create_ui(self):
        # Set window info
        self.iconphoto(self, tk.PhotoImage(file="icon_256.png")) 
        self.title("LoRA Tag Helper")

        self.create_menu()
        self.create_primary_frame()

        self.drop_target_register(DND_FILES)
        self.dnd_bind('<<Drop>>', self.handle_drop)

    def handle_drop(self, event):
        str_file = event.data
        try:
            if str_file and str_file[0] == "{" and str_file[-1]== "}":
                str_file = str_file[1:-1]
        except:
            pass                
        file = pathlib.Path(str_file)
        if len(self.image_files) > 0:
            self.go_to_image(None, file)
        elif file.is_dir():
            self.open_dataset(None, file)

    def handle_click(self,event = None):
        if(not self.context_menu == None):
            self.context_menu.handle_click()
    #Create primary frame
    def create_primary_frame(self):
        self.root_frame = tk.Frame(self)
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.minsize(500, 670)
        self.root_frame.grid(padx=0, pady=0, sticky="nsew")
        self.root_frame.rowconfigure(0, weight = 1)
        self.root_frame.columnconfigure(0, weight = 2)
        self.root_frame.columnconfigure(1, weight = 0)
        self.root_frame.columnconfigure(1, minsize=600)
        self.root_frame.bind_all("<Button-1>", self.handle_click,"+" )
        self.root_frame.bind_all("<Button-2>", self.handle_click,"+" )
        self.root_frame.bind_all("<Button-3>", self.handle_click,"+" )
        self.create_image_frame()
        self.create_form_frame()
        self.create_initial_frame()
        self.statusbar_text = tk.StringVar()
        self.statusbar = tk.Label(self, 
                                  textvar=self.statusbar_text, 
                                  bd=1, 
                                  relief=tk.RAISED, 
                                  anchor=tk.W)
        self.statusbar.grid(row=1, column=0, sticky="ew")

    # Create main menu bar
    def create_menu(self):
        menu_bar = tk.Menu(self)
        file_menu = tk.Menu(menu_bar, tearoff=0)

        file_menu.add_command(label="Open dataset...", 
                              command=self.open_dataset, 
                              underline=0, 
                              accelerator="Ctrl+O")
        self.bind("<Control-o>", self.open_dataset)

        file_menu.add_command(label="Reset this image to defaults...", 
                              command=self.reset, 
                              underline=0, 
                              accelerator="Ctrl+Shift+R")
        self.bind("<Control-R>", self.reset)

        file_menu.add_command(label="Dataset Browser...", 
                              command=self.open_dataset_viewer, 
                              underline=10, 
                              accelerator="Ctrl+D")
        self.bind("<Control-d>", self.open_dataset_viewer)

        file_menu.add_command(label="Save as Default...", 
                              command=self.save_defaults, 
                              underline=0, 
                              accelerator="Ctrl+Shift+S")
        self.bind("<Control-S>", self.save_defaults)

        file_menu.add_command(label="Generate Lora subset...", 
                              command=self.generate_lora_subset, 
                              underline=10, 
                              accelerator="Ctrl+L")
        self.bind("<Control-l>", self.generate_lora_subset)

        file_menu.add_command(label="Interrogate all automatic tags...", 
                              command=self.update_all_automatic_tags, 
                              underline=10, 
                              accelerator="Ctrl+Shift+T")
        self.bind("<Control-T>", self.update_all_automatic_tags)

        file_menu.add_command(label="Interrogater settings...", 
                              command=self.open_interrogator, 
                              underline=10, 
                              accelerator="Ctrl+Shift+T")
        self.bind("<Control-i>", self.update_all_automatic_tags)

        file_menu.add_command(label="Automatic Tags Editor...", 
                              command=self.open_auto_tags_editor, 
                              underline=10, 
                              accelerator="Ctrl+E")
        self.bind("<Control-e>", self.open_auto_tags_editor)

        file_menu.add_command(label="Title Feature Extraction...", 
                              command=self.open_feature_extractor, 
                              underline=10, 
                              accelerator="Ctrl+W")
        self.bind("<Control-w>", self.open_feature_extractor)

        file_menu.add_command(label="Logo Removal Tool...", 
                              command=self.open_logo_remover, 
                              underline=10, 
                              accelerator="Ctrl+W")
        self.bind("<Control-w>", self.open_logo_remover)

        file_menu.add_command(label="Exit", 
                              command=self.quit, 
                              underline=1, 
                              accelerator="Ctrl+Q")
        self.bind_all("<Control-q>", self.quit)

        #Add the complete menu bar to the file menu
        menu_bar.add_cascade(label="File", menu=file_menu, underline=0)
        self.config(menu=menu_bar)

    #Create the frame for image display
    def create_image_frame(self):
        self.image_frame = tk.Frame(self.root_frame, 
                              width=400, height=400, 
                              bd=2, 
                              relief=tk.SUNKEN)
        self.image_frame.grid(row=0, column=0, padx=0, pady=0, sticky="nsew")
        self.image_frame.rowconfigure(0, weight=1)
        self.image_frame.columnconfigure(0, weight=1)

        # Display image in image_frame
        self.image = self.icon_image
        self.framed_image = ImageTk.PhotoImage(self.image)
        self.sizer_frame = tk.Frame(self.image_frame,
                                    width=400, height=400,
                                    bd=0)
        self.sizer_frame.grid(row=0, column=0, sticky="nsew")
        self.sizer_frame.rowconfigure(0, weight=1)
        self.sizer_frame.columnconfigure(0, weight=1)

        self.sizer_frame.bind("<Configure>", self.image_resizer)

        self.x = self.y = 0
        self.canvas = tk.Canvas(self.sizer_frame, cursor="cross")

        self.canvas.grid(row=0,column=0,sticky="nswe")

        self.canvas.bind("<ButtonPress-1>", self.on_button_press)
        self.canvas.bind("<B1-Motion>", self.on_move_press)
        self.canvas.bind("<ButtonRelease-1>", self.on_button_release)

        self.rect = None

        self.start_x = None
        self.start_y = None

        center_x = self.sizer_frame.winfo_width() / 2
        center_y = self.sizer_frame.winfo_height() / 2

        self.canvas.create_image(center_x, center_y, anchor="center",image=self.framed_image)
        self.image_info_section()

    def image_info_section(self):

        posx = 10
        posy = 10
        self.image_info = self.canvas.create_text(posx , posy,  anchor= "nw",text= "", width= 200,font=("Segoe_UI_Semibold 9"))
        self.update_image_info()
    def update_image_info(self):
        print("update info")
        img_info = "w: " + str(self.image.width) + "\n" + "h: " + str(self.image.height)
        self.canvas.itemconfigure(self.image_info, text = img_info)

    #region tool settings

    def load_app_settings(self):
        path = appdata_path + "settings.json"
        
        if isfile(path):
            with open(path, "r") as f:
                json_data = json.load(f)
                print(str(json_data['interrogator_settings']))
                wd14_set = interrogator_wd14_settings(json_data["interrogator_settings"]["wd14_settings"])#["wd14_settings"]
                print(str(wd14_set.general_threshold))
                clip_set = interrogator_clip_settings(json_data["interrogator_settings"]["clip_settings"])
                #i_set = interrogator_settings(json_data['wd14_settings'],json_data['clip_settings'] )  # Instantiate InnerClass
                
                i_set = interrogator_settings(json_data["interrogator_settings"]["interrogator_options_pick"],wd14_set,clip_set)  # Instantiate InnerClass
                # settings = app_settings(json_data["window_states"],i_set)
                settings = app_settings(json_data["window_states"],i_set)
                return settings
        else:
            return app_settings([], interrogator_settings(interrogator_wd14_settings(),interrogator_clip_settings()))
    def save_app_settings(self):
        try:
            with open(appdata_path + "settings.json", "w+") as f:
                f.write(json.dumps(self.settings.__dict__, default=lambda o: o.__dict__, indent=4))
            print("saved app settings")
        except:
            print(traceback.format_exc())
    #endregion

    def on_button_press(self,event):
        # save mouse drag start position
        self.start_x = self.canvas.canvasx(event.x)
        self.start_y = self.canvas.canvasy(event.y)
        self.on_move_press(event)
        
    def on_move_press(self, event):
        curx = self.canvas.canvasx(event.x)
        cury = self.canvas.canvasy(event.y)

        l_pct, t_pct = self.coord_to_pct(curx, cury)
        r_pct, b_pct = self.coord_to_pct(self.start_x, self.start_y)

        self.l_pct = min(l_pct, r_pct)
        self.t_pct = min(t_pct, b_pct)
        self.r_pct = max(l_pct, r_pct)
        self.b_pct = max(t_pct, b_pct)

        self.l_pct = max(0, min(self.l_pct, 1))
        self.t_pct = max(0, min(self.t_pct, 1))
        self.r_pct = max(0, min(self.r_pct, 1))
        self.b_pct = max(0, min(self.b_pct, 1))

        # expand rectangle as you drag the mouse
        self.generate_crop_rectangle()
    
    def coord_to_pct(self, x, y):
        w = self.image_frame.winfo_width() - 4
        h = self.image_frame.winfo_height() - 4
        x_offset = (w - self.image_width) / 2
        y_offset = (h - self.image_height) / 2
        return ((x - x_offset) / self.image_width, 
                (y - y_offset) / self.image_height)

    def pct_to_coord(self, x_pct, y_pct):
        w = self.image_frame.winfo_width() - 4
        h = self.image_frame.winfo_height() - 4
        x_offset = (w - self.image_width) / 2
        y_offset = (h - self.image_height) / 2
        return (int(x_pct * self.image_width + x_offset),
                int(y_pct * self.image_height + y_offset))

    def get_crop(self):
        crop = [
                self.l_pct,
                self.t_pct,
                self.r_pct,
                self.b_pct
            ]
        return crop
    
    def generate_crop_rectangle(self):
        f_w = self.image_frame.winfo_width() - 4
        f_h = self.image_frame.winfo_height() - 4
        x_offset = (f_w - self.image_width) / 2
        y_offset = (f_h - self.image_height) / 2

        try:
            if self.crop_left_area:
                self.canvas.delete(self.crop_left_area)
            if self.crop_top_area:
                self.canvas.delete(self.crop_top_area)
            if self.crop_right_area:
                self.canvas.delete(self.crop_right_area)
            if self.crop_bottom_area:
                self.canvas.delete(self.crop_bottom_area)
        except:
            print(traceback.format_exc())

        l, t = self.pct_to_coord(self.l_pct, self.t_pct)
        r, b = self.pct_to_coord(self.r_pct, self.b_pct)

        
        w = int(l - x_offset)
        h = int(f_h - 2 * y_offset)
        fill = self.canvas.winfo_rgb("red") + (int((0.5 if w > 1 else 0) * 255),)
        image = Image.new('RGBA', (w, h), fill)
        self.crop_left_image = ImageTk.PhotoImage(image)
        self.crop_left_area = self.canvas.create_image(x_offset, y_offset, image=self.crop_left_image, anchor="nw")

        w = int(r - l)
        h = int(t - y_offset)
        fill = self.canvas.winfo_rgb("red") + (int((0.5 if h > 1 else 0) * 255),)
        image = Image.new('RGBA', (w, h), fill)
        self.crop_top_image = ImageTk.PhotoImage(image)
        self.crop_top_area = self.canvas.create_image(l, y_offset, image=self.crop_top_image, anchor="nw")

        w = int(f_w - r - x_offset)
        h = int(f_h - 2 * y_offset)
        fill = self.canvas.winfo_rgb("red") + (int((0.5 if w > 1 else 0) * 255),)
        image = Image.new('RGBA', (w, h), fill)
        self.crop_right_image = ImageTk.PhotoImage(image)
        self.crop_right_area = self.canvas.create_image(r, y_offset, image=self.crop_right_image, anchor="nw")

        w = int(r - l)
        h = int(f_h - b - y_offset)
        fill = self.canvas.winfo_rgb("red") + (int((0.5 if h > 1 else 0) * 255),)
        image = Image.new('RGBA', (w, h), fill)
        self.crop_bottom_image = ImageTk.PhotoImage(image)
        self.crop_bottom_area = self.canvas.create_image(l, b, image=self.crop_bottom_image, anchor="nw")


    def on_button_release(self, event):
        coord1 = self.pct_to_coord(self.l_pct, self.t_pct)
        coord2 = self.pct_to_coord(self.r_pct, self.b_pct)
        if(coord2[0] - coord1[0] < 5
           and coord2[1] - coord1[1] < 5):
            self.l_pct = 0
            self.t_pct = 0
            self.r_pct = 1
            self.b_pct = 1
            self.canvas.delete(self.crop_left_area)
            self.canvas.delete(self.crop_top_area)
            self.canvas.delete(self.crop_right_area)
            self.canvas.delete(self.crop_bottom_area)

    #Create the initial frame display
    def create_initial_frame(self):
        self.initial_frame = tk.Frame(self.root_frame,
                               width=300, height=400, 
                               bd=1, 
                               relief=tk.RAISED)
        self.initial_frame.columnconfigure(0, weight = 1)
        self.initial_frame.rowconfigure(0, weight = 1)
        self.initial_frame.rowconfigure(2, weight = 1)
        self.add_initial_buttons()
        self.show_initial_frame()

    #Create the frame for form display
    def create_form_frame(self):
        self.form_frame = tk.Frame(self.root_frame,
                               width=300, height=400, 
                               bd=1,
                               relief=tk.RAISED)
        self.form_frame.columnconfigure(1, weight = 1)

        self.top_group = tk.LabelFrame(self.form_frame, 
                                    text="")
        self.top_group.columnconfigure(1, weight = 1)

        self.top_group.grid(row=0, column=0, 
                          columnspan=2, 
                          padx=5, pady=5,
                          sticky="nsew")        

        self.add_artist_entry()
        self.add_style_entry()
        self.add_title_entry()
        self.add_rating_entry()
        self.add_summary_text()
        self.add_features_table()
        self.add_automatic_tags_text()        
        self.add_form_buttons()
        self.add_feature_checklist()
        self.show_form_frame()

    #Hide the right hand form controls
    def hide_form_frame(self):
        self.form_frame.grid_remove()

    #Show the right hand form controls
    def show_form_frame(self):
        self.form_frame.grid(row=0, column=1, 
                              padx=0, pady=0, 
                              sticky="nsew")

    #Hide the initial "Open a dataset" prompt
    def hide_initial_frame(self):
        self.initial_frame.grid_remove()

    #Show the initial "Open a dataset" prompt
    def show_initial_frame(self):
        self.initial_frame.grid(row=0, column=1, 
                              padx=0, pady=0, 
                              sticky="nsew")
        self.initial_frame.lift()
        self.image_resizer()

    #Add the star rating query to the form
    def add_rating_entry(self):
        #Labeled group for rating
        rating_group = tk.LabelFrame(self.form_frame, 
                                    text="Quality for Training")
        rating_group.grid(row=3, column=0, 
                          columnspan=2, 
                          padx=5, pady=5,
                          sticky="nsew")

        self.rating = tk.IntVar()
        self.rating.set(self.get_defaults()["rating"])
        tk.Radiobutton(rating_group, 
           text=f"Not rated",
           variable=self.rating, 
           value=0).grid(row=0, column=0, sticky="w")
        for i in range(1, 6):
            tk.Radiobutton(rating_group, 
               text=f"{i}",
               variable=self.rating, 
               value=i).grid(row=0, column=i, sticky="w")


    #Add the artist query to the form
    def add_artist_entry(self):
        artist_name_label = tk.Label(self.top_group, text="Artist: ")
        artist_name_label.grid(row=0, column=0, padx=0, pady=5, sticky="e")

        self.artist_name = tk.StringVar(None)
        self.artist_name.set(self.get_defaults()["artist"])
        self.artist_name_entry = tk.Entry(self.top_group,
                                     textvariable=self.artist_name, 
                                     justify="left")
        self.artist_name_entry.grid(row=0, column=1, padx=(0, 5), pady=5, sticky="ew")
        self.artist_name_entry.bind('<Control-a>', self.select_all)
        self.artist_name_entry.focus_set()
        self.artist_name_entry.select_range(0, 'end')

    #Add the style query to the form
    def add_style_entry(self):
        style_label = tk.Label(self.top_group, text="Style: ")
        style_label.grid(row=1, column=0, padx=0, pady=5, sticky="e")

        self.style = tk.StringVar(None)
        self.style.set(self.get_defaults()["style"])
        self.style_entry = tk.Entry(self.top_group,
                                     textvariable=self.style, 
                                     justify="left")
        self.style_entry.grid(row=1, column=1, padx=(0, 5), pady=5, sticky="ew")
        self.style_entry.bind('<Control-a>', self.select_all)

    #Add the title query to the form
    def add_title_entry(self):
        title_label = tk.Label(self.top_group, text="Title: ")
        title_label.grid(row=2, column=0, padx=0, pady=5, sticky="e")

        self.title_var = tk.StringVar(None)
        self.title_var.set(self.get_defaults()["title"])
        self.title_entry = tk.Entry(self.top_group, textvariable=self.title_var, justify="left")
        self.title_entry.grid(row=2, column=1, padx=(0, 5), pady=5, sticky="ew")
        self.title_entry.bind('<Control-a>', self.select_all)

    #Move the focus to the prev item in the form
    def focus_prev_widget(self, event):
        event.widget.tk_focusPrev().focus()
        return("break")

    #Move the focus to the next item in the form
    def focus_next_widget(self, event):
        event.widget.tk_focusNext().focus()
        return("break")

    #Add the summary text box to the form
    def add_summary_text(self):
        summary_label = tk.Label(self.form_frame, text="Summary: ")
        summary_label.grid(row=4, column=0, padx=5, pady=(5,0), sticky="sw")

        self.summary_textbox = tk.Text(self.form_frame, width=30, height=4, wrap=tk.WORD, spacing2=2, spacing3=2)
        self.summary_textbox.grid(row=5, column=0, 
                             columnspan=2, 
                             padx=5, pady=(0,5), 
                             sticky="ew")
        self.summary_textbox.bind("<Tab>", self.focus_next_widget)
        self.summary_textbox.bind('<Control-a>', self.select_all)
        #self.summary_textbox.bind('<KeyRelease>', self.add_features_from_summary)

    #Add the features table to the form
    def add_features_table(self):
        self.features_group = tk.LabelFrame(self.form_frame, 
                                    text="Features")
        self.features_group.grid(row=6, column=0, 
                            columnspan=2, 
                            padx=5, pady=5,
                            sticky="nsew")

        self.features_group.rowconfigure(1, weight=1)
        self.features_group.columnconfigure(0, weight=1)
        self.features_group.columnconfigure(1, weight=3)

        features_name_label = tk.Label(self.features_group, text="Name")
        features_name_label.grid(row=0, column=0, padx=5, pady=0, sticky="ew")
        features_desc_label = tk.Label(self.features_group, text="Description")
        features_desc_label.grid(row=0, column=1, 
                                 padx=5, pady=0, 
                                 sticky="ew")

        #Populate feature table
        for _ in range(2):
            self.add_row()

    #Add the automated tag text box to the form
    def add_automatic_tags_text(self):
        automatic_tags_label = tk.Label(self.form_frame, text="Automated tags: ")
        automatic_tags_label.grid(row=9, column=0, padx=5, pady=(5, 0), sticky="sw")

        self.automatic_tags_textbox = tk.Text(self.form_frame, width=30, height=4, wrap=tk.WORD, spacing2=2, spacing3=2)
        self.automatic_tags_textbox.grid(row=10, column=0, 
                                    columnspan=2, 
                                    padx=5, pady=(0, 5), 
                                    sticky="ew")

        self.automatic_tags_textbox.bind("<Tab>", self.focus_next_widget)
        self.automatic_tags_textbox.bind('<Control-a>', self.select_all)

        self.form_frame.rowconfigure(9, weight=1)

        import_tags_btn = tk.Button(self.form_frame, 
                                  text="Import automatic tags (Ctrl+T)", 
                                  command=self.update_ui_automatic_tags)
        import_tags_btn.grid(row=12, column=0, 
                             columnspan=2, 
                             padx=5, pady=5, 
                             sticky="ew")
        
        #On Linux at least, Ctrl-t has a really annoying default behavior that swaps two characters.
        self.bind("<Control-t>", self.update_ui_automatic_tags)
        self.artist_name_entry.bind("<Control-t>", self.update_ui_automatic_tags)
        self.style_entry.bind("<Control-t>", self.update_ui_automatic_tags)
        self.title_entry.bind("<Control-t>", self.update_ui_automatic_tags)
        self.summary_textbox.bind("<Control-t>", self.update_ui_automatic_tags)
        self.automatic_tags_textbox.bind("<Control-t>", self.update_ui_automatic_tags)
        self.automatic_tags_textbox.bind("<Control-m>", self.add_autotag_to_editor)

        save_json_btn = tk.Button(self.form_frame, 
                                  text="Save JSON (Ctrl+S)", 
                                  command=self.save_json)
        save_json_btn.grid(row=13, column=1, 
                           padx=5, pady=5, 
                           sticky="ew")
        self.bind("<Control-s>", self.save_json)
        self.autosave = tkinter.IntVar()
        self.autosave_toggle_btn = tk.Checkbutton(self.form_frame, 
                                  text="Autosave", 
                                  variable= self.autosave,
                                  command=self.autosave_toggle)
        self.autosave_toggle_btn.grid(row=13, column=0, 
                           padx=5, pady=5, 
                           sticky="ew")

        


    #Add the "Open a dataset" prompt button to the initial display
    def add_initial_buttons(self):
        self.initial_btn = tk.Button(self.initial_frame, 
                                  text="Open Dataset... (Ctrl+O)", 
                                  command=self.open_dataset)
        self.initial_btn.grid(row=2, column=0, 
                           padx=5, pady=5, 
                           sticky="ew")
                                  
    #Add the save and navigation buttons to the right-hand form
    def add_form_buttons(self):
        self.prev_file_btn = tk.Button(self.form_frame, 
                                  text="Previous (Ctrl+P/B)", 
                                  command=self.prev_file)
        self.prev_file_btn.grid(row=14, column=0, 
                           padx=5, pady=5, 
                           sticky="ew")
        self.root_frame.bind_all("<Control-p>", self.prev_file)
        self.root_frame.bind_all("<Control-b>", self.prev_file)

        self.next_file_btn = tk.Button(self.form_frame, 
                                  text="Next (Ctrl+N/F)", 
                                  command=self.next_file)
        self.next_file_btn.grid(row=14, column=1, 
                           padx=5, pady=5, 
                           sticky="ew")
        self.root_frame.bind_all("<Control-n>", self.next_file)
        self.root_frame.bind_all("<Control-f>", self.next_file)      

    def on_press(self, key):
        if key == pynput.keyboard.Key.ctrl_l:
            self.ctrl_pressed = True
        if key == pynput.keyboard.Key.alt_l:
            self.alt_pressed = True
        if key == pynput.keyboard.Key.shift_l:
            self.shift_pressed = True

    def on_release(self, key):
        if key == pynput.keyboard.Key.ctrl_l:
            self.ctrl_pressed = False
        if key == pynput.keyboard.Key.alt_l:
            self.alt_pressed = False
        if key == pynput.keyboard.Key.shift_l:
            self.shift_pressed = False
    

    def feature_clicked(self, iid, force_state = -1):        
        self.disable_feature_tracing()
        try:            
            tv = self.feature_checklist_treeview               
            deleting = False
            if(force_state == -1):
                if self.ctrl_pressed:
                    print(f"Delete {iid}")
                    deleting = True
                    tv.uncheck(iid)
                elif self.shift_pressed and not self.dataset_viewer_window == None:
                    toggle = tv.get_component_state(iid)
                    self.dataset_viewer_window.apply_feature_to_selection(iid,toggle)
                elif self.alt_pressed:
                    
                    print(f"Bulk Modify {iid}")
                    self.rename_feature(iid)
                else:
                    tv.toggle(iid)
            elif(force_state == 0):
                #deleting = True
                tv.uncheck(iid)
            elif(force_state == 1):
                tv.check(iid)


            feature_iids = tv.get_children()
            noun_iids = []
            desc_iids = []
            for feature in feature_iids:
                for noun in tv.get_children(feature):
                    noun_iids.append(noun)
            for noun in noun_iids:
                for desc in tv.get_children(noun):
                    desc_iids.append(desc)

            tree = [iid]
            while tv.parent(tree[0]):
                tree.insert(0, tv.parent(tree[0]))


            #Find the row that matches this feature (if any)
            for row in range(self.feature_count):
                if(self.features[row][0]["var"].get().strip() == tree[0].strip()):
                    break


            #Find the last component that matches this noun (if any)
            desc = self.features[row][1]["var"].get()
            components = []
            this_component = ""
            feature = tv.item(tree[0], "text")[2:].strip()
            noun = ""
            adjective = ""
            if len(tree) > 1:
                noun = tv.item(tree[1], "text")[2:].strip()
                if row < self.feature_count:
                    components = [c.strip() for c in desc.split(",")]
                    for c in reversed(components):
                        if c.endswith(noun):
                            this_component = c
                            break
            if len(tree) > 2:
                adjective = tv.item(tree[2], "text")[2:].strip()

            if tv.checked(iid):

                #Make a new feature row if necessary and set it.
                if row == self.feature_count:
                    for row in range(self.feature_count):
                        if(self.features[row][0]["var"] == ""
                           and self.features[row][1]["var"]):
                            break

                self.features[row][0]["var"].set(feature)

                #If this is a noun, and the noun isn't already in the
                #description, then add it.
                if len(tree) > 1 and not this_component.endswith(noun):
                    if desc != "":
                        desc += f", {noun}"
                    else:
                        desc = f"{noun}"
                    self.features[row][1]["var"].set(desc)
                    this_component = f"{noun}"
                    if components != ['']:
                        components.append(this_component)
                    else:
                        components = [this_component]

                #If this is an adjective, and it isn't already in the component,
                #then prepend it before the noun.
                if len(tree) > 2 and adjective not in this_component:
                    new_component = f"{adjective} {noun}".join(this_component.rsplit(noun, 1))
                    for i in reversed(range(len(components))):
                        if components[i] == this_component:
                            components[i] = new_component
                    self.features[row][1]["var"].set(", ".join(components))

            else:
                #If this is a feature, remove the entire feature row.
                if len(tree) == 1 and row != self.feature_count:
                    self.remove_row(row)

                #If this is a noun, remove the relevant component.
                if len(tree) == 2 and this_component != "":
                    components.remove(this_component)
                    self.features[row][1]["var"].set(", ".join(components))

                #If this is an adjective, remove it from the relevant component.
                if len(tree) == 3 and adjective in this_component:
                    new_component = this_component.replace(f"{adjective} ", "")
                    for i in reversed(range(len(components))):
                        if components[i] == this_component:
                            components[i] = new_component.strip()
                    self.features[row][1]["var"].set(", ".join(components))

            if deleting:
                tv.delete(iid)
                relative_path = relpath(pathlib.Path(self.image_files[self.file_index]).absolute(), self.path)
                parents = [str(p) for p in pathlib.Path(relative_path).parents]
                for p in self.known_feature_checklists:
                    if p in parents:
                        self.known_feature_checklists[p] = [x for x in self.known_feature_checklists[p] if not x[0].startswith(iid)]
                self.known_checklist_full[p] = [x for x in self.known_checklist_full[p] if not x[0].startswith(iid)]
                          
        except:
            print(traceback.format_exc())
        self.enable_feature_tracing()
        self.feature_modified(self.features[0][0]["var"].get())

    def feature_right_clicked(self, event = None):
        #print("f right click iid: " + str(iid))
        
        cmenu_iid = self.feature_checklist_treeview.identify('item', event.x, event.y)
        #print("f right click iid: " + str(self.cmenu_iid))
        menu_options = []
        # menu_options.append(context_menu_option_data("Delete", self.feature_rename_callback))
        # menu_options.append(context_menu_option_data("Rename", self.feature_rename_callback))
        # menu_options.append(context_menu_option_data("Rename", self.feature_rename_callback))

        menu_options.append(context_menu_option_data("Delete",  lambda: self.rename_feature(cmenu_iid )))
        menu_options.append(context_menu_option_data("Edit", lambda: self.rename_feature(cmenu_iid )))
        menu_options.append(context_menu_option_data("Add to Title Extractor", lambda: self.feature_extractor_add_entry(cmenu_iid)))

        self.open_context_menu(self.top_group,menu_options)

    def feature_rename_callback(self):
        self.rename_feature(self.cmenu_iid)
    def feature_extractor_add_entry(self,iid):
        if(self.feature_extractor_window == None):
            self.feature_extractor_window = title_feature_extractor_window(self,self.feature_extractor)
            self.feature_extractor_window.add_entry(iid)

    def add_feature_checklist(self):

        self.feature_checklist_group = tk.LabelFrame(self.form_frame, 
                                    text="")
        self.feature_checklist_group.grid(row=0, column=2, 
                            rowspan=15, 
                            padx=5, pady=5,
                            sticky="nsew")

        self.feature_checklist_group.rowconfigure(1, weight=1)
        self.feature_checklist_group.columnconfigure(0, weight=1,minsize=220)

        bgcolor = self.feature_checklist_group["background"]


        self.feature_checklist_controls_top = tk.Frame(self.feature_checklist_group,height= 10)
        self.feature_checklist_controls_top.grid(row=0, column=0, 
                            padx=0, pady=0,
                            sticky="nsew")
        self.feature_checklist_controls_top.rowconfigure(0, weight=1)
        self.feature_checklist_controls_top.columnconfigure(0, weight=1)

        self.checklist_mode_btn = tk.Button(self.feature_checklist_controls_top, text='Features: Directory',
                                            height= 1, relief= "groove",
                               command=self.switch_checklists)
        self.checklist_mode_btn.grid(row=0, column=0, padx=4, pady=4, sticky="sew")


        ttk.Style().configure("Treeview", borderwidth=0, relief=tk.FLAT, background=bgcolor, fieldbackground=bgcolor, font="Segoe_UI_Semibold 9")
        self.feature_checklist_treeview = TtkCheckList(self.feature_checklist_group,
                                                       height=self.feature_count, 
                                                       separator=treeview_separator,
                                                       clicked=self.feature_clicked)
        self.feature_checklist_treeview.grid(row=1, column=0, padx=5, pady=5, sticky="news")
        self.feature_checklist_treeview.rowconfigure(0, weight=1)
        self.feature_checklist_treeview.columnconfigure(0, weight=1)
        self.feature_checklist_treeview.bind("<Button-3>", self.feature_right_clicked)

        # Constructing vertical scrollbar
        # with treeview
        self.verscrlbar = ttk.Scrollbar(self.feature_checklist_group,
                           orient ="vertical",
                           command = self.feature_checklist_treeview.yview)
        self.verscrlbar.grid(row=1, column=1, sticky="nes")
        self.feature_checklist_treeview.configure(yscrollcommand = self.verscrlbar.set)
        self.update_checklist()

        self.feature_checklist_controls_bottom = tk.Frame(self.feature_checklist_group)
        self.feature_checklist_controls_bottom.grid(row=2, column=0, 
                            padx=2, pady=2,
                            sticky="nsew")
        self.feature_checklist_controls_bottom.columnconfigure(0, weight=1)
        self.feature_checklist_controls_bottom.columnconfigure(1, weight=1)
        self.feature_checklist_controls_bottom.columnconfigure(2, weight=0)
        self.feature_checklist_controls_bottom.rowconfigure(0, weight=1)
        self.feature_checklist_controls_bottom.rowconfigure(1, weight=0)

        copy_feature_checklist_btn = tk.Button(self.feature_checklist_controls_bottom, text='Copy', 
                               command=self.copy_item_data)
        copy_feature_checklist_btn.grid(row=0, column=0, padx=4, pady=4, sticky="sew")
        paste_feature_checklist_btn = tk.Button(self.feature_checklist_controls_bottom, text='Paste', 
                               command=self.paste_item_data)
        paste_feature_checklist_btn.grid(row=0, column=1, padx=4, pady=4, sticky="sew")

        self.paste_settings_btn = tk.Button(self.feature_checklist_controls_bottom, text='⛭', 
                               command=self.set_paste_settings)
        self.paste_settings_btn.grid(row=0, column=2, padx=4, pady=4, sticky="sew")

        self.clipboard_label = tk.Label(self.feature_checklist_controls_bottom, text="Clipboard: Empty")
        self.clipboard_label.grid(row=1, column=0, padx=2, pady=0, sticky="sw",columnspan=3)

    def copy_item_data(self):
        self.stored_item = self.get_item_from_ui()
        img = Image.open(self.image_files[self.file_index])
        self.paste_set.c_width = img.width
        self.paste_set.c_height = img.height

        self.clipboard_label.configure(text= "Clipboard: " + self.stored_item["title"])

    def paste_item_data(self):
        if(self.shift_pressed and not self.dataset_viewer_window == None and len(self.dataset_viewer_window.selected_entries) > 0):
            self.paste_item_to_selection()
        else:
            self.apply_paste_item_data(self.file_index)

    def paste_item_to_selection(self):
        selected_entry = self.file_index

        c_width = 0
        c_height = 0
        if(self.paste_set.con_resolution):
            c_width = self.paste_set.c_width
            c_height = self.paste_set.c_height
        
        for entry in self.dataset_viewer_window.selected_entries:
            file_index = self.image_files.index(entry.file)
            self.apply_paste_item_data(file_index,c_width,c_height)
        if(not selected_entry == self.file_index):
            self.set_ui(selected_entry)
            self.file_index = selected_entry

    def apply_paste_item_data(self,file_index,c_width = 0, c_height = 0):

        item = self.get_item_from_file(self.image_files[file_index])

        if(self.paste_set.con_title and not self.paste_set.con_title_text in item["title"]):
            return "break"
        if(self.paste_set.con_resolution):
            img = Image.open(self.image_files[file_index])
            if(not img.width == c_width or not img.height == c_height):
                return "break"

        if(self.paste_set.set_artist):
            try: 
                item["artist"] = self.stored_item["artist"]
            except: 
                print(traceback.format_exc())

        if(self.paste_set.set_style):
            try: 
                item["style"] = self.stored_item["style"]
            except: 
                print(traceback.format_exc())

        if(self.paste_set.set_rating):
            try:
                item["rating"] = self.stored_item["rating"]
            except:
                print(traceback.format_exc())

        if(self.paste_set.set_summary):
            try:
                item["summary"] = self.stored_item["summary"]
            except:
                print(traceback.format_exc())

        if(self.paste_set.set_autotags):
            try:
                if "automatic_tags" in self.stored_item:
                    if self.stored_item["automatic_tags"]:
                        item["automatic_tags"] = self.stored_item["automatic_tags"]

            except:
                print(traceback.format_exc())
        if(self.paste_set.set_cropping):
            try:
                item["crop"][0] = self.stored_item["crop"][0]
                item["crop"][1] = self.stored_item["crop"][1]
                item["crop"][2] = self.stored_item["crop"][2]
                item["crop"][3] = self.stored_item["crop"][3]
                #self.generate_crop_rectangle()
            except:
                print(traceback.format_exc())

        self.write_item_to_file(
            item,
            splitext(self.image_files[file_index])[0] + ".json")

        if(self.paste_set.set_features):
            self.file_index = file_index
            self.set_ui(file_index,None,True)
            features_modified = False
            self.disable_feature_tracing()
            try:
                i = 0
                features_modified = True
                for k, v in  self.stored_item["features"].items():
                    if(i >= self.feature_count):
                        self.add_row()    
                    self.disable_feature_tracing()            
                    self.features[i][0]["var"].set(k)
                    self.features[i][1]["var"].set(v)
                    i += 1
                
            except:
                print(traceback.format_exc())

            if(features_modified):
                if len(self.features) > 0:
                    self.feature_modified(self.features[0][0]["var"])
                self.save_json()


    def set_paste_settings(self,event = None):
        if len(self.image_files) == 0:
            showerror(parent=self, title="Error", message="Dataset must be open")
            return
        #Pop up dialog to save default settings for path
        self.update()
        self.wait_window(paste_settings_popup(self).top)
        self.update()

    def update_checklist(self):
        for item in self.feature_checklist_treeview.get_children():
           self.feature_checklist_treeview.delete(item)        
        for item in self.feature_checklist:
            self.feature_checklist_treeview.add_item(item[0])
            if item[1]:
                self.feature_checklist_treeview.check(item[0])
        self.feature_checklist_treeview.autofit()

    def disable_feature_tracing(self):    
        for i in range(len(self.features)):
            for j in range(2):
                if self.features[i][j]["trace"]:
                    self.features[i][j]["var"].trace_vdelete("w", self.features[i][j]["trace"])
                    self.features[i][j]["trace"] = None

    def enable_feature_tracing(self):
        self.disable_feature_tracing()
        for i in range(len(self.features)):
            for j in range(2):
                self.features[i][j]["trace"] = self.features[i][j]["var"].trace("w",
                    lambda name, index, mode, var=self.features[i][j]["var"]: self.feature_modified(var))

    #Clear the UI
    def clear_ui(self):
        self.summary_textbox.delete("1.0", "end")
        self.automatic_tags_textbox.delete("1.0", "end")
        self.image = self.icon_image
        self.framed_image = ImageTk.PhotoImage(self.image)
        self.canvas.delete(self.image_handle)

        self.disable_feature_tracing()

        if self.feature_count > 0:
            while self.feature_count > 1:
                self.remove_row(self.feature_count - 1)
            self.features[0][0]["var"].set("")
            self.features[0][1]["var"].set("")

        self.enable_feature_tracing()

        self.statusbar_text.set("")

    #Set the UI to the given item's values
    def set_ui(self, index: int, item = None, load_only_data = False):
        if len(self.image_files) == 0 or index > len(self.image_files):
            return
        
        self.clear_ui()

        f = self.image_files[index]
        if(not load_only_data):
            self.load_image(f)
            self.update_image_info()

        if item is None:
            item = self.get_item_from_file(self.image_files[index])


        try: 
            self.artist_name.set(item["artist"])
        except: 
            print(traceback.format_exc())

        try: 
            self.style.set(item["style"])
        except: 
            print(traceback.format_exc())

        try:
            self.title_var.set(item["title"])
        except:
            print(traceback.format_exc())

        try:
            self.rating.set(item["rating"])
        except:
            print(traceback.format_exc())

        try:
            self.summary_textbox.insert("1.0", item["summary"])
        except:
            print(traceback.format_exc())

        try:
            self.l_pct = item["crop"][0]
            self.t_pct = item["crop"][1]
            self.r_pct = item["crop"][2]
            self.b_pct = item["crop"][3]
        except:
            print(traceback.format_exc())

        self.generate_crop_rectangle()
        self.disable_feature_tracing()

        try:
            i = 0
            for k, v in item["features"].items():
                if(i >= self.feature_count):
                    self.add_row()    
                self.disable_feature_tracing()            
                self.features[i][0]["var"].set(k)
                self.features[i][1]["var"].set(v)
                i += 1
        except:
            print(traceback.format_exc())

        if len(self.features) > 0:
            self.feature_modified(self.features[0][0]["var"])

        try:
            if "automatic_tags" in item:
                if item["automatic_tags"]:
                    self.automatic_tags_textbox.insert("1.0", item["automatic_tags"])
        except:
            print(traceback.format_exc())

        #Enable/disable buttons as appropriate
        if self.file_index > 0:
            self.prev_file_btn["state"] = "normal"
        else:
            self.prev_file_btn["state"] = "disabled"

        if self.file_index < len(self.image_files) - 1:
            self.next_file_btn["state"] = "normal"
        else:
            self.next_file_btn["state"] = "disabled"

        
        self.statusbar_text.set(f"Image {1 + self.file_index}/{len(self.image_files)}: "
                                f"{relpath(pathlib.Path(self.image_files[self.file_index]), self.path)}")
        self.events.on_set_ui()
        self.update_idletasks()
        
      
    # walk over shadow registry and build an index of feature -> file index
    # note: i dont think you can do a partial update of this, we need to rebuild the entire
    # index whenver something has changed, because if a file used to be pointed to by feature A
    # and now it isnt, that information is no longer in the shadow registry and we cant really remove
    # it.
    def rebuild_feature_index(self):
        for i, sr in enumerate(self.shadow_registry):
            if not sr or not "features" in sr or not len(sr["features"].keys()):
                continue

            for f_name, f_desc in sr["features"].items():
                f_desc_exploded = [x.strip() for x in f_desc.split(',')]
                if f_name not in self.feature_index:
                    self.feature_index[f_name] = {}
                for _d in f_desc_exploded:
                    if not _d:
                        continue

                    if _d not in self.feature_index[f_name]:
                        self.feature_index[f_name][_d] = []
                    self.feature_index[f_name][_d].append(i)

    def init_shadow_registry(self):
        if not len(self.shadow_registry):
            self.shadow_registry = [None] * len(self.image_files)

    # synchronise in memory shadow registry from json on disk
    # awas 
    def update_shadow_registry(self, index, item=None):
        if not item:
            item = self.get_item_from_file(self.image_files[index])

        self.shadow_registry[index] = item

        return item

    #Gather known feature set
    def update_known_features(self, file, item):

        relative_path = pathlib.Path(relpath(pathlib.Path(file), self.path))
        parents = [str(p) for p in relative_path.parents]
        for p in parents:
            #print("parent " + str(p))
            if p not in self.known_features:
                self.known_features[p] = {}

        p = parents[0]

        combined_features = {}
        if p in self.known_features:
            combined_features = self.known_features[p]

        if "features" in item:
            for feature in item["features"]:
                components = item["features"][feature].split(",")
                if feature not in combined_features:
                    combined_features[feature] = ""
                combined_components = combined_features[feature].split(",")
                    
                for c in components:
                    c = c.strip()
                    if c not in combined_components:
                        combined_features[feature] += ", " + c                            

        self.known_features.update({p: combined_features})
                    

    def build_known_feature_checklists(self):
        #print("build feature checklist")
        self.known_feature_checklists = {}
        self.known_feature_checklist_full = []
        known_checklist_full = []
        for path in self.known_features:
            known_checklist = []
            p = str(path)
            for name in self.known_features[p]:
                if name != '':
                    desc = self.known_features[p][name]
                    new_item = (name, False)

                    found = False
                    for parent in pathlib.Path(path).parents:
                        parent = str(parent)
                        if parent not in self.known_feature_checklists:
                            self.known_feature_checklists[parent] = {}
                        if new_item in self.known_feature_checklists[parent]:
                            found = True

                    if not found and new_item not in known_checklist:
                        known_checklist.append(new_item)
                    if new_item not in known_checklist_full:
                        known_checklist_full.append(new_item)
                    components = desc.split(",")
                    for c in components:
                        c = c.strip()
                        if c != '' and c != name:
                            for c_split in self.split_component(c):
                                new_item = (name + treeview_separator + c_split, False)
                                found = False
                                for parent in pathlib.Path(path).parents:
                                    if new_item in self.known_feature_checklists[str(parent)]:
                                        found = True
                                if not found and new_item not in known_checklist:
                                    known_checklist.append(new_item)
                                if new_item not in known_checklist_full:
                                    known_checklist_full.append(new_item)
            known_checklist.sort()
            self.known_feature_checklists[path] = known_checklist
        #Build full checklist
        known_checklist_full.sort()
        self.known_feature_checklist_full = known_checklist_full


        self.known_features = {}

    def force_checklist_rebuild(self):
        self.use_full_checklist = not self.use_full_checklist

        for path in self.image_files:
            item = self.get_item_from_file(path)
            self.update_known_features(path, item)
        self.disable_feature_tracing()
        self.build_known_feature_checklists()
        self.build_checklist_from_features()
        self.enable_feature_tracing()     

    def switch_checklists(self):
        self.use_full_checklist = not self.use_full_checklist
        self.build_checklist_from_features()

    #Create open dataset action
    def open_dataset(self, event = None, directory = None):
        if len(self.image_files) > 0:
            answer = askyesno(title='confirmation',
                    message='Are you sure that you want to close this datast?')
            if not answer:
                return
            
        self.shadow_registry = {}
        self.feature_index = {}

        self.known_features = {}
        self.clear_ui()
        if(not self.dataset_viewer_window == None):
            print("dataset browser closed")
            self.dataset_viewer_window.close_dataset()
        self.show_initial_frame()

        #Clear the UI and associated variables
        self.file_index = 0
        self.image_files = []

        #Popup folder selection dialog
        if directory is None:
            try:
                self.path = tk.filedialog.askdirectory(
                    parent=self, 
                    initialdir="./dataset",
                    title="Select a dataset")
                if not self.path:
                    return
            except:
                print(traceback.format_exc())
                return
        else:
            self.path = directory                    

        #Get supported extensions
        exts = Image.registered_extensions()
        supported_exts = {ex for ex, f in exts.items() if f in Image.OPEN}

        #Get list of filenames matching those extensions
        files = [pathlib.Path(f).absolute()
                 for f in pathlib.Path(self.path).rglob("*")
                  if isfile(join(self.path, f))]
        
        self.image_files = [
            f for f in files if splitext(f)[1] in supported_exts]  

        self.image_files.sort()

        self.init_shadow_registry()

        #Populate JSONs
        for index, path in enumerate(self.image_files):
            #json_file = splitext(path)[0] + ".json"
            item = self.get_item_from_file(path)
            self.update_known_features(path, item)
            #self.write_item_to_file(item, json_file)

            # awas, inflate shadow registry here
            self.update_shadow_registry(index, item)
            # rebuild the feature index. not very efficient
            self.rebuild_feature_index()

        self.build_known_feature_checklists()

        #Point UI to beginning of queue
        if(len(self.image_files) > 0):
            self.file_index = 0
            self.set_ui(self.file_index)
            self.hide_initial_frame()
        else:
            showwarning(parent=self,
                        title="Empty Dataset",
                        message="No supported images found in dataset")
            self.show_initial_frame()
        
        if(not self.dataset_viewer_window == None):
            self.dataset_viewer_window.open_dataset()

    def generate_lora_subset(self, event = None):
        if len(self.image_files) > 0:
            self.save_unsaved_popup()
            #Pop up dialog to gather information and perform generation
            self.update()
            self.wait_window(generate_lora_subset_popup(self).top)
            self.update()


    def open_auto_tags_editor(self, event = None):
            if(self.auto_tags_window == None):
                self.auto_tags_window = automatic_tags_editor_window(self,self.auto_tags_editor)
            else:
                self.auto_tags_window.close()

    def open_interrogator(self, event = None):
            if(self.auto_tags_window == None):
                self.interrogator_win = interrogator_window(self)
            else:
                self.interrogator_win.close()

    def open_feature_extractor(self, event = None):
            if(self.feature_extractor_window == None):
                self.feature_extractor_window = title_feature_extractor_window(self,self.feature_extractor)
            else:
                self.feature_extractor_window.close()

    def open_logo_remover(self, event = None):
            if(self.feature_extractor_window == None):
                self.logo_remover_window = Logo_Removal.logo_removal_tool_window(self,self.logo_remover)
            else:
                self.logo_remover_window.close()

    def open_dataset_viewer(self, event = None):
            if(self.dataset_viewer_window == None):
                self.dataset_viewer_window = dataset_viewer(self)
            else:
                self.dataset_viewer_window.on_close()
    def update_dataset_viewer_entry(self, source, target):
            if(not self.dataset_viewer_window == None):
                self.dataset_viewer_window.update_entry_file(source,target)

    def open_context_menu(self,parent,menu_options ,event = None):
            if(self.context_menu == None):
                self.context_menu = context_menu(self,parent,menu_options)
            else:
                self.context_menu.close()
                self.context_menu = context_menu(self,parent,menu_options)
    def load_image(self, f):
        try:
            self.image = Image.open(f)
            self.image_resizer()

            prompt = ""
            try:
                self.image.load()  # Needed only for .png EXIF data
                prompt = " ".join(self.image.info['parameters'].split("Negative prompt: ")[0].split())
                prompt = re.sub(r"<.*>", "", prompt).strip().strip(",").strip()
            except:
                pass

            self.prompt = prompt
        except:
            print(traceback.format_exc())


    #Resize image to fit resized window
    def image_resizer(self, e = None):
        try:
            l, t = self.pct_to_coord(self.l_pct, self.t_pct)
            r, b = self.pct_to_coord(self.r_pct, self.b_pct)
        except:
            print(traceback.format_exc())

        tgt_width = self.image_frame.winfo_width() - 4
        tgt_height = self.image_frame.winfo_height() - 4

        if tgt_width < 1:
            tgt_width = 1
        if tgt_height < 1:
            tgt_height = 1

        new_width = int(tgt_height * self.image.width / self.image.height)
        new_height = int(tgt_width * self.image.height / self.image.width)

        if new_width < 1:
            new_width = 1
        if new_height < 1:
            new_height = 1

        if new_width <= tgt_width:
            self.image_width = new_width
            self.image_height = tgt_height
        else:
            self.image_width = tgt_width
            self.image_height = new_height
        resized_image = self.image.resize(
            (self.image_width, self.image_height), 
            Image.LANCZOS)
        self.framed_image = ImageTk.PhotoImage(resized_image)
        #self.image_label.configure(image=self.framed_image)
        center_x = self.sizer_frame.winfo_width() / 2
        center_y = self.sizer_frame.winfo_height() / 2

        try:
            if self.image_handle:
                self.canvas.delete(self.image_handle)
        except:
            print(traceback.format_exc())
        self.image_handle = self.canvas.create_image(center_x, center_y, anchor="center",image=self.framed_image)

        try:
            self.generate_crop_rectangle()
        except:
            print(traceback.format_exc())

    #Remove row from feature table
    def remove_row(self, i: int):
        self.feature_count -= 1
        if i != self.feature_count:
            for j in range(i, self.feature_count):
                self.features[j][0]["var"].set(self.features[j + 1][0]["var"].get())
                self.features[j][1]["var"].set(self.features[j + 1][1]["var"].get())
        self.features[self.feature_count][0]["entry"].grid_remove()
        self.features[self.feature_count][1]["entry"].grid_remove()
        self.features[self.feature_count][0]["var"].set("")
        self.features[self.feature_count][1]["var"].set("")

    def split_component(self, c):
        #Get the parts of speech
        pos = do_get_pos(c)

        wasalnum = False
        def rejoin(tokens):
            joined = ""
            first = True
            for t in tokens:
                if t.text != "":
                    if not first and str.isalnum(t.text[0]) and wasalnum:
                        joined += " "
                    first = False
                    joined += t.text
                    wasalnum = str.isalnum(t.text[-1])
            return joined

        #Rejoin any tokens that were split by a hyphen.
        fixed_pos = []
        it = iter(range(len(pos)))
        for i in it:
            try:
                if i < len(pos) - 2:
                    if pos[i + 1].text[0] == '-':
                        class token_imitator():
                            def __init__(self, pos_, text):
                                self.pos_ = pos_
                                self.text = text
                        joined_item = token_imitator(pos[i + 2].pos_, pos[i].text + "-" + pos[i + 2].text)
                        fixed_pos.append(joined_item)
                        next(it, None)
                        next(it, None)
                    else:
                        fixed_pos.append(pos[i])
                else:
                    fixed_pos.append(pos[i])
            except:
                print(traceback.format_exc())

        #If the final component is recognized as any kind of noun,
        #then use that as the parent.
        last_word_index = -1
        for last_word_token in reversed(fixed_pos):
            if str.isalnum(last_word_token.text[0]):
                break
            last_word_index -= 1
        if len(fixed_pos) > 1 and last_word_token.pos_ in ["NOUN", "PROPN"]:
            parent = last_word_token.text

            #Split by adjective
            splits = []
            this_split = []
            for c in fixed_pos[:last_word_index]:
                this_split.append(c)
                if c.pos_ in ["ADJ", "NUM", "NOUN", "PROPN"]:
                    splits.append(this_split)
                    this_split = []
            
            if this_split != []:
                splits.append(this_split)
                this_split = []

            retval = [parent]
            for s in splits:
                retval.append(parent + treeview_separator + rejoin([x for x in s]))
            
            return retval

        #If nothing else was detected, return the entire component.
        return [c]

    def build_checklist_from_features(self):
        #print("build checklist from features")
        path = relpath(pathlib.Path(self.image_files[self.file_index]).absolute().parent, self.path)
        parents = [str(p).strip() for p in pathlib.Path(path).parents]
        parents.insert(0, str(path).strip())
        self.feature_checklist = []
        if(self.use_full_checklist):
            for x in self.known_feature_checklist_full:
                    if x not in self.feature_checklist:
                        self.feature_checklist.append(x)
        else:
            for p in parents:
                for x in self.known_feature_checklists[str(p)]:
                    if x not in self.feature_checklist:
                        self.feature_checklist.append(x)

        for row in self.features:
            name = row[0]["var"].get().strip()
            if name != '':
                desc = row[1]["var"].get().strip()            
                self.feature_checklist.append((name,True))
                components = desc.split(",")
                for c in components:
                    c = c.strip()
                    if c != '' and c != name:
                        for c_split in self.split_component(c):
                            self.feature_checklist.append(
                                (name + treeview_separator + c_split, True))
        self.feature_checklist.sort()
        if(self.use_full_checklist):
            self.checklist_mode_btn.configure(text= "Features: All")
        else:
            current_dir = basename(self.image_files[self.file_index].absolute().parent) #relpath(pathlib.Path(self.image_files[self.file_index]).absolute().parent, self.path)
            self.checklist_mode_btn.configure(text= "Features: " + str(current_dir))
        self.update_checklist()

    #Callback for when feature is modified
    def feature_modified(self, var: str):
        self.disable_feature_tracing()
        found_i = None
        for i in range(self.feature_count):
            for j in range(len(self.features[i])):
                if self.features[i][j]["var"] is var:
                    found_i = i
                    found_j = j

        for i in range(self.feature_count - 1):
            if(not self.features[i][0]["var"].get()
              and not self.features[i][0]["var"].get()):
                self.remove_row(i)
                if i < found_i:
                    self.features[found_i - 1][found_j - 1]["entry"].focus()
                else:
                    self.features[found_i][found_j]["entry"].focus()


        if(self.features[self.feature_count - 1][0]["var"].get()
           or self.features[self.feature_count - 1][1]["var"].get()):
            self.add_row()


        self.build_checklist_from_features()
        self.enable_feature_tracing()



    #Add entry to feature table
    def add_entry(self, i: int, j: int):
        s = tk.StringVar(None)
        t = s.trace("w", 
                lambda name, index, mode, var=s: self.feature_modified(var))
        if j == 0:
            e = tk.Entry(self.features_group, 
                         textvariable=s, 
                         width=1,
                         justify="right")
        else:
            e = tk.Entry(self.features_group, 
                         textvariable=s, 
                         width=3,
                         justify="left")            
        e.grid(row=i + 1, column=j, 
               sticky="ew")
        e.bind('<Control-a>', self.select_all)        
        e.bind("<Control-t>", self.update_ui_automatic_tags)
        return {"var":s, "entry":e, "trace": t}

    #Add row to feature table
    def add_row(self):
        self.feature_count += 1
        if self.feature_count > len(self.features):
            row = []
            for j in range(2):
                row.append(self.add_entry(self.feature_count, j))
            self.features.append(row)
        else:
            self.features[self.feature_count - 1][0]["entry"].grid()
            self.features[self.feature_count - 1][1]["entry"].grid()


    def get_item_from_ui(self):

        item = self.get_defaults()
        try: 
            item["artist"] = self.artist_name.get()
        except: 
            print(traceback.format_exc())

        try: 
            item["style"] = self.style.get()
        except: 
            print(traceback.format_exc())

        try:
            item["title"] = self.title_var.get()
        except:
            print(traceback.format_exc())
        try:
            item["rating"] = self.rating.get()
        except:
            print(traceback.format_exc())

        try:
            item["summary"] = ' '.join(self.summary_textbox.get("1.0", "end").split())
        except:
            print(traceback.format_exc())

        try:
            item["crop"] = [
                self.l_pct,
                self.t_pct,
                self.r_pct,
                self.b_pct
            ]
        except:
            print(traceback.format_exc())

        try:
            features = {}
            for i in range(self.feature_count):
                key = self.features[i][0]["var"].get()
                if(key):
                    extant = ""
                    val = self.features[i][1]["var"].get()
                    if key in features:
                        extant = features[key] + ", "
                    features.update({key: extant + val})
            item["features"] = features
        except:
            print(traceback.format_exc())

        try:
            item["automatic_tags"] = ' '.join(self.automatic_tags_textbox.get("1.0", "end").split())
        except:
            print(traceback.format_exc())

        return item
    
    def get_defaults(self, path = None):
        if path is None:
            if len(self.image_files) == 0:
                path = "./dataset/default.png"
            else:
                path = self.image_files[self.file_index]
                
        defaults = {"lora_tag_helper_version": 1,
                    "title":splitext(pathlib.Path(path).name)[0],
                    "artist": "unknown",
                    "style": "photo",
                    "rating": 0,
                    "summary": self.prompt,
                    "features": {},
                    "crop": [0, 0, 1, 1],
                    "automatic_tags": ""}

        if len(self.image_files) == 0:
            return defaults
        
        path = pathlib.Path(path)        
        paths = [p for p in reversed(pathlib.Path(path).parents) if p not in pathlib.Path(self.path).parents]

        for p in paths:
            json_file = p / "defaults.json"
            if isfile(json_file):
                try:
                    with open(json_file) as f:
                        features = {}
                        if "features" in defaults:
                            features.update(defaults["features"])
                        defaults.update(json.load(f))
                        if "features" in defaults:
                            features.update(defaults["features"])
                        defaults["features"] = features
                except:
                    pass
        return defaults
    
    def get_item_from_file(self, path):
        #Read filename into title
        item = self.get_defaults(path)

        #If .txt available, read into automated caption
        txt_file = splitext(path)[0] + ".txt"
        try:
            with open(txt_file) as f:
                item["automatic_tags"] = ' '.join(f.read().split())
        except (FileNotFoundError) as error:
            pass

        #If available, parse JSON into fields
        json_file = splitext(path)[0] + ".json"
        try:
            with open(json_file) as f:
                json_item = json.load(f)
                item.update(json_item)
        except FileNotFoundError:
            pass

        try:
            if item["lora_tag_helper_version"] > 1:
                print("Warning: file generated by newer version of lora_tag_helper")
        except:
            print(traceback.format_exc())

        return item


    def write_item_to_file(self, item, json_file):
        try:
            with open(json_file, "w") as f:
                json.dump(item, f, indent=4)
        except:
            showerror(parent=self,
                      title="Couldn't save JSON",
                      message="Could not save JSON file")
            print(traceback.format_exc())
        
    def update_known_feature_checklists(self):
        path = relpath(pathlib.Path(self.image_files[self.file_index]).absolute().parent, self.path)
        temp_checklist = self.feature_checklist
        for i in range(len(temp_checklist)):
            temp_checklist[i] = (temp_checklist[i][0], False)
        if(self.use_full_checklist):
            self.known_feature_checklist_full = temp_checklist
        else:
            self.known_feature_checklists[path] = temp_checklist

        

    #Add UI elements for save JSON button
    def save_json(self, event = None):
        file = self.image_files[self.file_index]
        item = self.get_item_from_ui()
        defaults = self.get_defaults()
        trimmed_item = {x:item[x] for x in item if x in defaults and item[x] != defaults[x]}
        self.write_item_to_file(
            trimmed_item,
            splitext(file)[0] + ".json")

        self.update_shadow_registry(self.file_index, trimmed_item)
        # rebuild the feature index. not very efficient
        self.rebuild_feature_index()
        self.update_known_feature_checklists()

    def autosave_toggle(self):
       print("Autosave toggled " + str(self.autosave.get()))  
         
    #Update automatic tags in JSON for image file
    def update_automatic_tags(self, path, popup=False):
        if not interrogator_ready:
            showwarning(parent=self,
                        title="Not ready",
                        message="The interrogator is not yet ready.")
            return        
        json_file = splitext(path)[0] + ".json"
        item = self.get_item_from_file(json_file)

        if popup:
            item["automatic_tags"] = run_func_with_loading_popup(
                self,
                lambda: interrogate_automatic_tags(path,self.settings.interrogator_settings), 
                "Interrogating Image...", 
                "Interrogating Image...")            
        else:
            item["automatic_tags"] = interrogate_automatic_tags(path,self.settings.interrogator_settings)

        if "automatic_tags" not in item or not item["automatic_tags"]:
            item["automatic_tags"] = ""

        defaults = self.get_defaults(json_file)
        trimmed_item = {x:item[x] for x in item if x in defaults and item[x] != defaults[x]}

        self.write_item_to_file(trimmed_item, json_file)

    #Update automatic tags in all JSON files
    def update_all_automatic_tags(self, event = None):
        if not interrogator_ready:
            showwarning(parent=self,
                        title="Not ready",
                        message="The interrogator is not yet ready.")
            return        

        self.save_unsaved_popup()
        popup = tk.Toplevel(self)
        tk.Label(popup, text="Processing subset images...").grid(row=0,column=0)
        progress_var = tk.DoubleVar()
        progress_var.set(0)
        progress_bar = tk.ttk.Progressbar(popup, variable=progress_var, maximum=100)
        progress_bar.grid(row=1, column=0)#.pack(fill=tk.X, expand=1, side=tk.BOTTOM)
        popup.pack_slaves()
        i = 0
        for f in self.image_files:
            #Update progress bar
            progress_var.set(100 * i / len(self.image_files))
            popup.update()
            i = i + 1            
            self.update_automatic_tags(f, popup=False)
        popup.destroy()
        self.update_ui_automatic_tags()

    #Update automatic tags in all JSON files
    def update_ui_automatic_tags(self, event = None):
        if not interrogator_ready:
            showwarning(parent=self,
                        title="Not ready",
                        message="The interrogator is not yet ready.")
            return "break"    
        if len(self.image_files) > 0:
            self.save_unsaved_popup()
            self.update_automatic_tags(self.image_files[self.file_index])
            self.set_ui(self.file_index)
        return "break"

    def add_autotag_to_editor(self, event = None):
        selected_tag = self.automatic_tags_textbox.selection_get()
        if(not self.auto_tags_window):
            self.auto_tags_window = automatic_tags_editor_window(self,self.auto_tags_editor)     
        if (len(selected_tag) > 0):
            print("Add autotag " + selected_tag)
            tags = selected_tag.split(", ")
            for tag in tags:
                if(not tag == "" and not tag == " "):
                    self.auto_tags_window.add_entry(tag.replace(",",""))


    #Add UI elements for prev file button
    def prev_file(self, event = None):
        if self.file_index <= 0:
            self.file_index = 0
            return #Nothing to do if we're at first index.
        
        #Pop up unsaved data dialog if needed
        self.save_unsaved_popup()

        #Point UI to previous item in queue
        self.clear_ui()
        self.file_index -= 1
        self.set_ui(self.file_index)
        self.artist_name_entry.focus()
        class event_imitator():
            def __init__(self, widget):
                self.widget = widget
        self.select_all(event_imitator(self.artist_name_entry))




    #Add UI elements for next file button
    def next_file(self, event = None):
        if self.file_index >= len(self.image_files) - 1:
            self.file_index = len(self.image_files) - 1
            return #Nothing to do if we're at first index.
                
        #Pop up unsaved data dialog if needed
        self.save_unsaved_popup()

        #Point UI to next item in queue
        self.clear_ui()
        self.file_index += 1
        self.set_ui(self.file_index)
        self.artist_name_entry.focus()
        class event_imitator():
            def __init__(self, widget):
                self.widget = widget
        self.select_all(event_imitator(self.artist_name_entry))

    def save_defaults(self, event = None):
        if len(self.image_files) == 0:
            showerror(parent=self, title="Error", message="Dataset must be open")
            return
        #Pop up dialog to save default settings for path
        self.update()
        self.wait_window(save_defaults_popup(self).top)
        self.update()

    def add_features_from_summary(self, event = None):
        text = self.summary_textbox.get("1.0", "end")
        components = text.split(',')
        words = []
        for c in components:
            words.extend(c.split())

        features = {f[0] for f in self.feature_checklist}
        active_features = {f[0] for f in self.feature_checklist if f[1]}

       
        features_to_add = {f for f in features if f in words and f not in active_features}

        for i in range(self.feature_count):
            if self.features[i][0]["var"].get() in features_to_add:
                features_to_add.remove(self.features[i][0]["var"].get())


        self.disable_feature_tracing()
        i = self.feature_count - 1
        try:
            for f in features_to_add:
                self.add_row()
                self.features[i][0]["var"].set(f)
                i += 1
        except:
            print(traceback.format_exc())
        self.enable_feature_tracing()
        self.feature_modified(self.features[0][0]["var"])

    def rename_feature(self,iid, event = None):
        print("rename feature")
        if len(self.image_files) > 0:
            self.save_unsaved_popup()
            #Pop up dialog to rename features
            self.update()
            self.wait_window(rename_feature_popup(self,iid).top)
            self.update()     

    def modify_feature_across_dataset(self, feature_branch, changed_text, remove):
        for file in self.image_files:
            item = self.get_item_from_file(file)
            item_changed = False
            feature_to_change = ""
            if "features" in item:
                for feature in item["features"]:
                    if feature == feature_branch[len(feature_branch) - 1]:
                        if(len(feature_branch) > 1):
                            components = item["features"][feature].split(",")
                            component_to_remove = -1
                            for c in range(0, len(components)):  
                                comp = components[c].strip()
                                c_split_list = self.split_component(comp)
                                component_changed = False
                                component_segment_to_remove = -1
                                componentName = c_split_list[0] + treeview_separator
                                for x in range(0, len(c_split_list)):

                                    if(x >= 0):
                                        sub_name_only = c_split_list[x].replace(componentName,'')
                                        c_split_list[x] = sub_name_only
                                    if(c_split_list[x] == feature_branch[0]):
                                        c_split_list[x] = changed_text
                                        component_segment_to_remove = x
                                        component_changed = True

                                if component_changed:
                                    if(remove):
                                        if(c_split_list[0] == feature_branch[0]):
                                            component_to_remove = c
                                        else:
                                            del c_split_list[component_segment_to_remove]      
                                    c_split_list = c_split_list[1:] + [c_split_list[0]]
                                    components[c] = " ".join(c_split_list)
                                    item_changed = True

                            if item_changed:
                                if(remove and component_to_remove > -1):
                                    del components[component_to_remove]
                                item["features"][feature] = ",".join(components)
                        else:
                            feature_to_change = feature
                            item_changed = True
            if feature_to_change == feature_branch[len(feature_branch) - 1]:
                f_val = item["features"][feature_to_change]
                del item["features"][feature_to_change]
                if(not remove):
                    item["features"][changed_text] = f_val            
                            
            if item_changed:
                defaults = self.get_defaults()                
                trimmed_item = {x:item[x] for x in item if x in defaults and item[x] != defaults[x]}
                self.write_item_to_file(
                    trimmed_item,
                    splitext(file)[0] + ".json")
                self.update_known_features(self.image_files[self.file_index], item)
        # Update the UI        
        self.disable_feature_tracing()
        self.build_known_feature_checklists()
        self.set_ui(self.file_index)
        self.enable_feature_tracing()       

    def reset(self, event = None):
        self.set_ui(self.file_index, self.get_defaults())
        

    def go_to_image(self, event = None, file = None):
        if not file:
            file = tk.filedialog.askopenfilename(parent=self.root_frame, initialdir=self.path, title="Select an image in the dataset", filetypes =[('Supported images', [f"*{x}" for x in Image.registered_extensions()])])
            if file:
                file = pathlib.Path(file).absolute()
        if file.is_dir():
            i = 0
            for f in self.image_files:
                if str(f).startswith(str(file)):
                    self.file_index = i
                    self.set_ui(i)
                    break
                i += 1
        elif file:
            try:
                i = self.image_files.index(pathlib.Path(file))
                self.file_index = i
                self.set_ui(i)
            except ValueError:
                print(traceback.format_exc())
                print(f"Warning: Supplied path {file} is not an image in the dataset. Ignoring.")


        
    #Ask user if they want to save if needed
    def save_unsaved_popup(self):
        if(len(self.image_files) == 0):
           return
        json_file = "".join(splitext(self.image_files[self.file_index])[:-1]) + ".json"
        answer = False
        if not self.autosave.get():
            #print("JSON differences: " + str(diff(self.get_item_from_ui(), self.get_item_from_file(json_file))))
            if(self.get_item_from_ui() != self.get_item_from_file(json_file)):
                answer = askyesno(parent=self,
                                title='Save unsaved data?',
                                message='You have unsaved changes. Save JSON now?')

        if answer or self.autosave.get():
            defaults = self.get_defaults()
            item = self.get_item_from_ui()
            trimmed_item = {x:item[x] for x in item if x in defaults and item[x] != defaults[x]}
            self.write_item_to_file(trimmed_item, json_file)
            self.update_known_feature_checklists()

    def select_all(self, event):
        # select text
        try:
            event.widget.select_range(0, 'end')
        except:
            print(traceback.format_exc())
            event.widget.tag_add("sel", "1.0", "end")

        # move cursor to the end
        try:
            event.widget.icursor('end')
        except:
            print(traceback.format_exc())
            event.widget.mark_set("insert", "end")

        #stop propagation
        return 'break'

    #Create quit action
    def quit(self, event = None):
        self.save_unsaved_popup()
        self.save_app_settings()
        self.destroy()


#Application entry point
if __name__ == "__main__":
    global app
    #Instantiate the application
    app = lora_tag_helper()
    #Let the user do their thing
    app.mainloop()

