import os

def get_unique_filepath(filepath):
    """
    Ensures a filename is unique by appending (1), (2), etc. if it already exists.
    """
    if not os.path.exists(filepath):
        return filepath
    
    base, ext = os.path.splitext(filepath)
    counter = 1
    while os.path.exists(f"{base} ({counter}){ext}"):
        counter += 1
    return f"{base} ({counter}){ext}"