"""
GraphHopper Trip Planner - Window Version
=========================================
FEATURE 6: Graphical user interface (branch feature-gui)

A step-by-step window version of our trip planner, built with Tkinter,
which comes with Python. It does everything the command-line app
(graphhopper_parse-json_7.py) does:

    Step 1  Trip Settings   API key, travel mode (car/bike/foot), km or miles,
                            optional fuel details for a cost estimate
    Step 2  Set Your Route  start, destination and up to 3 more stops, with a
                            route preview drawn from GraphHopper's route shape
    Step 3  Trip Summary    distance, duration, stops, fuel cost, turn-by-turn
                            directions, and export to .csv or .txt

Errors (no internet, wrong API key, unknown place) show as friendly pop-ups.

How to run:
    1. pip install requests
    2. python trip_planner_gui.py
    3. Paste your GraphHopper API key in step 1. If the GRAPHHOPPER_API_KEY
       environment variable is set, the box fills in by itself.
"""

import csv
import math
import os
import queue
import threading
import tkinter as tk
import tkinter.font as tkfont
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

import requests

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
GEOCODE_URL = "https://graphhopper.com/api/1/geocode"
ROUTE_URL = "https://graphhopper.com/api/1/route"
REQUEST_TIMEOUT = 10      # seconds to wait for GraphHopper before giving up
KM_PER_MILE = 1.60934
MAX_STOPS = 5             # GraphHopper's free plan allows up to 5 points

# Colors
BG = "#e9edf3"            # window background
CARD = "#ffffff"          # main card
BORDER = "#e3e8ef"
TEXT = "#2d3748"
MUTED = "#8a94a6"
PRIMARY = "#1677ff"
PRIMARY_DARK = "#0f5fd6"
PRIMARY_SOFT = "#e8f1ff"
ACCENT = "#ff5a79"        # destination pin
ACCENT_SOFT = "#ffd9e1"
GREEN = "#22b07d"         # start pin
MAP_BG = "#f2f5f9"
MAP_GRID = "#e4e9f0"
INPUT_OFF = "#f4f6f9"

FONT = "TkDefaultFont"    # replaced with the best font found on this computer
ARROW = "→"          # the arrow between stop names

STEPS = {
    1: ("Trip Settings", "Choose how you travel and the units you want to see."),
    2: ("Set Your Route", "Enter where you start and where you are going. "
                          "You can add up to 3 more stops."),
    3: ("Trip Summary", "Review your distance, time and cost, then save your trip."),
}


def font(size, weight="normal"):
    return (FONT, size, weight)


# ---------------------------------------------------------------------------
# Logic: talking to GraphHopper (no window code here)
# ---------------------------------------------------------------------------
class ApiError(Exception):
    """Raised with a friendly message when a GraphHopper request fails."""


def call_api(url, params):
    """Send a GET request and return the JSON data, or raise ApiError."""
    try:
        reply = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
    except requests.exceptions.ConnectionError:
        raise ApiError("Cannot reach GraphHopper. Check your internet connection.") from None
    except requests.exceptions.Timeout:
        raise ApiError("GraphHopper took too long to answer. Please try again.") from None

    try:
        data = reply.json()
    except ValueError:
        raise ApiError("Unexpected response from GraphHopper (status "
                       + str(reply.status_code) + ").") from None

    if reply.status_code == 401:
        raise ApiError("Invalid API key. Check the key in your GraphHopper dashboard.")
    if reply.status_code == 429:
        raise ApiError("API limit reached. Wait a moment or check your daily credits.")
    if reply.status_code != 200:
        raise ApiError(data.get("message", "Request failed (status "
                                + str(reply.status_code) + ")."))
    return data


def geocode(place, key):
    """Turn a place name into (latitude, longitude, display name)."""
    data = call_api(GEOCODE_URL, {"q": place, "limit": 1, "key": key})
    if not data.get("hits"):
        raise ApiError('Could not find "' + place + '". Try a more specific name.')
    hit = data["hits"][0]
    parts = [hit.get("name"), hit.get("state"), hit.get("country")]
    name = ", ".join(part for part in parts if part)
    return hit["point"]["lat"], hit["point"]["lng"], name


def get_route(points, vehicle, key):
    """Get one route through all points. points = list of (lat, lng).
    The route shape (points_encoded=false) is used to draw the map preview."""
    params = [("point", str(lat) + "," + str(lng)) for lat, lng in points]
    params += [("vehicle", vehicle), ("locale", "en"), ("instructions", "true"),
               ("calc_points", "true"), ("points_encoded", "false"), ("key", key)]
    data = call_api(ROUTE_URL, params)
    if not data.get("paths"):
        raise ApiError("No route found between these places for this travel mode.")
    return data["paths"][0]


def convert_distance(meters, units):
    """Convert meters to kilometers ("km") or miles ("mi")."""
    km = meters / 1000
    return km if units == "km" else km / KM_PER_MILE


def format_duration(milliseconds):
    """Convert milliseconds to hh:mm:ss."""
    total_seconds = int(milliseconds / 1000)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return "{0:02d}:{1:02d}:{2:02d}".format(hours, minutes, seconds)


