import os
from os import listdir, makedirs, walk, getcwd, utime, remove, sep, scandir
from os.path import isfile, join, splitext, exists, getmtime, relpath, dirname, basename
import photoshop.api as ps
from photoshop import Session
from PIL import ImageTk, Image
import json
import traceback
import pathlib
import shutil
from tkinterdnd2 import DND_FILES, TkinterDnD
from tkinter.messagebox import askyesno, showinfo, showwarning, showerror
from tkinter import simpledialog, scrolledtext
import tkinter.filedialog as filedialog
import tkinter.ttk
import tkinter.font
import tkinter as tk
from tkinter import ttk
import pynput
import imagehash
import tag_helper
import glob


class logo_removal_tool(object):
    def __init__(self):
        self.mask_set_path = ""
        self.mask_entries = []
        self.use_masks = False
        self.check_res = True
        self.make_backup = True
        self.reset_crop = True
        self.use_selected_crop = True
        self.compare_images = True
        self.debug_save_cutout = True
class logo_removal_tool_window(object):
    def __init__(self,parent,tool):
        dirname = os.path.dirname(__file__)
        self.removal_tool = tool
        self.parent = parent
        self.folder_path = dirname
        self.current_backup_file = ""

        self.masks_folder = os.path.join(self.folder_path,"masks") #folder_path + "\masks" 
        self.input_folder = self.folder_path + "\input"
        self.output_folder = self.folder_path + "\output"
        self.backup_folder = self.folder_path + "\img_backups"
        self.cutout_check_folder = self.folder_path + "\cutout_check"
        self.show_ref = False
        self.ps_app = ps.Application()
        #self.ps_app.displayDialogs = ps.DialogModes.DisplayNoDialogs
        self.parent.events.on_set_ui += self.on_ui_set
        self.create_ui()

    #Create the frame for form display
    def create_ui(self):

        self.top = tk.Toplevel(self.parent)
        self.top.title("Title Feature Extraction")
        self.top.wm_minsize(420, 500)
        #self.top.wm_maxsize(420,800)
        self.top.wm_resizable(True,True)
        self.top.transient(self.parent)
        self.top.wm_protocol("WM_DELETE_WINDOW", self.on_close)

        self.top.grid_rowconfigure(0, weight=1) # this needed to be added
        self.top.grid_columnconfigure(0, weight=1) # as did this
        self.top.grid_columnconfigure(1, weight=1) # as did this

        self.form_frame = tk.Frame(self.top,
                               width=420, height=400, 
                               bd=1,
                               relief=tk.RAISED)
        self.form_frame.columnconfigure(0, weight = 0)
        self.form_frame.columnconfigure(1, weight = 0)
        self.form_frame.grid(row=0, column=0, 
                              padx=0, pady=0, 
                              sticky="nsew")
        

        self.add_mode_buttons()
        self.add_crop_settings_box()
        self.add_mask_settings_box()
        self.add_mask_entry_box()
        self.add_settings_box()
        self.add_form_buttons()

        self.set_selection_mode()
        self.check_for_backup()
    def add_mode_buttons(self):

        self.selection_toggle_box = tk.Frame(self.form_frame, 
                                   borderwidth=2,
                                   relief='sunken',)
        self.selection_toggle_box.grid(row=0, column=0, padx=(5, 5), pady=5, sticky="nsew")
        self.selection_toggle_box.columnconfigure(0,weight=1)
        self.selection_toggle_box.columnconfigure(1,weight=1)

        self.selection_toggle_btn1 = tk.Button(self.selection_toggle_box, 
                                  text="Use internal cropping", 
                                  command=self.toggle_selection_crop)
        self.selection_toggle_btn1.grid(row=0, column=0, 
                           padx=5, pady=5, 
                           sticky="ew")
        self.selection_toggle_btn2 = tk.Button(self.selection_toggle_box, 
                                  text="Use Photoshop Masks", 
                                  command=self.toggle_selection_masks)
        self.selection_toggle_btn2.grid(row=0, column=1, 
                           padx=5, pady=5, 
                           sticky="ew")

    def add_mask_settings_box(self):
        self.mask_settings_box = tk.Frame(self.form_frame, 
                                   borderwidth=2,
                                   relief='sunken',)
        self.mask_settings_box.grid(row=1, column=0, padx=(5, 5), pady=5, sticky="nsew")

        self.mask_directory_box = tk.Frame(self.mask_settings_box, 
                                   borderwidth=2,
                                   relief='sunken',)
        self.mask_directory_box.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")  
        self.mask_directory_box.columnconfigure(0,weight=0)
        self.mask_directory_box.columnconfigure(1,weight=1)

        mask_path_label = tk.Label(self.mask_directory_box, text="Masks Directory: ")
        mask_path_label.grid(row=0, column=0,
                             padx=(10, 0), pady=5, 
                             sticky="w") 
        self.mask_path_btn = tk.Button(self.mask_directory_box, 
                                  text="Select directory containing masks", 
                                  command=self.select_masks_dir)
        self.mask_path_btn.grid(row=0, column=1, 
                           padx=5, pady=5, 
                           sticky="ew")
        
        self.mask_bottom_box = tk.Frame(self.mask_settings_box, 
                                   borderwidth=2,
                                   relief='sunken',)
        self.mask_bottom_box.grid(row=2, column=0, padx=5, pady=5, sticky="nsew")  
        self.mask_bottom_box.columnconfigure(0,weight=0)
        self.mask_bottom_box.columnconfigure(1,weight=1)      

        self.compare_images = tk.BooleanVar(None)
        self.compare_images.set(self.removal_tool.reset_crop )
        self.compare_images.trace_add('write', self.toggle_compare_images)
        compare_images_chk = tk.Checkbutton(
            self.mask_bottom_box,
            var=self.compare_images,
            text=f"Compare Image cutout ")
        compare_images_chk.grid(row=0, column=0, padx=5, pady=5, sticky="w")    

        pass_threshold_label = tk.Label(self.mask_bottom_box, text="ImageHash threshold")
        pass_threshold_label.grid(row=1, column=0,
                             padx=(10, 0), pady=5, 
                             sticky="w")

        self.pass_threshold = tag_helper.NumericEntry(self.mask_bottom_box,
                                     justify="left")
        self.pass_threshold.set(12)
        self.pass_threshold.grid(row=1, column=1, 
                             padx=(0, 5), pady=5, 
                             sticky="w")                     
        
    def add_crop_settings_box(self):
        self.crop_settings_box = tk.Frame(self.form_frame, 
                                   borderwidth=2,
                                   relief='sunken',)
        self.crop_settings_box.grid(row=1, column=0, padx=(5, 5), pady=5, sticky="nsew")

        self.reset_crop = tk.BooleanVar(None)
        self.reset_crop.set(self.removal_tool.reset_crop )
        self.reset_crop.trace_add('write', self.toggle_reset_crop)
        reset_crop_chk = tk.Checkbutton(
            self.crop_settings_box,
            var=self.reset_crop,
            text=f"Reset cropping after ")
        reset_crop_chk.grid(row=2, column=0, padx=5, pady=5, sticky="w") 

        self.use_selected_crop = tk.BooleanVar(None)
        self.use_selected_crop.set(self.removal_tool.use_selected_crop )
        self.use_selected_crop.trace_add('write', self.toggle_use_selected_crop)
        use_selected_crop_chk = tk.Checkbutton(
            self.crop_settings_box,
            var=self.use_selected_crop,
            text=f"Use cropping from active file only")
        use_selected_crop_chk.grid(row=3, column=0, padx=5, pady=5, sticky="w") 

    def add_mask_entry_box(self):

        # self.show_ref_btn = tk.Button(self.form_frame, 
        #                           text="Show Reference Image", 
        #                           command=self.toggle_ref_image)
        # self.show_ref_btn.grid(row=0, column=0, 
        #                    padx=5, pady=5, 
        #                    sticky="ew")
        self.scroll_frame = tag_helper.ScrollableFrame(self.mask_settings_box)
        self.scroll_frame.grid(row=1, column=0, padx=(5, 5), pady=5, sticky="nsew")
        #self.scroll_frame.configure(width= 120)
        self.scroll_frame.columnconfigure(0, weight=1)
        self.scroll_frame.scrollable_frame.columnconfigure(0, weight=1)
        # self.scroll_frame.columnconfigure(tuple(range(8)), weight=0)
        # self.scroll_frame.scrollable_frame.columnconfigure(tuple(range(8)), weight=0)
        #self.scroll_frame.scrollable_frame.columnconfigure(0,weight=1)

    def add_settings_box(self):

        self.settings_box = tk.Frame(self.form_frame, 
                                   borderwidth=2,
                                   relief='sunken',)
        self.settings_box.grid(row=2, column=0, padx=(5, 5), pady=5, sticky="nsew")
        
        self.check_res = tk.BooleanVar(None)
        self.check_res.set(self.removal_tool.check_res)
        self.check_res.trace_add('write', self.toggle_check_res)
        check_res_chk = tk.Checkbutton(
            self.settings_box,
            var=self.check_res,
            text=f"Same resolution only")
        check_res_chk.grid(row=2, column=0, padx=5, pady=5, sticky="w") 

        self.set_backup = tk.BooleanVar(None)
        self.set_backup.set(self.removal_tool.make_backup)
        self.set_backup.trace_add('write', self.toggle_backup)
        set_features_chk = tk.Checkbutton(
            self.settings_box,
            var=self.set_backup,
            text=f"Backup images")
        set_features_chk.grid(row=3, column=0, padx=5, pady=5, sticky="w") 

          
    def add_form_buttons(self):

        self.controlsbox = tk.Frame(self.form_frame, 
                                   borderwidth=2,
                                   relief='sunken',)
        self.controlsbox.grid(row=3, column=0, padx=(5, 5), pady=5, sticky="nsew")
        self.controlsbox.columnconfigure(0,weight= 1)
        self.controlsbox.columnconfigure(1,weight= 1)

        
        self.restore_img_btn = tk.Button(self.controlsbox, 
                                  text="Restore from backup", 
                                  command=self.restore_from_backup)
        self.restore_img_btn.grid(row=1, column=0, 
                           padx=5, pady=5, 
                           sticky="ew",columnspan= 2)
        self.restore_img_btn.bind_all("<Control-r>", self.restore_from_backup,"+" )

        self.process_images_btn = tk.Button(self.controlsbox, 
                                  text="Process Images", 
                                  command=self.process_images)
        self.process_images_btn.grid(row=2, column=0, 
                           padx=5, pady=5, 
                           sticky="ew",columnspan= 2)
        
        self.process_images_btn = tk.Button(self.controlsbox, 
                                  text="test", 
                                  command=self.Test)
        self.process_images_btn.grid(row=3, column=0, 
                           padx=5, pady=5, 
                           sticky="ew",columnspan= 2)

    def Test(self):
        file = self.parent.image_files[self.parent.file_index]
        item = self.parent.get_item_from_file(file)
        if("crop" in item):
            target_crop = item["crop"]
            print("target bounds: " + str(self.bounds_from_cropping(target_crop)))

    def close(self):
        self.on_close()
        #self.top.grab_release()
        return "break"
    def on_close(self):
        self.parent.events.on_set_ui -= self.on_ui_set
        self.restore_img_btn.unbind_all("<Control-r>")
        self.top.destroy()
        self.parent = None

    def toggle_backup(self, *args):
        self.removal_tool.make_backup = self.set_backup.get()
    def toggle_check_res(self, *args):
        self.removal_tool.check_res = self.check_res.get()
    def toggle_reset_crop(self, *args):
        self.removal_tool.reset_crop = self.reset_crop.get()
    def toggle_compare_images(self, *args):
        self.removal_tool.compare_images = self.compare_images.get()
    def toggle_use_selected_crop(self,*args):
        self.removal_tool.use_selected_crop = self.use_selected_crop.get()
    def toggle_selection_crop(self):
        self.removal_tool.use_masks = False
        self.set_selection_mode()
    def toggle_selection_masks(self):
        self.removal_tool.use_masks = True
        self.set_selection_mode()
    def set_selection_mode(self):
        if self.removal_tool.use_masks:

            self.selection_toggle_btn2.config(relief="sunken",fg= tag_helper.theme.color("text"))
            self.selection_toggle_btn1.config(relief="raised",fg= tag_helper.theme.color("text_disabled"))

            self.mask_settings_box.grid(row=1, column=0, padx=(5, 5), pady=5, sticky="nsew")
            self.crop_settings_box.grid_forget()
        else:
            self.selection_toggle_btn1.config(relief="sunken",fg= tag_helper.theme.color("text"))
            self.selection_toggle_btn2.config(relief="raised",fg= tag_helper.theme.color("text_disabled"))

            self.mask_settings_box.grid_forget()
            self.crop_settings_box.grid(row=1, column=0, padx=(5, 5), pady=5, sticky="nsew")

    def select_masks_dir(self, directory = None):
         #Popup folder selection dialog
        if directory is None:
            try:
                self.removal_tool.mask_set_path = filedialog.askdirectory(
                    parent=self.top, 
                    initialdir=self.masks_folder,
                    title="Select masks folder")
                if not self.removal_tool.mask_set_path:
                    return
            except:
                print(traceback.format_exc())
                return
        else:
            self.removal_tool.mask_set_path = directory  

        self.mask_path_btn.configure(text= str(basename(self.removal_tool.mask_set_path)))

        self.load_masks() 



    def load_masks(self):
        self.clear_masks()
        for filename in listdir(self.removal_tool.mask_set_path):
            if filename.endswith('.psd'):#filename.endswith('.png') or filename.endswith('.jpg'):

                path = join(self.removal_tool.mask_set_path, filename)
    
                print("mask: " + path + " added")
                
                mask_entry = mask_ui_entry(self.scroll_frame.scrollable_frame,self,len(self.removal_tool.mask_entries))
                ps_doc = self.ps_app.open(path)
                mask_entry.path = path
                mask_entry.width = round(ps_doc.width)
                mask_entry.height = round(ps_doc.height)
                #mask_entry.ps_doc = ps_doc
                ps_doc.selection.load(ps_doc.channels.getByName("Mask"),ps.SelectionType.ReplaceSelection, False)
                if(not os.path.isfile(splitext(mask_entry.path)[0] + ".png")):
                    ps_doc.saveAs(splitext(path)[0].__str__(), ps.PNGSaveOptions(), True)
                ps_bounds = ps_doc.selection.bounds
                print("MASK selection: " + str(ps_bounds))
                bounds = (
                (ps_bounds[0], ps_bounds[1]),
                (ps_bounds[0], ps_bounds[3]),
                (ps_bounds[2],  ps_bounds[3]),
                (ps_bounds[2], ps_bounds[1]),
                )
                mask_entry.mask_bounds = bounds
                ps_doc.selection.load(ps_doc.channels.getByName("Compare"),ps.SelectionType.ReplaceSelection, False)
                mask_entry.compare_bounds = ps_doc.selection.bounds
                print("MASK compare bounds: " + str(mask_entry.compare_bounds))
                print("jpg path: " + str(splitext(mask_entry.path)[0] + ".png"))
                if(os.path.isfile(splitext(mask_entry.path)[0] + ".png")):
                    print("jpg path exists")
                    mask_entry.compare_cutout = self.image_cutout_bounds(splitext(mask_entry.path)[0] + ".png",mask_entry.compare_bounds)
                else:
                    print("jpg path doesn't exist")
                    mask_entry.compare_cutout = self.image_cutout_bounds(mask_entry.path,mask_entry.compare_bounds)
                if(self.removal_tool.debug_save_cutout):
                    mask_entry.compare_cutout.save(join(self.cutout_check_folder + "\mask", splitext(basename(mask_entry.path))[0] + ".png"))
                mask_entry.create_ui()
                ps_doc.selection.deselect()
                #Close Photoshop document and add mask to list
                ps_doc.close(ps.SaveOptions.DoNotSaveChanges)
                self.removal_tool.mask_entries.append(mask_entry)

                

    def clear_masks(self):
        for mask in self.removal_tool.mask_entries:
            mask.delete_entry()
        self.removal_tool.mask_entries.clear()
    def process_images(self):
        # Iterate over all files in the folder
        selected_item = self.parent.get_item_from_file(self.parent.image_files[self.parent.file_index])
        source_width = 0
        source_height = 0
        if(not self.removal_tool.use_masks):
            with Image.open(self.parent.image_files[self.parent.file_index]) as img:
                source_width = img.width
                source_height = img.height
        if(not self.parent.dataset_viewer_window == None):
            progress_counter = 0
            progress_max = len(self.parent.dataset_viewer_window.selected_entries)
            for entry in self.parent.dataset_viewer_window.selected_entries:
                progress_counter += 1
                print("processing start: " + basename(entry.file))
                if(self.removal_tool.use_masks):
                    self.pick_mask(entry.file)
                else:
                    self.use_cropping(entry.file,selected_item,source_width,source_height)
                print(os.path.basename(entry.file) + " processed " + str(progress_counter) + "/" + str(progress_max))
        else:
            selected_file = self.parent.image_files[self.parent.file_index]
            if(self.removal_tool.use_masks):
                self.pick_mask(selected_file)
            else:
                self.use_cropping(selected_file,selected_item,source_width,source_height)
        print("Logo Removal Done!")

    def use_cropping(self,file,selected_item,source_width,source_height):
        requirements_fullfilled = True
        #Check if target has the same res if cropping from selected file is used
        if(self.removal_tool.use_selected_crop and self.removal_tool.check_res):
            print("Checking res!")
            with Image.open(file) as img:
                if(not img.width == source_width or not img.height == source_height):
                    print("not same res!")
                    requirements_fullfilled = False
        #check file type
        if(splitext(file)[1] == ".png"):
            requirements_fullfilled = False
        if(requirements_fullfilled):
            item = self.parent.get_item_from_file(file)
            if("crop" in item):
                img_width = 0
                img_height = 0
                with Image.open(file) as img:
                    img_width = img.width
                    img_height = img.height
                target_crop = item["crop"]
                print(str(basename(file)) + " target crop: " + str(target_crop))
                if(self.removal_tool.use_selected_crop):
                    print("use selected crop")
                    target_crop = selected_item["crop"]
                if target_crop != [0, 0, 1, 1]:
                    self.reset_crop_in_tool(item,file)    
                    self.content_aware_fill(file,self.bounds_from_cropping(target_crop,img_width,img_height))
                else:
                    print(basename(file) + " couldn't be processed, no croping mask was set.")      
            else:
                print(basename(file) + " couldn't be processed, no croping mask field in item.")
        else:
            print(basename(file) + " skipped, requirements not fulfilled.")
    def pick_mask(self,image_path):
            # Process the image
            choosen_mask = None
            with Image.open(image_path) as img:
                last_compare_success = int(self.pass_threshold.get())
                for mask in self.removal_tool.mask_entries:
                    requirements_fullfilled = True
                    if(self.removal_tool.check_res):
                        if(not img.width == mask.width or not img.height == mask.height):
                            print("Not same Size: " + basename(mask.path) + " H:" + str(mask.height) + " W:" + str(mask.width))
                            print("Not same Size: " + basename(mask.path) + " H:" + str(img.height) + " W:" + str(img.width))
                            requirements_fullfilled = False
                    #check file type
                    if(splitext(image_path)[1] == ".png"):
                        print("Wrong Format " + basename(mask.path))
                        requirements_fullfilled = False
                    if(requirements_fullfilled):
                        if(self.compare_images):
                            cutout = self.image_cutout_bounds(image_path,mask.compare_bounds)
                            compare_value = self.compare_image_cutouts(cutout, mask.compare_cutout)
                            print(basename(image_path) + " Compare value: " + str(compare_value) + " to mask: " + mask.path)
                            if(compare_value < last_compare_success):
                                if(self.removal_tool.debug_save_cutout):
                                    cutout.save(join(self.cutout_check_folder,  splitext(basename(image_path))[0] + " mask_" + splitext(basename(mask.path))[0] +  " CV_" + str(compare_value) + ".png"))
                                    #cutout.save(join(self.cutout_check_folder, basename(image_path) + " mask: " + basename(mask.path) + " CV:" + str(compare_value)))
                                last_compare_success = compare_value
                                choosen_mask = mask
                        else:
                            choosen_mask = mask

            if(not choosen_mask == None):
                self.content_aware_fill(image_path,choosen_mask.mask_bounds,choosen_mask)
            else:
                print(basename(image_path) + " couldn't be processed, no matching mask was found.")
                
    def reset_crop_in_tool(self, item, file):
        if(self.removal_tool.reset_crop):
            item["crop"] = [0, 0, 1, 1]
            defaults = self.parent.get_defaults()
            trimmed_item = {x:item[x] for x in item if x in defaults and item[x] != defaults[x]}
            self.parent.write_item_to_file(
                trimmed_item,
                splitext(file)[0] + ".json")
        
    def bounds_from_cropping(self,crop, width, height):
            x_min = crop[0] * width
            y_min = crop[1] * height
            x_max = crop[2] * width
            y_max = crop[3] * height
            bounds = (
                (x_min, y_min),
                (x_min, y_max),
                (x_max, y_max),
                (x_max, y_min),
                )
            return bounds

    def compare_image_cutouts(self,target_cutout, compare_cutout):
        target_hash = imagehash.colorhash(target_cutout) 
        compare_hash = imagehash.colorhash(compare_cutout)


        return compare_hash - target_hash

    def image_cutout(self,path,crop): 
            if crop != [0, 0, 1, 1]:            
                with Image.open(path) as cropped_img:
                    cropped_img = cropped_img.crop(
                        (crop[0] * cropped_img.width,
                         crop[1] * cropped_img.height,
                         crop[2] * cropped_img.width, 
                         crop[3] * cropped_img.height))
                    return cropped_img
                
    def image_cutout_bounds(self,path,bounds): 
                with Image.open(path) as cropped_img:
                    cropped_img = cropped_img.crop(
                        (bounds[0],
                         bounds[1],
                         bounds[2], 
                         bounds[3]))
                    return cropped_img
    # Function to process an image
    def content_aware_fill(self,image_path, bounds, mask = None):
        with Session() as ps:
            image_path_without_extension = splitext(image_path)[0]
            doc = self.ps_app.open(image_path.__str__())
            #Load the mask image as a selection
            if(mask == None):
                doc.selection.select(bounds)
            else:
                mask_doc = self.ps_app.open(mask.path)
                self.ps_app.activeDocument = doc
                #mask_doc.selection.load(mask_doc.channels.getByName("Mask"),ps.SelectionType.ReplaceSelection, False)
                #doc.channels.add(mask_doc.channels.getByName("Mask"))
                #selAlpha = doc.channels.add()
                #mask_doc.selection.store(selAlpha)
                #doc.selection.select(mask.mask_bounds)
                doc.selection.load(mask_doc.channels.getByName("Mask"),ps.SelectionType.ReplaceSelection, False)
                mask_doc.close(ps.SaveOptions.DoNotSaveChanges)

            if(self.removal_tool.make_backup):

                backup_path = join(self.backup_folder, basename(image_path))
                file_occurances = glob.glob(backup_path)
                if len(file_occurances) == 0:
                    #self.parent.move_file(image_path, join(self.backup_folder, basename(image_path)))
                    shutil.copy2(image_path, join(self.backup_folder, basename(image_path)))

            #Apply content-aware fill
            self.ps_app.doAction("ContentAwareFill","Logo Removal Tool")

            #Save the processed image
            doc.saveAs(image_path_without_extension.__str__(), ps.PNGSaveOptions(compression=8), True)
            doc.close(ps.SaveOptions.DoNotSaveChanges)
            new_path = pathlib.Path(image_path_without_extension + ".png")
            if(not new_path == image_path):
                self.parent.image_files[self.parent.image_files.index(image_path)] = new_path
                self.parent.update_dataset_viewer_entry(image_path,new_path)
                remove(image_path)
            if(self.parent.image_files.index(new_path) == self.parent.file_index):
                self.parent.set_ui(self.parent.file_index)
            

    def check_for_backup(self):
        selected_file = self.parent.image_files[self.parent.file_index]
        backup_path = join(self.backup_folder, basename(splitext(selected_file)[0] + ".*"))
        file_occurances = glob.glob(backup_path)
        if len(file_occurances) > 0:
            self.current_backup_file = file_occurances[0]
            self.restore_img_btn.configure(fg= tag_helper.theme.color("text"))
        else:
            self.restore_img_btn.configure(fg= tag_helper.theme.color("text_disabled"))
    def restore_from_backup(self,event = None):
        if(not self.current_backup_file == ""):
            index = self.parent.image_files.index(self.parent.image_files[self.parent.file_index])
            source_path = self.parent.image_files[self.parent.file_index]
            target_path = pathlib.Path(join(dirname(self.parent.image_files[self.parent.file_index]), basename(self.current_backup_file)))

            shutil.move(self.current_backup_file,target_path)
            self.parent.image_files[index] = target_path
            self.parent.update_dataset_viewer_entry(source_path,target_path)
            remove(source_path)
            self.current_backup_file = ""
            self.parent.set_ui(self.parent.file_index)
        

    def on_ui_set(self):
        self.check_for_backup()
        
