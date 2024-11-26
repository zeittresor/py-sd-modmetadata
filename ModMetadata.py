import sys
import os
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ExifTags, PngImagePlugin, ImageTk, ImageOps
import re
from datetime import datetime
import platform

def select_image():
    file_path = filedialog.askopenfilename(
        filetypes=[("PNG images", "*.png")], title="Select a PNG image")
    return file_path

def read_png_chunks(file_path):
    chunks = {}
    with open(file_path, 'rb') as f:
        # Skip the 8-byte PNG signature
        f.read(8)
        while True:
            # Each chunk consists of length (4 bytes), type (4 bytes), data, and CRC (4 bytes)
            length_bytes = f.read(4)
            if len(length_bytes) == 0:
                break  # End of file
            length = int.from_bytes(length_bytes, byteorder='big')
            chunk_type = f.read(4).decode('latin-1')
            data = f.read(length)
            crc = f.read(4)
            if chunk_type in ['tEXt', 'zTXt', 'iTXt']:
                try:
                    text = data.decode('latin-1', errors='replace')
                    if '\x00' in text:
                        key, value = text.split('\x00', 1)
                        chunks[key] = value
                    else:
                        chunks[chunk_type] = text
                except Exception:
                    pass
    return chunks

def parse_parameters(params_text):
    data = {}
    # Extract key-value pairs including Prompt and Template
    pattern = r'(Prompt|Template|[\w ]+?):\s*([^,\n]+)'
    matches = re.findall(pattern, params_text)
    consumed = set()
    for key, value in matches:
        key = key.strip()
        value = value.strip()
        data[key] = value
        consumed.add(f"{key}: {value}")
    # Remove consumed parts from the text
    for item in consumed:
        params_text = params_text.replace(item, '')
    # Clean up any remaining text
    params_text = params_text.strip().strip(',').strip()
    params_text = re.sub(r'(,\s*)+', ', ', params_text)  # Replace multiple commas with a single comma
    params_text = params_text.strip(', ')
    if params_text:
        data['Unparsed'] = params_text
    return data

def extract_metadata(image_path):
    img = Image.open(image_path)
    info = img.info
    metadata = {}

    # Basic file information
    file_stats = os.stat(image_path)
    file_size = file_stats.st_size
    creation_time = file_stats.st_ctime
    modification_time = file_stats.st_mtime
    creation_datetime = datetime.fromtimestamp(creation_time)
    modification_datetime = datetime.fromtimestamp(modification_time)
    metadata['File Size'] = f"{file_size} Bytes"
    metadata['Creation Date'] = creation_datetime.strftime('%Y-%m-%d %H:%M:%S')
    metadata['Modification Date'] = modification_datetime.strftime('%Y-%m-%d %H:%M:%S')

    # Image dimensions
    width, height = img.size
    metadata['Dimensions'] = f"{width} x {height} Pixels"

    # DPI
    dpi = img.info.get('dpi', None)
    if dpi:
        metadata['DPI'] = f"{dpi[0]} x {dpi[1]}"
    else:
        metadata['DPI'] = 'Unknown'

    # Image format and mode
    metadata['Format'] = img.format
    metadata['Mode'] = img.mode

    # Exif data (if any)
    exif_data = {}
    if hasattr(img, '_getexif') and img._getexif():
        exif = img._getexif()
        if exif:
            for tag_id, value in exif.items():
                tag = ExifTags.TAGS.get(tag_id, tag_id)
                exif_data[tag] = value
            metadata.update(exif_data)

    # Text chunks from PNG file
    png_chunks = read_png_chunks(image_path)
    # Check if 'parameters' is present and parse it
    if 'parameters' in png_chunks:
        params_data = parse_parameters(png_chunks['parameters'])
        metadata.update(params_data)
        del png_chunks['parameters']
    metadata.update(png_chunks)

    # Remove 'parameters' from metadata if it exists
    metadata.pop('parameters', None)

    # Other metadata from img.info
    for key, value in info.items():
        if key not in ['dpi', 'exif', 'parameters']:
            metadata[key] = value

    # Ensure 'parameters' is not in metadata
    metadata.pop('parameters', None)

    return metadata