def friendly_duration(milliseconds):
    """Convert milliseconds to a short form like '2h 35m' or '18 min'."""
    hours, minutes = divmod(int(milliseconds / 60000), 60)
    if hours:
        return "{0}h {1:02d}m".format(hours, minutes)
    return "{0} min".format(max(minutes, 1))


def parse_positive(text, field_name):
    """Read an optional positive number from a text box.
    Returns None when the box is empty, raises ValueError when it is invalid."""
    text = text.strip()
    if text == "":
        return None
    try:
        value = float(text)
    except ValueError:
        raise ValueError(field_name + " must be a number.") from None
    if value <= 0:
        raise ValueError(field_name + " must be more than 0.")
    return value


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------
def round_rect(canvas, x1, y1, x2, y2, radius, **options):
    """Draw a rectangle with rounded corners on a canvas."""
    radius = min(radius, (x2 - x1) / 2, (y2 - y1) / 2)
    points = [x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
              x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
              x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1]
    return canvas.create_polygon(points, smooth=True, **options)


def draw_pin(canvas, x, y, radius, color):
    """Draw a map pin whose tip is at (x, y). Returns the center of its head."""
    cx, cy = x, y - radius * 1.9
    canvas.create_polygon(x - radius * 0.8, cy + radius * 0.55, x + radius * 0.8,
                          cy + radius * 0.55, x, y, fill=color, outline="")
    canvas.create_oval(cx - radius, cy - radius, cx + radius, cy + radius,
                       fill=color, outline="")
    return cx, cy


class PillButton(tk.Canvas):
    """A rounded button drawn on a canvas, since Tkinter buttons are square."""

    STYLES = {
        "primary": (PRIMARY, PRIMARY_DARK, PRIMARY, "white"),
        "soft": (PRIMARY_SOFT, "#d9e8ff", PRIMARY_SOFT, PRIMARY),
        "outline": (CARD, "#f4f7fb", BORDER, TEXT),
        "toggle": (CARD, "#f4f7fb", BORDER, TEXT),
        "selected": (PRIMARY_SOFT, PRIMARY_SOFT, PRIMARY, PRIMARY),
    }

    def __init__(self, parent, text, command, kind="primary", width=130, height=38):
        super().__init__(parent, width=width, height=height, bg=parent["bg"],
                         highlightthickness=0, bd=0, cursor="hand2")
        self.text, self.command, self.kind = text, command, kind
        self.size = (width, height)
        self.enabled = True
        self.hovering = False
        self.bind("<Enter>", lambda event: self._hover(True))
        self.bind("<Leave>", lambda event: self._hover(False))
        self.bind("<ButtonRelease-1>", self._click)
        self.draw()

    def draw(self):
        self.delete("all")
        width, height = self.size
        fill, hover, outline, color = self.STYLES[self.kind]
        if not self.enabled:
            if self.kind == "primary":
                fill = outline = "#c9d6e8"
                color = "white"
            else:
                color = "#c5cdd8"
        elif self.hovering:
            fill = hover
        round_rect(self, 1, 1, width - 1, height - 1, height / 2,
                   fill=fill, outline=outline, width=1)
        self.create_text(width / 2, height / 2, text=self.text, fill=color,
                         font=font(10, "bold"))

    def _hover(self, hovering):
        self.hovering = hovering
        self.draw()

    def _click(self, event):
        if self.enabled and 0 <= event.x <= self.size[0] and 0 <= event.y <= self.size[1]:
            self.command()

    def set_enabled(self, enabled):
        self.enabled = enabled
        self.configure(cursor="hand2" if enabled else "")
        self.draw()

    def set_kind(self, kind):
        self.kind = kind
        self.draw()

    def set_text(self, text):
        self.text = text
        self.draw()