class mask_ui_entry(object):
    def __init__(self,parent,parent_class,row):
        self.parent_class = parent_class
        self.parent = parent
        self.row_index = row
        self.ps_doc = None
        self.path = ""
        self.width = 0
        self.height = 0
        self.mask_bounds = []
        self.compare_bounds = []
        self.compare_cutout = Image.new('RGB', (1, 1))

    def create_ui(self):

        self.entry_frame = tk.Frame(self.parent, 
                                borderwidth=2,
                                relief='raised',)
        
        self.entry_frame.grid(row=self.row_index, column=0,padx=(1, 1), pady=2, sticky="nsew", columnspan= 2)
        #self.entry_frame.rowconfigure(0,weight=0)
        self.entry_frame.columnconfigure(tuple(range(8)), weight=1)
        #self.entry_frame.columnconfigure(0,weight=1)
        self.count_label = tk.Label(self.entry_frame,text= "#" + str(self.row_index), width=4, font=('Calibri 10'))
        self.count_label.grid(row=0, column=0, padx=(1, 1), pady=2, sticky="nsew")

        self.entry_label = tk.Label(self.entry_frame, text=splitext(basename(self.path))[0])
        self.entry_label.grid(row=0, column=1, padx=(1, 1), pady=2, sticky="nsew")

        self.entry_count = tk.IntVar(self.entry_frame,0,"entries")
        self.entry_count_label = tk.Label(self.entry_frame,textvariable= self.entry_count, width=4, font=('Calibri 10'))
        self.entry_count_label.grid(row=1, column=0, padx=(1, 1), pady=2, sticky="nsew")

        
        # self.select_btn = tk.Button(self.entry_frame, text= splitext(basename(self.path))[0], 
        #                     command=self.select_mask, font=('Calibri 10'))
        # self.select_btn.grid(row=0, column=1, padx=4, pady=2, sticky="nsew")


    def select_mask(self):
        print("mask selected")
        self.parent_class.entry_clicked(self)
        #parent_class.

    def set_row_index(self, row):
        self.row_index = row
        self.entry_frame.grid(row=self.row_index)
        self.count_label.config(text= "#" + str(self.row_index))
    def delete_entry(self):
        self.entry_frame.destroy()
