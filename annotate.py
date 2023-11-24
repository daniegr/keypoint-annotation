import copy
import os
import sys
import argparse
import timeit
from datetime import datetime
from shutil import copyfile
import csv
import random
from ast import literal_eval as make_tuple
import tkinter as tk
from tkinter import font
from PIL import ImageTk, Image


CURRENT_DIR = os.path.dirname(os.path.realpath(__file__))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TRAINING_DIR = os.path.join(BASE_DIR, 'training')
CSV_PATH = os.path.join(CURRENT_DIR, 'annotations.csv')
SESSIONS_PATH = os.path.join(BASE_DIR, "sessions.txt")
BACKUP_PATH = os.path.join(CURRENT_DIR, 'backups')
COLORS = ['#fff142', '#fff142', '#a8cf74', '#a8cf74', '#fff142', '#576ab1', '#5883c4', '#56bdef', '#f19718', '#d33592',
          '#d962a6', '#e18abd', '#f19718', '#8ac691', '#a3d091', '#c0dc92', '#7b76b7', '#907ab8', '#a97fb9']
BODY_PART_NAMES = ['Head top', 'Nose', 'Right ear', 'Left ear', 'Upper neck', 'Right shoulder',
                        'Right elbow', 'Right wrist', 'Upper chest', 'Left shoulder', 'Left elbow', 'Left wrist',
                        'Mid pelvis', 'Right pelvis', 'Right knee', 'Right ankle', 'Left pelvis', 'Left knee', 'Left ankle']
BODY_PART_PARENT = ['Head top', 'Head top', 'Nose', 'Nose', 'Nose', 'Upper neck', 'Right shoulder', 'Right elbow',
                    'Upper neck', 'Upper neck', 'Left shoulder', 'Left elbow', 'Upper chest', 'Mid pelvis', 'Right pelvis',
                    'Right knee', 'Mid pelvis', 'Left pelvis', 'Left knee']
BODY_PART_CHILDREN = [['Nose'], ['Right ear', 'Left ear', 'Upper neck'], [], [], ['Right shoulder', 'Upper chest', 'Left shoulder'],
                      ['Right elbow'], ['Right wrist'], [], ['Mid pelvis'], ['Left elbow'], ['Left wrist'], [],
                      ['Right pelvis', 'Left pelvis'], ['Right knee'], ['Right ankle'], [], ['Left knee'], ['Left ankle'], []]
NUM_BODY_PARTS = len(BODY_PART_NAMES)


class Datastore:
    ''' A simple class to handle writing of annotations (i.e., coordinates for body parts) into a csv file format '''

    def __init__(self, file_name=CSV_PATH, training=False):
        self.file_name = file_name
        self.headers = ["index", "file"] + [body_part.lower().replace(' ', '_') for body_part in BODY_PART_NAMES] + ["done"]

        # Make empty csv file if it does not already exist
        if not os.path.isfile(file_name):
            with open(file_name, 'w') as f:
                writer = csv.DictWriter(
                    f, fieldnames=self.headers)
                writer.writeheader()

        elif (not training) and file_name == CSV_PATH:
            # Make sure the backup folder exists
            os.makedirs(BACKUP_PATH, exist_ok=True)

            # Make a copy of the existing csv_file
            backup_name = "{}_annotations_backup.csv".format(
                datetime.now().strftime("%Y%m%d-%H%M%S"))
            copyfile(file_name, os.path.join(BACKUP_PATH, backup_name))

    def save_annotations(self, filenames, annotations, statuses):
        ''' Write elements in the datastore to csv file '''

        with open(self.file_name, 'w') as f:
            writer = csv.writer(f)
            writer.writerow(self.headers)

            for i, (filename, annotation, status) in enumerate(zip(filenames, annotations, statuses)):
                row = [i, filename] + annotation + [status]
                writer.writerow(row)

    def _read_file(self):
        ''' Returns a list of all elements in the datastore, represented as dictionaries '''

        with open(self.file_name, 'r') as f:
            reader = csv.DictReader(f)
            return [row for row in reader]

    def get_annotations(self):
        ''' Returns a list of all images in the datastore, represented as list containing coordinates '''

        annotations = []
        for row in self._read_file():
            coordinates = [row[body_part.lower().replace(' ', '_')] for body_part in BODY_PART_NAMES]

            annotations.append([make_tuple(coordinate)
                                for coordinate in coordinates])

        return annotations

    def get_statuses(self):
        ''' Returns a list of all images in the datastore, represented as list containing completion statuses '''

        statuses = []
        for row in self._read_file():
            status = row['done']
            statuses.append(status)

        return statuses

    def get_last_thumbnail_index(self):
        '''Returns the stored index of the last annotated picture'''

        data = self._read_file()

        last_index = -1
        if data:
            for row in data:
                if row['done'] == 'True':
                    last_index = int(row['index'])

        return last_index