def format_metadata(metadata):
    sections = {
        'File Information': {},
        'Image Information': {},
        'Generation Parameters': {},
        'Exif Information': {},
        'More Infos': {}
    }

    # List of known generation parameters
    gen_params = [
        'Prompt', 'Template', 'Steps', 'Sampler', 'CFG scale', 'CFG', 'Seed', 'Size', 'Model', 'Negative prompt',
        'Schedule type', 'Distilled CFG Scale', 'Face restoration', 'Version', 'Diffusion in Low Bits',
        'Module 1', 'Module 2', 'Module 3', 'LoRA', 'Embedding', 'SD Model', 'SD Version',
        'Clip Skip', 'ENSD', 'Hires upscale', 'Hires upscaler', 'Batch size', 'Batch pos', 'Denoising strength'
    ]

    assigned_keys = set()

    # Assign metadata to sections
    for key, value in metadata.items():
        if key in assigned_keys:
            continue  # Skip if already assigned

        if key in ['File Size', 'Creation Date', 'Modification Date']:
            sections['File Information'][key] = value
            assigned_keys.add(key)
        elif key in ['Dimensions', 'DPI', 'Format', 'Mode']:
            sections['Image Information'][key] = value
            assigned_keys.add(key)
        elif key in gen_params:
            sections['Generation Parameters'][key] = value
            assigned_keys.add(key)
        elif key in ExifTags.TAGS.values():
            sections['Exif Information'][key] = value
            assigned_keys.add(key)
        else:
            sections['More Infos'][key] = value
            assigned_keys.add(key)

    return build_formatted_text(sections)

def build_formatted_text(sections):
    # Build formatted text with longer separators
    formatted_text = ""
    separator = '-' * 40  # Adjust the length as needed
    for section, data in sections.items():
        if data:
            formatted_text += f"{section}:\n"
            for key, value in sorted(data.items()):
                formatted_text += f"{key}: {value}\n"
            formatted_text += f"\n{separator}\n\n"
    return formatted_text

def update_metadata_from_text(metadata, text):
    # Parse the text and update metadata
    lines = text.strip().split('\n')
    current_section = None
    for line in lines:
        line = line.strip()
        if not line or line == '-' * 40:
            continue
        if line.endswith(':') and not ':' in line[:-1]:
            # It's a section header
            current_section = line[:-1]
        else:
            if ': ' in line:
                key, value = line.split(': ', 1)
                metadata[key.strip()] = value.strip()
    return metadata

def save_image_with_metadata(image_path, metadata):
    # Load the image
    img = Image.open(image_path)

    # Prepare metadata for saving
    pnginfo = PngImagePlugin.PngInfo()

    # Reconstruct the 'parameters' field
    params_keys = [
        'Prompt', 'Template', 'Steps', 'Sampler', 'CFG scale', 'CFG', 'Seed', 'Size', 'Model', 'Negative prompt',
        'Schedule type', 'Distilled CFG Scale', 'Face restoration', 'Version', 'Diffusion in Low Bits',
        'Module 1', 'Module 2', 'Module 3', 'LoRA', 'Embedding', 'SD Model', 'SD Version',
        'Clip Skip', 'ENSD', 'Hires upscale', 'Hires upscaler', 'Batch size', 'Batch pos', 'Denoising strength'
    ]

    parameters = ''
    for key in params_keys:
        if key in metadata:
            parameters += f"{key}: {metadata[key]}, "
            del metadata[key]

    if parameters:
        parameters = parameters.strip(', ')
        pnginfo.add_text('parameters', parameters)

    # Add other metadata as text chunks
    for key, value in metadata.items():
        if key not in ['File Size', 'Creation Date', 'Modification Date']:
            pnginfo.add_text(key, str(value))

    # Save the image with updated metadata
    save_path = filedialog.asksaveasfilename(defaultextension=".png",
                                             filetypes=[("PNG images", "*.png")],
                                             title="Save Image As")
    if save_path:
        img.save(save_path, pnginfo=pnginfo)
        messagebox.showinfo("Success", "Image saved successfully.")

