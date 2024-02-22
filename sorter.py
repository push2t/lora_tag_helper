import os

# Get the current directory
current_directory = os.path.dirname(os.path.abspath(__file__))

# Create a dictionary to store the groups of files
file_groups = {}

# Iterate over all files in the directory
for filename in os.listdir(current_directory):
    # Get the file name without extension
    file_name, file_extension = os.path.splitext(filename)
    
    # Skip directories and this script file
    if os.path.isdir(filename) or filename == os.path.basename(__file__):
        continue
    
    # Add the file to the corresponding group
    if file_name in file_groups:
        file_groups[file_name].append([filename, file_extension])
    else:
        file_groups[file_name] = [[filename, file_extension]]

# Rename the files in each group
print(file_groups)
i = 0
for group_name in file_groups:
    files = file_groups[group_name]
    i += 1

    for uhh in files:
        print(uhh)
        f, ext = uhh
        print(f"renaming {f} to {i}{ext}")
        os.rename(os.path.join(current_directory, f), os.path.join(current_directory, f"{i}{ext}"))

    # Generate the new names for the files in the group
    #new_names = [f"{file_extension[1:]}.{i+1}" for i, file_extension in enumerate(file_group)]
    
    # Rename the files
    #for old_name, new_name in zip(file_group, new_names):
    #    print(f"Renaming {old_name} to {new_name}")
#        os.rename(os.path.join(current_directory, old_name), os.path.join(current_directory, new_name))