# ---------------------------------------------------------------------------
# The window
# ---------------------------------------------------------------------------
class TripPlannerApp(tk.Tk):
    """Three-step trip planner: settings, route with map, summary."""

    def __init__(self):
        super().__init__()
        global FONT, ARROW
        FONT = self.pick_font()
        if FONT not in ("Segoe UI", "Helvetica Neue", "Ubuntu", "Inter", "DejaVu Sans", "Arial"):
            ARROW = "->"                   # some fonts have no arrow symbol
        self.title("GraphHopper Trip Planner")
        self.geometry("1000x660")
        self.minsize(940, 620)
        self.configure(bg=BG)

        self.step = 1
        self.route = None                  # {"stops", "path", "vehicle"} once found
        self.fuel = None                   # (efficiency, price) or None
        self.summary_rows = []             # used when saving the trip
        self.results = queue.Queue()       # background thread -> window
        self.busy = False
        self.map_message = ("Your route will appear here",
                            "Enter your stops, then click Find Route.")

        self.setup_styles()
        self.build_layout()
        self.show_step(1)

    # ----- setup -------------------------------------------------------------
    def pick_font(self):
        """Use the nicest font this computer has."""
        available = set(tkfont.families(self))
        for name in ("Segoe UI", "Helvetica Neue", "Ubuntu", "Inter", "DejaVu Sans", "Arial"):
            if name in available:
                return name
        return tkfont.nametofont("TkDefaultFont").actual("family")

    def setup_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Trip.Treeview", background=CARD, fieldbackground=CARD,
                        foreground=TEXT, rowheight=30, borderwidth=0, font=font(10))
        style.configure("Trip.Treeview.Heading", background=CARD, foreground=MUTED,
                        font=font(9, "bold"), relief="flat", borderwidth=0)
        style.map("Trip.Treeview.Heading", background=[("active", CARD)])
        style.map("Trip.Treeview", background=[("selected", PRIMARY_SOFT)],
                  foreground=[("selected", PRIMARY)])
        style.layout("Trip.Treeview", [("Trip.Treeview.treearea", {"sticky": "nswe"})])
        style.configure("Trip.Vertical.TScrollbar", troughcolor=CARD, background="#d9e0ea",
                        bordercolor=CARD, arrowcolor=MUTED, lightcolor="#d9e0ea",
                        darkcolor="#d9e0ea", gripcount=0)

    def build_layout(self):
        # A soft edge behind the card works like a shadow
        shadow = tk.Frame(self, bg="#dce2ea")
        shadow.pack(fill="both", expand=True, padx=28, pady=24)
        card = tk.Frame(shadow, bg=CARD)
        card.pack(fill="both", expand=True, padx=(0, 2), pady=(0, 3))

        self.build_sidebar(card)
        tk.Frame(card, bg=BORDER, width=1).pack(side="left", fill="y")

        main = tk.Frame(card, bg=CARD, padx=34, pady=26)
        main.pack(side="left", fill="both", expand=True)

        nav = tk.Frame(main, bg=CARD)
        nav.pack(side="bottom", fill="x", pady=(16, 0))
        self.prev_button = PillButton(nav, "‹   Previous", self.on_previous,
                                      kind="outline", width=128)
        self.prev_button.pack(side="left")
        self.next_button = PillButton(nav, "Next Step   ›", self.on_next, width=150)
        self.next_button.pack(side="right")

        self.title_label = tk.Label(main, bg=CARD, fg=TEXT, font=font(17, "bold"), anchor="w")
        self.title_label.pack(fill="x", pady=(0, 14))

        self.content = tk.Frame(main, bg=CARD)
        self.content.pack(fill="both", expand=True)
        self.step_frames = [self.build_step1(), self.build_step2(), self.build_step3()]

    # ----- sidebar -------------------------------------------------------------
    def build_sidebar(self, card):
        side = tk.Frame(card, bg=CARD, width=250)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)

        self.steps_canvas = tk.Canvas(side, width=250, height=60, bg=CARD,
                                      highlightthickness=0)
        self.steps_canvas.pack(pady=(30, 0))
        self.art = tk.Canvas(side, width=170, height=120, bg=CARD, highlightthickness=0)
        self.art.pack(pady=(42, 14))
        self.side_title = tk.Label(side, bg=CARD, fg=TEXT, font=font(11, "bold"))
        self.side_title.pack()
        self.side_text = tk.Label(side, bg=CARD, fg=MUTED, font=font(9), wraplength=190,
                                  justify="center")
        self.side_text.pack(pady=(6, 0))

        bottom = tk.Frame(side, bg=CARD)
        bottom.pack(side="bottom", pady=(0, 26))
        tk.Frame(bottom, bg=BORDER, width=30, height=2).pack(pady=(0, 14))
        tk.Label(bottom, text="Team Syntax Error", bg=CARD, fg=TEXT,
                 font=font(9, "bold")).pack()
        tk.Label(bottom, text="Powered by the GraphHopper API", bg=CARD, fg=MUTED,
                 font=font(9)).pack(pady=(2, 0))

    def draw_sidebar(self):
        canvas = self.steps_canvas
        canvas.delete("all")
        for number in (1, 2, 3):
            x, y = 125 + (number - 2) * 46, 24
            if number == self.step:
                canvas.create_oval(x - 15, y - 15, x + 15, y + 15, outline=PRIMARY, width=1.5)
                color = PRIMARY
            elif number < self.step:
                color = PRIMARY
            else:
                color = "#b6bfcc"
            canvas.create_text(x, y, text=str(number), fill=color, font=font(10, "bold"))
        canvas.create_line(110, 56, 140, 56, fill=BORDER, width=2)

        title, text = STEPS[self.step]
        self.side_title.configure(text=title)
        self.side_text.configure(text=text)
        self.art.delete("all")
        (self.draw_car, self.draw_city_pin, self.draw_summary_art)[self.step - 1]()

    def draw_car(self):
        c = self.art
        c.create_oval(36, 96, 136, 106, fill="#eef2f7", outline="")
        c.create_line(18, 104, 152, 104, fill=BORDER, width=2)
        c.create_polygon(54, 60, 68, 38, 106, 38, 122, 60, fill=CARD, outline=PRIMARY, width=2)
        c.create_line(87, 38, 87, 60, fill=PRIMARY, width=2)
        round_rect(c, 30, 58, 142, 90, 10, fill="#dbe8ff", outline=PRIMARY, width=2)
        c.create_oval(134, 66, 141, 73, fill="#ffd166", outline="")
        c.create_oval(31, 66, 37, 73, fill=ACCENT, outline="")
        for x in (60, 112):
            c.create_oval(x - 12, 80, x + 12, 104, fill=CARD, outline=PRIMARY, width=3)
            c.create_oval(x - 3, 89, x + 3, 95, fill=PRIMARY, outline="")
        cx, cy = draw_pin(c, 150, 40, 8, ACCENT)
        c.create_oval(cx - 3.5, cy - 3.5, cx + 3.5, cy + 3.5, fill=CARD, outline="")

    def draw_city_pin(self):
        c = self.art
        c.create_line(16, 104, 154, 104, fill=PRIMARY, width=2)
        c.create_rectangle(36, 50, 70, 104, fill="#dbe8ff", outline=PRIMARY, width=2)
        for y in (58, 70, 82):
            for x in (43, 57):
                c.create_rectangle(x, y, x + 7, y + 6, fill=PRIMARY, outline="")
        c.create_rectangle(102, 32, 132, 104, fill="#dbe8ff", outline=PRIMARY, width=2)
        for y in (40, 52, 64, 76):
            for x in (108, 119):
                c.create_rectangle(x, y, x + 6, y + 6, fill=PRIMARY, outline="")
        for x in (24, 146):
            c.create_line(x, 104, x, 88, fill=PRIMARY, width=2)
            c.create_oval(x - 9, 72, x + 9, 92, fill="#cfe3ff", outline=PRIMARY, width=2)
        c.create_oval(66, 98, 104, 108, fill=ACCENT_SOFT, outline="")
        cx, cy = draw_pin(c, 85, 103, 17, ACCENT)
        c.create_oval(cx - 9, cy - 9, cx + 9, cy + 9, fill=CARD, outline="")
        c.create_line(cx - 5, cy, cx - 1, cy + 4, cx + 5.5, cy - 4, fill=PRIMARY,
                      width=2.5, capstyle="round", joinstyle="round")

    def draw_summary_art(self):
        c = self.art
        c.create_oval(48, 100, 124, 110, fill="#eef2f7", outline="")
        round_rect(c, 52, 14, 114, 104, 8, fill=CARD, outline=PRIMARY, width=2)
        round_rect(c, 62, 26, 104, 36, 4, fill=PRIMARY_SOFT, outline="")
        for y, end in ((48, 102), (60, 102), (72, 88)):
            c.create_line(64, y, end, y, fill="#c8d6ea", width=4, capstyle="round")
        c.create_line(68, 88, 90, 84, fill=PRIMARY, width=2)
        c.create_oval(64, 84, 72, 92, fill=GREEN, outline="")
        c.create_oval(86, 80, 94, 88, fill=ACCENT, outline="")
        c.create_oval(102, 76, 132, 106, fill=GREEN, outline=CARD, width=3)
        c.create_line(110, 91, 115, 96, 124, 86, fill=CARD, width=3,
                      capstyle="round", joinstyle="round")

    # ----- reusable form pieces ----------------------------------------------
    def field_label(self, parent, text):
        return tk.Label(parent, text=text, bg=CARD, fg=MUTED, font=font(9, "bold"), anchor="w")

    def make_entry(self, parent, variable, show="", width=30):
        return tk.Entry(parent, textvariable=variable, show=show, width=width, relief="flat",
                        font=font(10), fg=TEXT, bg=CARD, insertbackground=TEXT,
                        highlightthickness=1, highlightbackground=BORDER,
                        highlightcolor=PRIMARY, disabledbackground=INPUT_OFF,
                        disabledforeground=MUTED)

    def make_toggles(self, parent, options, variable, width, on_change=None):
        """A row of pill buttons where only one can be selected."""
        buttons = {}

        def select(value):
            variable.set(value)
            for option, button in buttons.items():
                button.set_kind("selected" if option == value else "toggle")
            if on_change:
                on_change()

        for label, value in options:
            button = PillButton(parent, label, lambda v=value: select(v), width=width, height=36,
                                kind="selected" if variable.get() == value else "toggle")
            button.pack(side="left", padx=(0, 8))
            buttons[value] = button
        return select

    # ----- step 1: settings ----------------------------------------------------
    def build_step1(self):
        frame = tk.Frame(self.content, bg=CARD)

        self.field_label(frame, "API KEY").pack(fill="x")
        key_row = tk.Frame(frame, bg=CARD)
        key_row.pack(fill="x", pady=(6, 18))
        self.api_key = tk.StringVar(value=os.environ.get("GRAPHHOPPER_API_KEY", ""))
        self.key_entry = self.make_entry(key_row, self.api_key, show="•")
        self.key_entry.pack(side="left", fill="x", expand=True, ipady=8, ipadx=6)
        self.show_key = tk.Label(key_row, text="Show", bg=CARD, fg=PRIMARY,
                                 font=font(9, "bold"), cursor="hand2")
        self.show_key.pack(side="left", padx=(12, 0))
        self.show_key.bind("<Button-1>", lambda event: self.toggle_key())

        self.field_label(frame, "TRAVEL MODE").pack(fill="x")
        mode_row = tk.Frame(frame, bg=CARD)
        mode_row.pack(fill="x", pady=(6, 18))
        self.vehicle = tk.StringVar(value="car")
        self.select_vehicle = self.make_toggles(
            mode_row, [("Car", "car"), ("Bike", "bike"), ("Foot", "foot")], self.vehicle,
            width=96, on_change=self.on_settings_changed)

        self.field_label(frame, "UNITS").pack(fill="x")
        unit_row = tk.Frame(frame, bg=CARD)
        unit_row.pack(fill="x", pady=(6, 18))
        self.units = tk.StringVar(value="km")
        self.select_units = self.make_toggles(
            unit_row, [("Kilometers", "km"), ("Miles", "mi")], self.units,
            width=120, on_change=self.on_settings_changed)

        self.fuel_title = self.field_label(frame, "FUEL COST  (CAR ONLY, OPTIONAL)")
        self.fuel_title.pack(fill="x")
        fuel_row = tk.Frame(frame, bg=CARD)
        fuel_row.pack(fill="x", pady=(6, 6))
        self.efficiency = tk.StringVar()
        self.price = tk.StringVar()
        self.fuel_entries = []
        self.fuel_labels = []
        for variable in (self.efficiency, self.price):
            box = tk.Frame(fuel_row, bg=CARD)
            box.pack(side="left", padx=(0, 16))
            label = tk.Label(box, bg=CARD, fg=TEXT, font=font(9), anchor="w")
            label.pack(fill="x")
            entry = self.make_entry(box, variable, width=16)
            entry.pack(fill="x", ipady=7, ipadx=6, pady=(4, 0))
            self.fuel_labels.append(label)
            self.fuel_entries.append(entry)
        self.fuel_hint = tk.Label(frame, bg=CARD, fg=MUTED, font=font(9), anchor="w",
                                  text="Leave these empty to skip the cost estimate.")
        self.fuel_hint.pack(fill="x", pady=(4, 0))
        self.update_fuel_fields()
        return frame

    def toggle_key(self):
        hidden = self.key_entry["show"] != ""
        self.key_entry.configure(show="" if hidden else "•")
        self.show_key.configure(text="Hide" if hidden else "Show")

    def update_fuel_fields(self):
        """Match the fuel labels to the units and switch them off for bike/foot."""
        if self.units.get() == "km":
            self.fuel_labels[0].configure(text="Km per liter")
            self.fuel_labels[1].configure(text="Price per liter")
        else:
            self.fuel_labels[0].configure(text="Miles per gallon")
            self.fuel_labels[1].configure(text="Price per gallon")
        state = "normal" if self.vehicle.get() == "car" else "disabled"
        for entry in self.fuel_entries:
            entry.configure(state=state)

    def on_settings_changed(self):
        self.update_fuel_fields()
        if self.route and self.route["vehicle"] != self.vehicle.get():
            self.route = None
            self.map_message = ("Travel mode changed", "Click Find Route to update the map.")

    # ----- step 2: route and map -----------------------------------------------
    def build_step2(self):
        frame = tk.Frame(self.content, bg=CARD)
        self.stop_vars = []
        self.stop_rows = []
        self.stop_dots = []
        dots = [GREEN, ACCENT] + [PRIMARY] * (MAX_STOPS - 2)
        names = ["From", "To"] + ["Then"] * (MAX_STOPS - 2)
        for index in range(MAX_STOPS):
            row = tk.Frame(frame, bg=CARD)
            tk.Label(row, text=names[index], width=6, anchor="w", bg=CARD, fg=MUTED,
                     font=font(9, "bold")).pack(side="left")
            dot = tk.Canvas(row, width=14, height=14, bg=CARD, highlightthickness=0)
            dot.create_oval(2, 2, 12, 12, fill=dots[index], outline="", tags="dot")
            dot.pack(side="left", padx=(0, 10))
            self.stop_dots.append(dot)
            variable = tk.StringVar()
            variable.trace_add("write", lambda *args: self.on_stops_changed())
            entry = self.make_entry(row, variable)
            entry.pack(side="left", fill="x", expand=True, ipady=7, ipadx=6)
            entry.bind("<Return>", lambda event: self.find_route())
            self.stop_vars.append(variable)
            self.stop_rows.append(row)
            if index < 2:
                row.pack(fill="x", pady=4)

        actions = tk.Frame(frame, bg=CARD)
        actions.pack(fill="x", pady=(8, 0))
        self.add_stop_link = tk.Label(actions, text="+  Add stop", bg=CARD, fg=PRIMARY,
                                      font=font(9, "bold"), cursor="hand2")
        self.add_stop_link.pack(side="left")
        self.add_stop_link.bind("<Button-1>", lambda event: self.add_stop())
        self.find_button = PillButton(actions, "Find Route", self.find_route, kind="soft",
                                      width=120, height=34)
        self.find_button.pack(side="right")
        self.actions_row = actions

        self.map_canvas = tk.Canvas(frame, bg=MAP_BG, highlightthickness=1,
                                    highlightbackground=BORDER, height=220)
        self.map_canvas.pack(fill="both", expand=True, pady=(12, 0))
        self.map_canvas.bind("<Configure>", lambda event: self.draw_map())
        return frame

    def visible_stop_count(self):
        return sum(1 for row in self.stop_rows if row.winfo_manager())

    def add_stop(self):
        count = self.visible_stop_count()
        if count < MAX_STOPS:
            self.stop_rows[count].pack(fill="x", pady=4, after=self.stop_rows[count - 1])
        if count + 1 >= MAX_STOPS:
            self.add_stop_link.configure(text="Maximum of 5 places", fg=MUTED, cursor="")
        self.color_dots()

    def color_dots(self):
        """Green for the start, pink for the last place, blue for stops between,
        matching the pins on the map."""
        last = self.visible_stop_count() - 1
        for index, dot in enumerate(self.stop_dots):
            color = GREEN if index == 0 else ACCENT if index == last else PRIMARY
            dot.itemconfigure("dot", fill=color)

    def on_stops_changed(self):
        if self.route is not None and not self.busy:
            self.route = None
            self.map_message = ("Stops changed", "Click Find Route to update the map.")
            self.draw_map()

    def draw_map(self):
        """Draw the route preview, or a placeholder when there is no route yet."""
        c = self.map_canvas
        c.delete("all")
        width, height = c.winfo_width(), c.winfo_height()
        if width < 40 or height < 40:
            return
        for x in range(0, width, 28):
            c.create_line(x, 0, x, height, fill=MAP_GRID)
        for y in range(0, height, 28):
            c.create_line(0, y, width, y, fill=MAP_GRID)

        if self.route is None:
            title, text = self.map_message
            cx, cy = width / 2, height / 2 - 10
            head = draw_pin(c, cx, cy, 13, "#c3cedd")
            c.create_oval(head[0] - 5, head[1] - 5, head[0] + 5, head[1] + 5,
                          fill=MAP_BG, outline="")
            c.create_text(cx, cy + 24, text=title, fill=TEXT, font=font(10, "bold"))
            c.create_text(cx, cy + 44, text=text, fill=MUTED, font=font(9),
                          width=width - 40, justify="center")
            return

        stops, path = self.route["stops"], self.route["path"]
        coords = path.get("points", {}).get("coordinates") or [[s[1], s[0]] for s in stops]
        if len(coords) > 1500:                      # keep drawing fast on long routes
            coords = coords[::len(coords) // 1500 + 1] + [coords[-1]]
        lngs = [p[0] for p in coords] + [s[1] for s in stops]
        lats = [p[1] for p in coords] + [s[0] for s in stops]
        min_lng, max_lng, min_lat, max_lat = min(lngs), max(lngs), min(lats), max(lats)
        squash = math.cos(math.radians((min_lat + max_lat) / 2))
        span_x = max((max_lng - min_lng) * squash, 1e-6)
        span_y = max(max_lat - min_lat, 1e-6)
        pad, pad_top = 40, 60
        scale = min((width - 2 * pad) / span_x, (height - pad - pad_top) / span_y)
        off_x = (width - span_x * scale) / 2
        off_y = pad_top + ((height - pad - pad_top) - span_y * scale) / 2

        def to_xy(lng, lat):
            return off_x + (lng - min_lng) * squash * scale, off_y + (max_lat - lat) * scale

        line = [value for lng, lat in coords for value in to_xy(lng, lat)]
        if len(line) >= 4:
            c.create_line(*line, fill=CARD, width=10, capstyle="round", joinstyle="round")
            c.create_line(*line, fill=PRIMARY, width=5, capstyle="round", joinstyle="round")

        last = len(stops) - 1
        for index, (lat, lng, name) in enumerate(stops):
            x, y = to_xy(lng, lat)
            color = GREEN if index == 0 else ACCENT if index == last else PRIMARY
            if index == last:
                c.create_oval(x - 16, y - 7, x + 16, y + 7, fill=ACCENT_SOFT, outline="")
            hx, hy = draw_pin(c, x, y, 10, color)
            if 0 < index < last:
                c.create_text(hx, hy, text=str(index + 1), fill=CARD, font=font(8, "bold"))
            else:
                c.create_oval(hx - 4, hy - 4, hx + 4, hy + 4, fill=CARD, outline="")
            label = name.split(",")[0].upper()
            text_width = tkfont.Font(family=FONT, size=8, weight="bold").measure(label)
            chip_w = text_width + 22
            chip_x = hx + 18 + chip_w / 2              # to the right of the pin
            if chip_x + chip_w / 2 > width - 6:        # no room: put it on the left
                chip_x = hx - 18 - chip_w / 2
            chip_y = hy
            if index == last:
                round_rect(c, chip_x - chip_w / 2, chip_y - 11, chip_x + chip_w / 2,
                           chip_y + 11, 4, fill=ACCENT, outline="")
                c.create_text(chip_x, chip_y, text=label, fill=CARD, font=font(8, "bold"))
            else:
                round_rect(c, chip_x - chip_w / 2, chip_y - 11, chip_x + chip_w / 2,
                           chip_y + 11, 4, fill=CARD, outline=BORDER)
                c.create_text(chip_x, chip_y, text=label, fill=TEXT, font=font(8, "bold"))

        units = self.units.get()
        stats = "{0:,.1f} {1}   ·   {2}".format(
            convert_distance(path["distance"], units), units, friendly_duration(path["time"]))
        stats_w = tkfont.Font(family=FONT, size=9, weight="bold").measure(stats) + 28
        round_rect(c, 12, 12, 12 + stats_w, 42, 15, fill=CARD, outline=BORDER)
        c.create_text(12 + stats_w / 2, 27, text=stats, fill=TEXT, font=font(9, "bold"))

    # ----- step 3: summary -----------------------------------------------------
    def build_step3(self):
        frame = tk.Frame(self.content, bg=CARD)
        self.route_label = tk.Label(frame, bg=CARD, fg=MUTED, font=font(10), anchor="w",
                                    justify="left", wraplength=620)
        self.route_label.pack(fill="x")

        tiles = tk.Frame(frame, bg=CARD)
        tiles.pack(fill="x", pady=(12, 14))
        self.tiles = {}
        for column, name in enumerate(("Distance", "Duration", "Stops", "Fuel cost")):
            tiles.columnconfigure(column, weight=1, uniform="tiles")
            tile = tk.Frame(tiles, bg=CARD, highlightthickness=1, highlightbackground=BORDER,
                            padx=14, pady=10)
            tile.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 10, 0))
            value = tk.Label(tile, text="—", bg=CARD, fg=PRIMARY, font=font(15, "bold"),
                             anchor="w")
            value.pack(fill="x")
            caption = tk.Label(tile, text=name, bg=CARD, fg=MUTED, font=font(9), anchor="w")
            caption.pack(fill="x")
            self.tiles[name] = (value, caption)

        tk.Label(frame, text="TURN-BY-TURN DIRECTIONS", bg=CARD, fg=MUTED,
                 font=font(9, "bold"), anchor="w").pack(fill="x")
        table_box = tk.Frame(frame, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        table_box.pack(fill="both", expand=True, pady=(6, 10))
        self.table = ttk.Treeview(table_box, columns=("num", "instruction", "distance"),
                                  show="headings", style="Trip.Treeview", height=6)
        for column, heading, width, anchor, stretch in (
                ("num", "#", 44, "center", False), ("instruction", "INSTRUCTION", 420, "w", True),
                ("distance", "DISTANCE", 110, "e", False)):
            self.table.heading(column, text=heading, anchor=anchor)
            self.table.column(column, width=width, anchor=anchor, stretch=stretch)
        self.table.tag_configure("stripe", background="#f7f9fc")
        scrollbar = ttk.Scrollbar(table_box, orient="vertical", command=self.table.yview,
                                  style="Trip.Vertical.TScrollbar")
        self.table.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.table.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=4)

        export = tk.Frame(frame, bg=CARD)
        export.pack(fill="x")
        PillButton(export, "Save as CSV", lambda: self.save_trip("csv"), kind="outline",
                   width=118, height=34).pack(side="left")
        PillButton(export, "Save as TXT", lambda: self.save_trip("txt"), kind="outline",
                   width=118, height=34).pack(side="left", padx=10)
        self.saved_label = tk.Label(export, bg=CARD, fg=GREEN, font=font(9), anchor="w")
        self.saved_label.pack(side="left", fill="x", expand=True)
        return frame

    def render_summary(self):
        stops, path, vehicle = self.route["stops"], self.route["path"], self.route["vehicle"]
        units = self.units.get()
        distance = convert_distance(path["distance"], units)
        names = [stop[2].split(",")[0] for stop in stops]
        self.route_label.configure(
            text=(" " + ARROW + " ").join(names) + "     ·     by " + vehicle)

        self.tiles["Distance"][0].configure(text="{0:,.1f} {1}".format(distance, units))
        self.tiles["Duration"][0].configure(text=friendly_duration(path["time"]))
        self.tiles["Stops"][0].configure(text=str(len(stops)))
        self.summary_rows = [
            ("Route", (" " + ARROW + " ").join(stop[2] for stop in stops)),
            ("Travel mode", vehicle),
            ("Total distance", "{0:.2f} {1}".format(distance, units)),
            ("Trip duration", format_duration(path["time"])),
        ]
        cost_value, cost_caption = self.tiles["Fuel cost"]
        if vehicle == "car" and self.fuel is not None:
            efficiency, price = self.fuel
            fuel_used = distance / efficiency
            fuel_unit = "L" if units == "km" else "gal"
            cost_value.configure(text="{0:,.2f}".format(fuel_used * price))
            cost_caption.configure(text="Fuel cost · {0:.2f} {1}".format(fuel_used, fuel_unit))
            self.summary_rows += [("Fuel used", "{0:.2f} {1}".format(fuel_used, fuel_unit)),
                                  ("Fuel cost", "{0:,.2f}".format(fuel_used * price))]
        else:
            cost_value.configure(text="—")
            cost_caption.configure(text="Fuel cost (car only)")

        self.table.delete(*self.table.get_children())
        for number, step in enumerate(path.get("instructions", []), start=1):
            step_distance = convert_distance(step.get("distance", 0), units)
            tags = ("stripe",) if number % 2 == 0 else ()
            self.table.insert("", "end", tags=tags, values=(
                number, step.get("text", ""), "{0:.2f} {1}".format(step_distance, units)))
        self.saved_label.configure(text="")

    def save_trip(self, extension):
        """Save the trip summary and directions to a .csv or .txt file."""
        if self.route is None:
            return
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        kinds = {"csv": ("CSV file", "*.csv"), "txt": ("Text file", "*.txt")}
        filename = filedialog.asksaveasfilename(
            title="Save trip", initialfile="trip_" + stamp + "." + extension,
            defaultextension="." + extension, filetypes=[kinds[extension]])
        if not filename:
            return
        units = self.units.get()
        steps = self.route["path"].get("instructions", [])
        try:
            if extension == "txt":
                with open(filename, "w", encoding="utf-8") as file:
                    file.write("TRIP SUMMARY\n")
                    for field, value in self.summary_rows:
                        file.write(field + ": " + value + "\n")
                    file.write("\nDIRECTIONS\n")
                    for number, step in enumerate(steps, start=1):
                        file.write("{0}. {1} ({2:.2f} {3})\n".format(
                            number, step.get("text", ""),
                            convert_distance(step.get("distance", 0), units), units))
            else:
                with open(filename, "w", newline="", encoding="utf-8") as file:
                    writer = csv.writer(file)
                    for field, value in self.summary_rows:
                        writer.writerow([field, value])
                    writer.writerow([])
                    writer.writerow(["Step", "Instruction", "Distance (" + units + ")"])
                    for number, step in enumerate(steps, start=1):
                        writer.writerow([number, step.get("text", ""), "{0:.2f}".format(
                            convert_distance(step.get("distance", 0), units))])
        except OSError as problem:
            messagebox.showerror("Could not save", str(problem))
            return
        self.saved_label.configure(text="Saved to " + os.path.basename(filename))

    # ----- moving between steps ------------------------------------------------
    def show_step(self, number):
        self.step = number
        for frame in self.step_frames:
            frame.pack_forget()
        self.step_frames[number - 1].pack(fill="both", expand=True)
        self.title_label.configure(text=STEPS[number][0])
        self.draw_sidebar()
        if number == 1:
            self.prev_button.pack_forget()
        elif not self.prev_button.winfo_manager():
            self.prev_button.pack(side="left")
        self.next_button.set_text("Plan New Trip" if number == 3 else "Next Step   ›")
        if number == 2:
            self.after(20, self.draw_map)
        if number == 3:
            self.render_summary()

    def on_previous(self):
        if not self.busy and self.step > 1:
            self.show_step(self.step - 1)

    def on_next(self):
        if self.busy:
            return
        if self.step == 1:
            if self.api_key.get().strip() == "":
                messagebox.showwarning("Missing API key", "Please paste your GraphHopper API key.")
                return
            self.fuel = None
            if self.vehicle.get() == "car":
                try:
                    efficiency = parse_positive(self.efficiency.get(), self.fuel_labels[0]["text"])
                    price = parse_positive(self.price.get(), self.fuel_labels[1]["text"])
                except ValueError as problem:
                    messagebox.showwarning("Check fuel details", str(problem))
                    return
                if efficiency is not None and price is not None:
                    self.fuel = (efficiency, price)
            self.show_step(2)
        elif self.step == 2:
            if self.route is not None:
                self.show_step(3)
            else:
                self.find_route(advance=True)
        else:
            self.new_trip()

    def new_trip(self):
        self.route = None
        for variable in self.stop_vars:
            variable.set("")
        for row in self.stop_rows[2:]:
            row.pack_forget()
        self.add_stop_link.configure(text="+  Add stop", fg=PRIMARY, cursor="hand2")
        self.color_dots()
        self.map_message = ("Your route will appear here",
                            "Enter your stops, then click Find Route.")
        self.show_step(2)

    # ----- finding the route (in the background) -------------------------------
    def find_route(self, advance=False):
        if self.busy:
            return
        places = [variable.get().strip() for variable in self.stop_vars]
        if places[0] == "" or places[1] == "":
            messagebox.showwarning("Missing stops", "Please enter where you start (From) "
                                   "and where you are going (To).")
            return
        places = [place for place in places if place]
        self.set_busy(True)
        self.map_message = ("Finding your route...", "Asking GraphHopper for directions.")
        self.draw_map()
        worker = threading.Thread(target=self.fetch_route, daemon=True, args=(
            self.api_key.get().strip(), places, self.vehicle.get(), advance))
        worker.start()
        self.after(100, self.check_results)

    def fetch_route(self, key, places, vehicle, advance):
        """Runs in a background thread so the window does not freeze."""
        try:
            stops = [geocode(place, key) for place in places]
            path = get_route([(lat, lng) for lat, lng, _ in stops], vehicle, key)
            self.results.put(("ok", ({"stops": stops, "path": path, "vehicle": vehicle},
                                     advance)))
        except ApiError as problem:
            self.results.put(("error", str(problem)))
        except Exception as problem:  # anything unexpected still shows a message
            self.results.put(("error", "Something went wrong: " + str(problem)))

    def check_results(self):
        """Pick up the background thread's answer without blocking the window."""
        try:
            kind, payload = self.results.get_nowait()
        except queue.Empty:
            self.after(100, self.check_results)
            return
        self.set_busy(False)
        if kind == "ok":
            self.route, advance = payload
            self.draw_map()
            if advance:
                self.show_step(3)
        else:
            self.map_message = ("Could not get the route", payload)
            self.draw_map()
            messagebox.showerror("Could not get route", payload)

    def set_busy(self, busy):
        self.busy = busy
        self.find_button.set_enabled(not busy)
        self.next_button.set_enabled(not busy)
        self.prev_button.set_enabled(not busy)
        self.configure(cursor="watch" if busy else "")


if __name__ == "__main__":
    app = TripPlannerApp()
    app.mainloop()