def print_image_infos(image_path, metadata_text):
    # Implement actual printing functionality
    try:
        from tkinter import simpledialog
        # Create a temporary file to store the combined image and metadata
        from PIL import ImageDraw, ImageFont

        # Create a new image to hold the original image and metadata
        img = Image.open(image_path)
        width, height = img.size

        # Choose a font size
        font_size = 14
        font = ImageFont.load_default()

        # Create a new image for the metadata text
        lines = metadata_text.strip().split('\n')
        line_height = font_size + 2
        text_height = line_height * len(lines)
        text_image = Image.new('RGB', (width, text_height), 'white')
        draw = ImageDraw.Draw(text_image)

        # Draw text onto the image
        y_text = 0
        for line in lines:
            draw.text((0, y_text), line, font=font, fill='black')
            y_text += line_height

        # Combine the original image and the text image vertically
        combined_height = height + text_height
        combined_image = Image.new('RGB', (width, combined_height), 'white')
        combined_image.paste(img, (0, 0))
        combined_image.paste(text_image, (0, height))

        # Save the combined image to a temporary file
        temp_path = os.path.join(os.getcwd(), 'temp_print_image.png')
        combined_image.save(temp_path)

        # Open print dialog
        if platform.system() == 'Windows':
            os.startfile(temp_path, 'print')
        else:
            messagebox.showinfo("Info", "Printing is only implemented on Windows.")
    except Exception as e:
        messagebox.showerror("Error", f"An error occurred while printing: {e}")