class Annotate(tk.Frame):
    ''' Initialize parameters and GUI '''

    def __init__(self, root, args, training=False):
        super().__init__()
        root.attributes('-fullscreen', True)
        self.root = root
        self.args = args

        # GUI dimensions
        screen_width, screen_height = root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.toolbar_height = int(screen_height * 0.15)
        self.image_size = int(screen_width), int(screen_height * 0.85)
        self.guideline_height = self.toolbar_height - 16
        self.marker_radius = int((screen_height / 60) * 0.65)
        self.line_width = int((screen_height / 150) * 0.65)

        # Initialize
        self.root = root
        self.datastore = Datastore(training=training)
        self.body_part_index = 0
        self.thumbnails_path = self.args.image_folder
        self.thumbnail_index = 0
        self.thumbnails = get_image_names(self.thumbnails_path)
        self.current_coordinates = []
        self.markers = []
        self.lines = []
        self.annotations = []
        self.absent_body_parts = set()
        self.completed_objects = []
        self.statuses = []

        # Load annotations, thumbnail index and statuses
        self.load_from_datastore()

        # Load number of image started at and time of start
        self.start_image = self.thumbnail_index - 1
        self.start_time = timeit.default_timer()

        # Create dictionary to track body part markers
        self._drag_data = {"x": 0, "y": 0, "item": None}

        # Flags
        self.is_dragging = False
        self.training_done = False
        self.is_training = False

        # Initialize GUI
        self.initialize_gui()

        # Figure out if annotation work is already done
        completed = False
        if self.is_completed():
            completed = True
            self.thumbnail_index -= 1

        # Display body part markers
        self.update_image()

        # Display completion screen
        if completed:
            self.show_completed_screen()

    def initialize_gui(self):
        ''' Display visual elements '''
        self.add_main_frame(self.root)
        self.bind_keystroke_events(self.root)
        self.add_top_canvas()
        self.add_bottom_canvas()
        self.add_annotation_frame()
        self.add_guideline()
        self.add_last_image_button()
        self.add_confirm_button()
        self.initialize_lines()
        self.initialize_markers()

        # Initialize image text
        self.image_text = None

    def load_from_datastore(self):
        ''' Extract information from datastore '''

        # Obtain index of current image
        last_index = self.datastore.get_last_thumbnail_index()
        if last_index > -1:
            self.thumbnail_index = last_index + 1

        # Retrieve existing annotations as a list
        for annotation in self.datastore.get_annotations():
            self.annotations.append(annotation)

        # Retrieve statuses
        for status in self.datastore.get_statuses():
            self.statuses.append(status)

    def current_video_name(self):
        ''' Returns current video name '''

        # Extract name of current video
        current_thumbnail = self.thumbnails[self.thumbnail_index]
        return current_thumbnail.split('[')[0]

    def current_image_number(self):
        ''' Returns current image number '''

        # Extract number of current image
        current_thumbnail = self.thumbnails[self.thumbnail_index]
        return int(current_thumbnail.split('[')[1][:4])

    def initialize_markers(self):
        ''' Initializes body part markers '''

        for _ in range(NUM_BODY_PARTS):

            # Create markers
            marker = self.top_canvas.create_oval(
                0, 0, 0, 0, fill="", outline="")
            self.markers.append(marker)
            self.current_coordinates.append((0, 0))

            # Bind to events
            self.top_canvas.tag_bind(
                marker, "<ButtonPress-1>", self.on_marker_click)
            self.top_canvas.tag_bind(
                marker, "<ButtonRelease-1>", self.on_marker_release)
            self.top_canvas.tag_bind(
                marker, "<B1-Motion>", self.on_marker_motion)

    def initialize_lines(self):
        ''' Initializes body part association lines '''

        for _ in range(NUM_BODY_PARTS):

            # Create lines
            line = self.top_canvas.create_line(300, 35, 400, 200, fill='', width=self.line_width)
            self.lines.append(line)

    def reset_markers(self):
        ''' Reset body part markers due to change of image '''

        # Reset body part index
        self.body_part_index = 0

        # Reset body part markers
        for i in range(NUM_BODY_PARTS):
            marker = self.markers[i]
            self.top_canvas.itemconfig(marker, fill='', outline='', width=1)
            self.top_canvas.coords(marker, 0, 0, 0, 0)

    def reset_lines(self):
        ''' Reset body part association lines due to change of image '''

        # Reset body part association lines
        for i in range(NUM_BODY_PARTS):
            line = self.lines[i]
            self.top_canvas.itemconfig(line, fill='', width=1)

    def draw_markers(self):
        ''' Draw markers of a image previously annotated '''

        # Set body part index to maximum value
        self.body_part_index = NUM_BODY_PARTS

        # Coordinates do not exist
        if self.thumbnail_index >= len(self.annotations):
            raise RuntimeWarning(
                'Trying to draw markers, but has no coordinates')

        for body_part_index in range(NUM_BODY_PARTS):

            # Obtain parent index
            parent_index = BODY_PART_NAMES.index(BODY_PART_PARENT[body_part_index])

            # Draw marker
            marker = self.markers[body_part_index]
            self.top_canvas.itemconfig(
                marker, fill=COLORS[body_part_index], outline='white')

            # Draw association line
            line = self.lines[body_part_index]
            self.top_canvas.itemconfig(
                line, fill=COLORS[parent_index], width=self.line_width)

            # Fetch location of marker and parent marker
            normalized_x, normalized_y = self.current_coordinates[body_part_index]
            x_pos = normalized_x * self.image.width
            y_pos = normalized_y * self.image.height
            normalized_x_parent, normalized_y_parent = self.current_coordinates[parent_index]
            x_pos_parent = normalized_x_parent * self.image.width
            y_pos_parent = normalized_y_parent * self.image.height

            # Set location of marker
            self.top_canvas.coords(
                marker, x_pos - self.marker_radius, y_pos - self.marker_radius, x_pos + self.marker_radius, y_pos + self.marker_radius)
            
            # Set location of association line
            self.top_canvas.coords(
                line, x_pos, y_pos, x_pos_parent, y_pos_parent)

    def bind_keystroke_events(self, root):
        ''' Facilitate keystroke events '''

        root.bind('<Left>', self.previous_image)
        root.bind('<BackSpace>', self.previous_image)
        root.bind('<Right>', self.on_confirm_click)
        root.bind('<Return>', self.on_confirm_click)
        root.bind('<space>', self.on_confirm_click)
        root.bind('<Escape>', self.close)
        root.bind('e', self.quit_training)

    def add_main_frame(self, root):
        self.main_frame = tk.Frame(root)
        self.main_frame.pack(side=tk.LEFT, fill=tk.BOTH,
                             expand=True, padx=0, pady=0)

    def add_top_canvas(self):
        self.top_canvas = tk.Canvas(self.main_frame)
        self.top_canvas.pack(side='top', fill=tk.NONE)
        self.top_canvas.configure(background='black')

    def add_bottom_canvas(self):
        self.bottom_canvas = tk.Canvas(
            self.main_frame)

        self.bottom_canvas.pack_propagate(0)
        self.bottom_canvas.pack(side='bottom', fill=tk.Y)

    def get_resized_size(self, img):
        ''' Returns size of image in fullscreen mode '''

        # Calculate width
        image_width, image_height = img.size
        max_width, max_height = self.image_size
        resized_height = max_height
        resized_width = int(
            (float(image_width) / float(image_height)) * float(resized_height))

        # Adjust height if too wide
        if (resized_width > max_width):
            resized_height = int(
                (float(image_height) / float(image_width)) * float(max_width))
            resized_width = max_width

        return (resized_width, resized_height)

    def load_image(self, imagepath):
        img = Image.open(imagepath)
        resized_size = self.get_resized_size(img)
        img = img.resize(resized_size)
        self.image = img
        self.tk_image = ImageTk.PhotoImage(img, size=img.size)

    def add_annotation_frame(self):
        self.annotation_frame = self.top_canvas.create_image(
            0, 0, anchor='nw',
        )

        # Facilitate click to place markers
        self.top_canvas.bind("<ButtonRelease-1>", self.on_image_release)

        # Facilitate right click to confirm annotation
        self.top_canvas.bind('<Button-2>', self.on_right_click)
        self.top_canvas.bind('<Button-3>', self.on_right_click)

    def add_last_image_button(self):
        self.last_image_button = tk.Button(
            self.bottom_canvas, width=10, text="LAST\nIMAGE", bg="white", fg="black", borderwidth=0, default='active', command=self.previous_image)
        self.last_image_button.config(font=('helvetica', 14, 'bold'))
        self.last_image_button.pack(fill=tk.Y, side=tk.LEFT)

    def add_confirm_button(self):
        self.accept_button = tk.Button(
            self.bottom_canvas, text="CONFIRM\nANNOTATION", bg="white", fg="green", borderwidth=0, default='active', command=self.on_confirm_click)
        self.accept_button.config(font=('helvetica', 14, 'bold'))
        self.accept_button.pack(fill=tk.BOTH, side=tk.LEFT, expand=True)

    def add_guideline(self):
        self.add_guideline_area()
        self.add_guideline_label()
        self.add_guideline_image(0)

    def add_guideline_area(self):
        self.guideline_canvas = tk.Frame(
            self.bottom_canvas, height=self.toolbar_height)
        self.guideline_canvas.pack(fill=tk.BOTH, side=tk.LEFT)

    def add_guideline_label(self):
        self.guideline_label = tk.Label(
            self.guideline_canvas, text="GUIDELINE:", width=12)
        self.guideline_label.config(font=('helvetica', 10, 'bold'))
        self.guideline_label.pack(side=tk.TOP, fill=tk.Y)

    def add_guideline_image(self, body_part_index):

        # Create image
        guideline_image_path = os.path.join(
            BASE_DIR, 'frontend/body_parts', '{}.png'.format(body_part_index))
        img = Image.open(guideline_image_path)

        # Resize image
        width, height = img.size
        resized_height = self.guideline_height-10
        resized_width = int((float(width) / float(height))
                            * float(resized_height))
        resized_size = resized_width, resized_height
        img = img.resize(resized_size)

        try:
            if self.guideline_field:
                self.guideline_image = ImageTk.PhotoImage(img)
                self.guideline_field.configure(image=self.guideline_image)
                self.guideline_field.image = self.guideline_image
        except:
            self.guideline_image = ImageTk.PhotoImage(img)
            self.guideline_field = tk.Label(
                self.guideline_canvas, image=self.guideline_image)
            self.guideline_field.pack(fill=tk.BOTH, side=tk.BOTTOM)

    #
    #  EVENTS
    #

    def close(self, event):
        '''Exit the program'''

        # Store number of images annotated and time spent
        store_session(self)

        # Exit
        sys.exit()

    def quit_training(self, event):
        '''Shortcut to quit training'''

        # Continue to annotation program
        if self.is_training:
            self.on_complete_training(self.args)

    def on_confirm_click(self, event=None):
        ''' Act if confirm button is pressed '''

        if self.body_part_index == NUM_BODY_PARTS:

            # Store coordinates
            if self.is_new_image():
                if not len(self.annotations) == len(self.thumbnails):
                    self.annotations.append(
                        copy.deepcopy(self.current_coordinates))
                    self.statuses.append('True')
            else:
                self.annotations[self.thumbnail_index] = copy.deepcopy(
                    self.current_coordinates)
                self.statuses[self.thumbnail_index] = 'True'
            if len(self.annotations) <= len(self.thumbnails):
                self.save_to_datastore()

            # Change to next image
            self.next_image()

    def on_image_release(self, event):
        ''' Place body part marker '''

        # Stop dragging
        if self.is_dragging:
            self.is_dragging = False
            return

        # Do nothing if all markers are placed
        if self.body_part_index >= NUM_BODY_PARTS:
            return

        # Place body part marker and association lines according to event position
        normalized_x = event.x / self.image.width
        normalized_y = event.y / self.image.height
        self.current_coordinates[self.body_part_index] = (
            normalized_x, normalized_y)
        marker = self.markers[self.body_part_index]
        self.top_canvas.coords(marker, event.x - self.marker_radius, event.y - self.marker_radius,
                               event.x + self.marker_radius, event.y + self.marker_radius)
        parent_index = BODY_PART_NAMES.index(BODY_PART_PARENT[self.body_part_index])
        normalized_x_parent, normalized_y_parent = self.current_coordinates[parent_index]
        x_pos_parent = normalized_x_parent * self.image.width
        y_pos_parent = normalized_y_parent * self.image.height
        line = self.lines[self.body_part_index]
        self.top_canvas.coords(line, event.x, event.y, x_pos_parent, y_pos_parent)

        # If during training, check if the point is correctly placed
        if self.is_training:
            margin = 0.02

            ground_truth_x, ground_truth_y = self.ground_truth_annotations[
                self.thumbnail_index][self.body_part_index]

            if not ((abs(normalized_x - ground_truth_x) < margin) and (abs(normalized_y - ground_truth_y) < margin)):
                # Point is placed outside the margin

                color = 'grey'
                self.top_canvas.itemconfig(
                    marker, fill=color, outline='white')

                line = self.lines[self.body_part_index]
                self.top_canvas.itemconfig(
                    line, fill=color, width=self.line_width)

                return

            # Change descriptive text
            self.update_image_text()

            # Update guideline image
            self.add_guideline_image(self.body_part_index)

        # Make marker visible
        color = COLORS[self.body_part_index]
        self.top_canvas.itemconfig(
            marker, fill=color, outline='white')

        # Make association line visible
        self.top_canvas.itemconfig(
            line, fill=COLORS[parent_index], width=self.line_width)

        # Iterate to the next body part
        self.body_part_index += 1

        # Change descriptive text
        self.update_image_text()

        # Update guideline image
        self.add_guideline_image(self.body_part_index)

    def on_marker_click(self, event):
        ''' Start tracking of item when clicked '''

        # Start dragging
        self.is_dragging = True

        # Record the respective body part marker item and the location
        self._drag_data["item"] = self.top_canvas.find_closest(event.x, event.y)[
            0]
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y
        self.start_coord = (event.x, event.y)

    def on_marker_right_click(self, event):
        ''' Change transparency of body part marker '''

        # Locate clicked body part marker item
        body_part = self.top_canvas.find_closest(event.x, event.y)[0]
        body_part_index = int(body_part) - 2

        # Change transparency according to previous status
        if body_part in self.absent_body_parts:
            # Increase transparency
            self.absent_body_parts.remove(body_part)
            self.top_canvas.itemconfig(
                body_part, fill=COLORS[body_part_index], outline='white', width=1)

        else:
            # Remove transparency
            self.absent_body_parts.add(body_part)
            self.top_canvas.itemconfig(
                body_part, fill='white', outline=COLORS[body_part_index], width=5)

    def on_marker_motion(self, event):
        ''' Update information when tracked item is moved '''

        # Continue dragging
        self.is_dragging = True

        # Move body part marker and association line according to distance of movement
        delta_x = event.x - self._drag_data["x"]
        delta_y = event.y - self._drag_data["y"]
        self.top_canvas.move(self._drag_data["item"], delta_x, delta_y)
        current_body_part_index = self._drag_data["item"] - 2 - NUM_BODY_PARTS
        parent_index = BODY_PART_NAMES.index(BODY_PART_PARENT[current_body_part_index])
        if current_body_part_index == parent_index:
            self.top_canvas.coords(
                self.lines[current_body_part_index], event.x, event.y, event.x, event.y)
        else:
            normalized_x_parent, normalized_y_parent = self.current_coordinates[parent_index]
            x_pos_parent = normalized_x_parent * self.image.width
            y_pos_parent = normalized_y_parent * self.image.height
            self.top_canvas.coords(
                self.lines[current_body_part_index], event.x, event.y, x_pos_parent, y_pos_parent)

        # Update association lines for children
        for child in BODY_PART_CHILDREN[current_body_part_index]:
            child_index = BODY_PART_NAMES.index(child)
            normalized_x_child, normalized_y_child = self.current_coordinates[child_index]
            x_pos_child = normalized_x_child * self.image.width
            y_pos_child = normalized_y_child * self.image.height
            self.top_canvas.coords(
                self.lines[child_index], event.x, event.y, x_pos_child, y_pos_child)

        # Record the new position
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y

    def on_marker_release(self, event):
        ''' Stop tracking of item when pressed '''

        # Update x coordinate
        normalized_x = event.x / self.image.width
        if normalized_x < 0.0:
            normalized_x = 0.0
        elif normalized_x > 1.0:
            normalized_x = 1.0

        # Update y coordinate
        normalized_y = event.y / self.image.height
        if normalized_y < 0.0:
            normalized_y = 0.0
        elif normalized_y > 1.0:
            normalized_y = 1.0

        # Update coordinates according to new location
        body_part_index = int(self._drag_data["item"]) - 2 - NUM_BODY_PARTS
        self.current_coordinates[body_part_index] = (
            normalized_x, normalized_y)

        # Terminate drag of body part marker item
        self._drag_data["item"] = None
        self._drag_data["x"] = 0
        self._drag_data["y"] = 0

        if self.is_training and (body_part_index == self.body_part_index):
            margin = 0.02
            marker = self.markers[self.body_part_index]

            ground_truth_x, ground_truth_y = self.ground_truth_annotations[
                self.thumbnail_index][self.body_part_index]

            if not ((abs(normalized_x - ground_truth_x) < margin) and (abs(normalized_y - ground_truth_y) < margin)):

                color = 'grey'
                self.top_canvas.itemconfig(
                    marker, fill=color, outline='white')

                line = self.lines[body_part_index]
                self.top_canvas.itemconfig(
                    line, fill='grey', width=self.line_width)

            else:

                # Make marker visible
                color = COLORS[self.body_part_index]
                self.top_canvas.itemconfig(
                    marker, fill=color, outline='white')

                # Draw association line
                parent_index = BODY_PART_NAMES.index(BODY_PART_PARENT[body_part_index])
                line = self.lines[body_part_index]
                self.top_canvas.itemconfig(
                    line, fill=COLORS[parent_index], width=self.line_width)

                # Iterate to the next body part
                self.body_part_index += 1

                # Change descriptive text
                self.update_image_text()

        elif self.body_part_index < NUM_BODY_PARTS:

            # Change descriptive text
            self.update_image_text()

        # Update guideline image
        self.add_guideline_image(body_part_index)

    def on_right_click(self, event):
        ''' Act if confirm button is pressed '''

        self.on_confirm_click(event)

    def on_complete_training(self, event=None):

        # Clean UI
        if len(self.completed_objects) > 0:
            for item in self.completed_objects:
                try:
                    self.top_canvas.delete(item)
                except:
                    pass
        self.completed_objects = []

        self.root.destroy()
        root = tk.Tk()
        root.title("Annotation program")

        self.__init__(root, self.args)
        self.update_image()

    def update_image_text(self):
        ''' Update descriptive text when body part is correctly annotated '''

        # Delete text if already exists
        if self.image_text:
            self.top_canvas.delete(self.image_text)

        # More body parts to annotate in this example
        if self.is_training:
            if self.body_part_index < NUM_BODY_PARTS:
                text = "{}".format(
                    BODY_PART_NAMES[self.body_part_index])
                self.image_text = self.top_canvas.create_text(self.image.width * 0.5,
                                                              self.image.height * 0.96,
                                                              text=text, fill="#ffffff",
                                                              font=font.Font(family='Helvetica', size=15,
                                                                             weight='bold'), justify=tk.CENTER)

        # Completed annotating this training example
        elif self.body_part_index == NUM_BODY_PARTS:
            text = "Image: {} out of {} ".format(self.thumbnail_index + 1, len(self.thumbnails))
            self.image_text = self.top_canvas.create_text(self.image.width * 0.5, self.image.height * 0.96,
                                                          text=text, fill="#ffffff",
                                                          font=font.Font(family='Helvetica', size=15, weight='bold'), justify=tk.CENTER)
        else:
            text = "{}\nImage: {} out of {} ".format(
                BODY_PART_NAMES[self.body_part_index], self.thumbnail_index + 1, len(self.thumbnails))
            self.image_text = self.top_canvas.create_text(self.image.width * 0.5, self.image.height * 0.96,
                                                          text=text, fill="#ffffff",
                                                          font=font.Font(family='Helvetica', size=15, weight='bold'), justify=tk.CENTER)

    #
    # Methods for changing image
    #

    def update_image(self):
        ''' Perform GUI update and store information due to change of image '''

        # Extract information for upcoming image
        thumbnail = self.thumbnails[self.thumbnail_index]
        file_path = os.path.join(self.thumbnails_path, thumbnail)

        # Annotation photo
        self.load_image(file_path)
        self.top_canvas.delete(self.annotation_frame)
        width, height = self.image.size
        self.annotation_frame = self.top_canvas.create_image(3, 3, anchor=tk.NW,
                                                             image=self.tk_image)
        self.top_canvas.lower(self.annotation_frame)

        # Adjust dimensions according to current image height
        width, height = self.image.size
        self.main_frame.config(width=width)
        self.top_canvas.config(width=width, height=height)
        self.bottom_canvas.config(width=width - 4)
        
        # Reinitiate markers
        if self.thumbnail_index < len(self.annotations):
            self.current_coordinates = self.annotations[self.thumbnail_index]
            self.draw_markers()
        else:
            self.reset_lines()
            self.reset_markers()

        # Change image text
        if self.image_text:
            self.top_canvas.delete(self.image_text)
        if self.is_training:
            if self.body_part_index < NUM_BODY_PARTS:
                text = "{}".format(
                    BODY_PART_NAMES[self.body_part_index])
                self.image_text = self.top_canvas.create_text(self.image.width * 0.5, self.image.height * 0.96,
                                                              text=text, fill="#ffffff",
                                                              font=font.Font(family='Helvetica', size=15, weight='bold'), justify=tk.CENTER)
        else:
            if self.body_part_index < NUM_BODY_PARTS:
                text = "{}\nImage: {} out of {} ".format(
                    BODY_PART_NAMES[self.body_part_index], self.thumbnail_index + 1, len(self.thumbnails))
            else:
                text = "Image: {} out of {} ".format(
                    self.thumbnail_index + 1, len(self.thumbnails))
            self.image_text = self.top_canvas.create_text(self.image.width * 0.5, self.image.height * 0.96,
                                                          text=text, fill="#ffffff",
                                                          font=font.Font(family='Helvetica', size=15, weight='bold'), justify=tk.CENTER)
        
        # Update guideline image
        self.add_guideline_image(self.body_part_index)
        
        # Force markers in front
        for i in range(NUM_BODY_PARTS):
            marker = self.markers[i]
            self.top_canvas.lift(marker)

    def is_new_image(self):
        ''' Returns True if the image does not already exist '''

        return self.thumbnail_index == len(self.annotations)

    def previous_image(self, event=None):
        '''  Change to previous image '''

        if self.thumbnail_index == 0:
            # Do nothing if you are on the first image
            return

        # Update information according to previous image
        self.thumbnail_index -= 1
        self.current_coordinates = self.annotations[self.thumbnail_index]
        self.update_image()

        # Last image overall
        if self.thumbnail_index < len(self.thumbnails):
            # Remove completed text
            if not len(self.completed_objects) == 0:
                for item in self.completed_objects:
                    self.top_canvas.delete(item)
                self.completed_objects = []

        # Display full body configuration
        self.body_part_index = NUM_BODY_PARTS
        self.add_guideline_image(self.body_part_index)

    def next_image(self, event=None):
        ''' Change to next image '''

        # Increase thumbnail index
        if self.is_completed():
            pass
        else:
            self.thumbnail_index += 1

        if self.is_training and self.is_completed():
            self.show_completed_training_screen()
            
        # Update information according to next image
        elif self.is_completed():
            self.show_completed_screen()
        else:
            self.update_image()

    def is_completed(self):
        ''' Check if all images have been annotated '''

        return self.thumbnail_index == len(self.thumbnails)

    def save_to_datastore(self):
        ''' Store information to csv file '''

        # Create data structures
        annotations = []
        thumbnails = []
        statuses = []
        for thumbnail, annotation, status in zip(self.thumbnails, self.annotations, self.statuses):
            annotations.append(annotation)
            thumbnails.append(thumbnail)
            statuses.append(status)

        # Store to file
        self.datastore.save_annotations(
            filenames=thumbnails, annotations=annotations, statuses=statuses)

    def show_completed_screen(self):
        ''' Display message for completing annotation work '''

        # Create completion screen
        if len(self.completed_objects) == 0:
            rectangle = self.top_canvas.create_rectangle(self.image.width * 0.10, self.image.height *
                                                         0.25, self.image.width * 0.9, self.image.height * 0.75, fill="#ffffff")
            main_text = self.top_canvas.create_text(self.image.width * 0.5,
                                                    self.image.height * 0.3,
                                                    text="Annotation completed!", fill="#000000",
                                                    font=font.Font(family='Helvetica', size=25, weight='bold'))
            descriptive_text = self.top_canvas.create_text(self.image.width * 0.5,
                                                           self.image.height * 0.4,
                                                           text="Thank you very much for your contribution \nannotating images for a good cause!", fill="#000000",
                                                           font=font.Font(family='Helvetica', size=15, weight='bold'), justify=tk.CENTER)

            # Display prize
            prize_image_path = os.path.join(BASE_DIR, 'frontend', 'prize.png')
            prize_img = Image.open(prize_image_path)
            height = int(self.image.height * 0.25)
            prize_img = prize_img.resize((height, height))
            self.prize_image = ImageTk.PhotoImage(
                prize_img, size=prize_img.size)
            self.prize_field = self.top_canvas.create_image(
                self.image.width * 0.5,
                self.image.height * 0.585,
                image=self.prize_image
            )

            self.completed_objects = [
                rectangle, main_text, descriptive_text, self.prize_field]

    def show_completed_training_screen(self):
        ''' Display message for completing training '''

        # Create completion screen
        rectangle = self.top_canvas.create_rectangle(self.image.width * 0.10, self.image.height *
                                                     0.4, self.image.width * 0.9, self.image.height * 0.75, fill="#ffffff")
        main_text = self.top_canvas.create_text(self.image.width * 0.5,
                                                self.image.height * 0.45,
                                                text="Training completed!", fill="#000000",
                                                font=font.Font(family='Helvetica', size=25, weight='bold'))
        descriptive_text = self.top_canvas.create_text(self.image.width * 0.5,
                                                       self.image.height * 0.61,
                                                       text="Did you know?\nIf you are confident that you place\nthe markers correctly, training can be\n skipped by pressing 'E'.\n\nGood luck annotating!", fill="#000000",
                                                       font=font.Font(family='Helvetica', size=15, weight='bold'), justify=tk.CENTER)
        continue_button = self.accept_button = tk.Button(
            self.top_canvas, width=22, height=1, text="START TO ANNOTATE", bg="white", fg="black", borderwidth=0, default='active', command=self.on_complete_training)
        continue_button.config(font=('helvetica', 24, 'bold'))
        continue_button_window = self.top_canvas.create_window(
            self.image.width * 0.5, self.image.height * 0.65, anchor=tk.N, window=continue_button)
        self.completed_objects = [rectangle,
                                  main_text, descriptive_text, continue_button, continue_button_window]

    def do_training(self):
        ''' Start program in training mode '''

        # Initialize
        self.is_training = True
        self.thumbnail_index = 0
        self.body_part_index = 0
        if len(self.completed_objects) > 0:
            for item in self.completed_objects:
                self.top_canvas.delete(item)
            self.completed_objects = []

        # Load a datastore with the 'true' annotations for training examples
        ground_truth_csv = os.path.join(TRAINING_DIR, 'ground_truth.csv')
        self.ground_truth = Datastore(ground_truth_csv)
        self.ground_truth_annotations = self.ground_truth.get_annotations()

        # Create an empty datastore for the training annotations
        training_csv = os.path.join(TRAINING_DIR, 'training.csv')

        if os.path.isfile(training_csv):
            os.remove(training_csv)

        self.datastore = Datastore(training_csv)
        self.annotations = self.datastore.get_annotations()

        # Load the training images
        self.thumbnails_path = os.path.join(TRAINING_DIR, 'images')
        self.thumbnails = get_image_names(
            self.thumbnails_path, shuffle=False, training=True)

        self.update_image()