def create_gui():
    root = tk.Tk()
    root.title("Image Metadata Viewer / Modifier")
    root.geometry("800x600")

    # Variables to store image path and metadata
    image_path = ''
    metadata = {}
    metadata_text = ''

    # Create PanedWindow
    paned_window = tk.PanedWindow(root, orient='horizontal')
    paned_window.pack(fill='both', expand=True)

    # Left frame for the image
    image_frame = tk.Frame(paned_window)
    paned_window.add(image_frame, minsize=200)  # Set minimum size if needed

    # Right frame for the text
    text_frame = tk.Frame(paned_window)
    paned_window.add(text_frame)

    # Create buttons
    top_frame = tk.Frame(root)
    top_frame.pack(side='top', fill='x')

    def load_image():
        nonlocal image_path, metadata, metadata_text, img, photo
        image_path = select_image()
        if image_path:
            metadata = extract_metadata(image_path)
            metadata_text = format_metadata(metadata)
            text_widget.config(state='normal')
            text_widget.delete('1.0', tk.END)
            text_widget.insert('1.0', metadata_text)
            text_widget.config(state='normal')  # Make editable
            # Load image
            img = Image.open(image_path)
            # Initially display the image
            display_image()
            # Bind resize event to image_frame
            image_frame.bind('<Configure>', on_image_frame_resize)

    def save_image():
        nonlocal metadata
        # Get updated text from text widget
        updated_text = text_widget.get('1.0', tk.END)
        metadata = update_metadata_from_text(metadata, updated_text)
        if image_path:
            save_image_with_metadata(image_path, metadata)
        else:
            messagebox.showwarning("Warning", "No image loaded.")

    def print_image():
        if image_path:
            # Get updated text from text_widget
            updated_text = text_widget.get('1.0', tk.END)
            print_image_infos(image_path, updated_text)
        else:
            messagebox.showwarning("Warning", "No image loaded.")

    def maximize_view():
        root.state('zoomed')
        paned_window.sash_place(0, int(root.winfo_screenwidth() / 2), 0)
        text_widget.config(wrap='word')

    load_button = tk.Button(top_frame, text="Load Image", command=load_image)
    load_button.pack(side='left', padx=5, pady=5)

    save_button = tk.Button(top_frame, text="Save Image", command=save_image)
    save_button.pack(side='left', padx=5, pady=5)

    print_button = tk.Button(top_frame, text="Print Image Infos", command=print_image)
    print_button.pack(side='left', padx=5, pady=5)

    maximize_button = tk.Button(top_frame, text="Maximize", command=maximize_view)
    maximize_button.pack(side='left', padx=5, pady=5)

    # Text widget with scrollbars in text_frame
    xscrollbar = tk.Scrollbar(text_frame, orient='horizontal')
    xscrollbar.pack(side='bottom', fill='x')
    yscrollbar = tk.Scrollbar(text_frame, orient='vertical')
    yscrollbar.pack(side='right', fill='y')

    text_widget = tk.Text(text_frame, wrap='none', xscrollcommand=xscrollbar.set, yscrollcommand=yscrollbar.set)
    text_widget.pack(side='left', fill='both', expand=True)

    xscrollbar.config(command=text_widget.xview)
    yscrollbar.config(command=text_widget.yview)

    # Variables to store the image
    img = None
    photo = None

    # Canvas to display the image
    image_canvas = tk.Canvas(image_frame, bg='gray')
    image_canvas.pack(fill='both', expand=True)

    def on_image_frame_resize(event):
        if img:
            display_image()

    def display_image():
        # Get the size of the image_frame
        frame_width = image_frame.winfo_width()
        frame_height = image_frame.winfo_height()
        if frame_width > 1 and frame_height > 1:
            # Resize the image to fit the frame
            resized_img = ImageOps.contain(img, (frame_width, frame_height))
            photo_img = ImageTk.PhotoImage(resized_img)
            image_canvas.delete("all")
            image_canvas.create_image(frame_width // 2, frame_height // 2, anchor='center', image=photo_img)
            image_canvas.image = photo_img  # Keep a reference to avoid garbage collection

    root.mainloop()

def display_help():
    help_text = """
Usage: python ViewMeta.py [options] [image_path]

Options:
  -h, --help          Show this help message and exit
  -version            Display version information
  -god                Display custom message

If no image_path is provided, the GUI will open and allow you to load an image.
If an image_path is provided, the image and metadata will be displayed directly.
"""
    print(help_text)

def main():
    args = sys.argv[1:]

    if '-h' in args or '--help' in args:
        display_help()
    elif '-version' in args:
        print("github.com/zeittresor")
    elif '-god' in args:
        print("Erstellt mit 100% ChatGPT Q1 Preview Model")
    else:
        image_path = None
        for arg in args:
            if not arg.startswith('-'):
                image_path = arg
                break

        if image_path:
            if os.path.exists(image_path):
                metadata = extract_metadata(image_path)
                metadata_text = format_metadata(metadata)
                # Display metadata in GUI
                def display_metadata_gui():
                    root = tk.Tk()
                    root.title("Image Metadata Viewer")
                    root.geometry("800x600")

                    # Create PanedWindow
                    paned_window = tk.PanedWindow(root, orient='horizontal')
                    paned_window.pack(fill='both', expand=True)

                    # Left frame for the image
                    image_frame = tk.Frame(paned_window)
                    paned_window.add(image_frame, minsize=200)  # Set minimum size if needed

                    # Right frame for the text
                    text_frame = tk.Frame(paned_window)
                    paned_window.add(text_frame)

                    # Text widget with scrollbars in text_frame
                    xscrollbar = tk.Scrollbar(text_frame, orient='horizontal')
                    xscrollbar.pack(side='bottom', fill='x')
                    yscrollbar = tk.Scrollbar(text_frame, orient='vertical')
                    yscrollbar.pack(side='right', fill='y')

                    text_widget = tk.Text(text_frame, wrap='none', xscrollcommand=xscrollbar.set, yscrollcommand=yscrollbar.set)
                    text_widget.insert('1.0', metadata_text)
                    text_widget.config(state='normal')  # Make editable
                    text_widget.pack(side='left', fill='both', expand=True)

                    xscrollbar.config(command=text_widget.xview)
                    yscrollbar.config(command=text_widget.yview)

                    # Load image
                    img = Image.open(image_path)

                    # Canvas to display the image
                    image_canvas = tk.Canvas(image_frame, bg='gray')
                    image_canvas.pack(fill='both', expand=True)

                    def on_image_frame_resize(event):
                        display_image()

                    def display_image():
                        # Get the size of the image_frame
                        frame_width = image_frame.winfo_width()
                        frame_height = image_frame.winfo_height()
                        if frame_width > 1 and frame_height > 1:
                            # Resize the image to fit the frame
                            resized_img = ImageOps.contain(img, (frame_width, frame_height))
                            photo_img = ImageTk.PhotoImage(resized_img)
                            image_canvas.delete("all")
                            image_canvas.create_image(frame_width // 2, frame_height // 2, anchor='center', image=photo_img)
                            image_canvas.image = photo_img  # Keep a reference to avoid garbage collection

                    # Bind resize event to image_frame
                    image_frame.bind('<Configure>', on_image_frame_resize)

                    root.mainloop()

                display_metadata_gui()
            else:
                print(f"Error: File '{image_path}' does not exist.")
        else:
            create_gui()

if __name__ == "__main__":
    main()