def get_image_names(dir_path, shuffle=False, training=False):
    ''' Returns ordered list of images '''

    image_names = []
    for file in os.listdir(dir_path):
        if file.endswith('.jpg') or file.endswith('.png'):
            image_names.append(file)
    image_names.sort()

    if shuffle:
        # Deterministic shuffling to obtain randomized order of images
        random.seed(42)
        random.shuffle(image_names)

    return image_names


def store_session(annotate):
    ''' Store number of images annotated and time of session '''

    if not annotate.is_training:

        # Compute number of images annotated
        num_images_annotated = annotate.datastore.get_last_thumbnail_index() - \
            annotate.start_image

        # Compute time spent and date of termination
        seconds_spent = timeit.default_timer() - annotate.start_time
        date = str(datetime.now()).split()[0]

        # Write to file
        if not os.path.exists(SESSIONS_PATH):
            with open(SESSIONS_PATH, "w") as file:
                file.write("Number of images annotated,Seconds spent,Date")
                file.close()
        with open(SESSIONS_PATH, "a") as file:
            file.write("\n{},{},{}".format(
                num_images_annotated, seconds_spent, date))
            file.close()


def main(args):
    ''' Main program '''

    # Initialize annotation program
    root = tk.Tk()
    root.title("Training")

    # Create GUI and functionality of annotation program
    annotate = Annotate(root, args, training=True)
    annotate.pack(fill="both", expand=True)
    annotate.do_training()

    root.mainloop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--image-folder', type=str, dest='image_folder', help='Path of folder with images to annotate')
    args = parser.parse_args()
    
    main(args)