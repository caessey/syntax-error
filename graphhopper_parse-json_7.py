import csv
import os
from datetime import datetime
 
import requests
import urllib.parse
 
geocode_url = "https://graphhopper.com/api/1/geocode?"
route_url = "https://graphhopper.com/api/1/route?"
REQUEST_TIMEOUT = 10  # seconds to wait for GraphHopper before giving up
 
 
# ---------------------------------------------------------------------------
# FEATURE 1: Colored output (added in branch feature-ui-colors)
# ANSI color codes make headings, success messages and errors easy to spot.
# No extra library is needed.
# ---------------------------------------------------------------------------
class Color:
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    END = "\033[0m"
 
 
if os.name == "nt":  # lets Windows terminals show colors
    os.system("")
 
 
def info(text):
    print(Color.CYAN + text + Color.END)
 
 
def success(text):
    print(Color.GREEN + text + Color.END)
 
 
def warning(text):
    print(Color.YELLOW + text + Color.END)
 
 
def error(text):
    print(Color.RED + Color.BOLD + "Error: " + text + Color.END)
 
 
def heading(text):
    line = "=" * 60
    print("\n" + Color.HEADER + Color.BOLD + line + "\n" + text.center(60) + "\n" + line + Color.END)
 
 
def convert_distance(meters, units):
    """FEATURE 2: Convert meters to kilometers or miles."""
    km = meters / 1000
    if units == "km":
        return km
    return km / 1.60934
 
 
# ---------------------------------------------------------------------------
# FEATURE 4: Directions table, trip summary and fuel estimate
# (branch feature-summary-table)
# ---------------------------------------------------------------------------
def shorten(text, width):
    """Cut long text so the table columns stay aligned."""
    if len(text) <= width:
        return text
    return text[: width - 3] + "..."
 
 
def ask_number(prompt):
    """Ask for a positive number. Pressing Enter skips (returns None)."""
    while True:
        answer = input(Color.BOLD + prompt + Color.END).strip()
        if answer == "":
            return None
        try:
            value = float(answer)
            if value > 0:
                return value
        except ValueError:
            pass
        warning("Please enter a positive number, or press Enter to skip.")
 
 
def print_summary(route_names, vehicle, meters, milliseconds, units, fuel):
    """Show the trip summary box, including fuel cost for car trips."""
    distance = convert_distance(meters, units)
    sec = int(milliseconds / 1000 % 60)
    min = int(milliseconds / 1000 / 60 % 60)
    hr = int(milliseconds / 1000 / 60 / 60)
    heading("TRIP SUMMARY")
    print(Color.BLUE + "Route:          " + Color.END + route_names)
    print(Color.BLUE + "Travel mode:    " + Color.END + vehicle)
    print(Color.BLUE + "Total distance: " + Color.END + "{0:.2f} {1}".format(distance, units))
    print(Color.BLUE + "Trip duration:  " + Color.END + "{0:02d}:{1:02d}:{2:02d}".format(hr, min, sec))
    if fuel is not None:
        efficiency, price = fuel
        fuel_unit = "L" if units == "km" else "gal"
        fuel_used = distance / efficiency
        print(Color.BLUE + "Fuel used:      " + Color.END + "{0:.2f} {1}".format(fuel_used, fuel_unit))
        print(Color.BLUE + "Fuel cost:      " + Color.END + "{0:,.2f}".format(fuel_used * price))
 
 
def print_directions(instructions, units):
    """Show turn-by-turn directions as a numbered table."""
    heading("TURN-BY-TURN DIRECTIONS")
    print(Color.BOLD + "{0:>3}  {1:<44}  {2:>9}".format("#", "Instruction", "Distance") + Color.END)
    print("-" * 60)
    for number, step in enumerate(instructions, start=1):
        distance = convert_distance(step["distance"], units)
        print("{0:>3}  {1:<44}  {2:>6.2f} {3}".format(number, shorten(step["text"], 44), distance, units))
    print("-" * 60)
 
 
# ---------------------------------------------------------------------------
# FEATURE 5: Error handling, safe API key and export
# (branch feature-export-errors)
# ---------------------------------------------------------------------------
def get_api_key():
    """Read the key from the GRAPHHOPPER_API_KEY environment variable,
    or ask the user. The key is never stored in the code or on GitHub."""
    key = os.environ.get("GRAPHHOPPER_API_KEY", "").strip()
    if key:
        info("Using API key from the GRAPHHOPPER_API_KEY environment variable.")
        return key
    while key == "":
        key = input(Color.BOLD + "Enter your GraphHopper API key: " + Color.END).strip()
    return key
 
 
def call_api(url):
    """Send a GET request. Returns (status, data), or (None, None) if the
    request failed, after printing a clear error message."""
    try:
        reply = requests.get(url, timeout=REQUEST_TIMEOUT)
    except requests.exceptions.ConnectionError:
        error("Cannot reach GraphHopper. Check your internet connection.")
        return None, None
    except requests.exceptions.Timeout:
        error("GraphHopper took too long to answer. Please try again.")
        return None, None
    try:
        data = reply.json()
    except ValueError:
        error("Unexpected response from GraphHopper (status " + str(reply.status_code) + ").")
        return None, None
    if reply.status_code == 401:
        error("Invalid API key. Check the key in your GraphHopper dashboard.")
    elif reply.status_code == 429:
        error("API limit reached. Wait a moment or check your daily credits.")
    return reply.status_code, data
 
 
def export_trip(route_names, vehicle, path, units):
    """Save the trip to a .txt or .csv file in the current folder."""
    choice = input(Color.BOLD + "Save this trip? (1) .txt  (2) .csv  (Enter) No: " + Color.END).strip()
    if choice not in ("1", "2"):
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    distance = "{0:.2f} {1}".format(convert_distance(path["distance"], units), units)
    try:
        if choice == "1":
            filename = "trip_" + stamp + ".txt"
            with open(filename, "w", encoding="utf-8") as file:
                file.write("Route: " + route_names + "\n")
                file.write("Travel mode: " + vehicle + "\n")
                file.write("Total distance: " + distance + "\n\nDIRECTIONS\n")
                for number, step in enumerate(path["instructions"], start=1):
                    step_distance = convert_distance(step["distance"], units)
                    file.write("{0}. {1} ({2:.2f} {3})\n".format(number, step["text"], step_distance, units))
        else:
            filename = "trip_" + stamp + ".csv"
            with open(filename, "w", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerow(["Route", route_names])
                writer.writerow(["Travel mode", vehicle])
                writer.writerow(["Total distance", distance])
                writer.writerow([])
                writer.writerow(["Step", "Instruction", "Distance (" + units + ")"])
                for number, step in enumerate(path["instructions"], start=1):
                    step_distance = convert_distance(step["distance"], units)
                    writer.writerow([number, step["text"], "{0:.2f}".format(step_distance)])
        success("Trip saved to " + filename)
    except OSError as exc:
        error("Could not save the file: " + str(exc))
 
 
def geocoding(location, key):
    while location == "":
        location = input("Enter the location again: ")
    url = geocode_url + urllib.parse.urlencode({"q": location, "limit": "1", "key": key})
    json_status, json_data = call_api(url)
    if json_status is None:
        return None, "null", "null", location
 
    if json_status == 200 and len(json_data["hits"]) != 0:
        lat = json_data["hits"][0]["point"]["lat"]
        lng = json_data["hits"][0]["point"]["lng"]
        name = json_data["hits"][0]["name"]
 
        if "country" in json_data["hits"][0]:
            country = json_data["hits"][0]["country"]
        else:
            country = ""
 
        if "state" in json_data["hits"][0]:
            state = json_data["hits"][0]["state"]
        else:
            state = ""
 
        if len(state) != 0 and len(country) != 0:
            new_loc = name + ", " + state + ", " + country
        elif len(state) != 0:
            new_loc = name + ", " + country
        else:
            new_loc = name
 
        success("  Found: " + new_loc)
    else:
        lat = "null"
        lng = "null"
        new_loc = location
        if json_status == 200:
            error('Could not find "' + location + '".')
        elif json_status not in (401, 429):
            error("Geocode API status " + str(json_status) + ": " + json_data.get("message", ""))
    return json_status, lat, lng, new_loc
 
 
heading("GRAPHHOPPER TRIP PLANNER")
info("Type q at any prompt to quit.")
key = get_api_key()
 
while True:
    # -----------------------------------------------------------------------
    # FEATURE 2: Travel mode menu and unit choice (branch feature-units-mode)
    # The user picks a number instead of typing the profile name, and
    # chooses whether distances are shown in kilometers or miles.
    # -----------------------------------------------------------------------
    heading("TRIP SETTINGS")
    travel_modes = {"1": "car", "2": "bike", "3": "foot"}
    choice = input(Color.BOLD + "Travel mode? (1) Car  (2) Bike  (3) Foot: " + Color.END).strip()
    if choice == "quit" or choice == "q":
        break
    while choice not in travel_modes:
        warning("Please enter 1, 2 or 3.")
        choice = input(Color.BOLD + "Travel mode? (1) Car  (2) Bike  (3) Foot: " + Color.END).strip()
    vehicle = travel_modes[choice]
 
    unit_choice = input(Color.BOLD + "Units? (1) Kilometers  (2) Miles: " + Color.END).strip()
    if unit_choice == "quit" or unit_choice == "q":
        break
    while unit_choice not in ("1", "2"):
        warning("Please enter 1 or 2.")
        unit_choice = input(Color.BOLD + "Units? (1) Kilometers  (2) Miles: " + Color.END).strip()
    units = "km" if unit_choice == "1" else "mi"
 
    # -----------------------------------------------------------------------
    # FEATURE 3: Multiple stops (branch feature-multi-stops)
    # The user enters a start, a destination, then optional extra stops.
    # GraphHopper's free plan allows up to 5 points per route.
    # -----------------------------------------------------------------------
    max_stops = 5
    stops = []
    quit_program = False
    while len(stops) < max_stops:
        if len(stops) == 0:
            prompt = "Starting Location: "
        elif len(stops) == 1:
            prompt = "Destination: "
        else:
            prompt = "Next stop (press Enter to finish, max " + str(max_stops) + " places): "
        place = input(Color.BOLD + prompt + Color.END).strip()
        if place == "quit" or place == "q":
            quit_program = True
            break
        if place == "":
            if len(stops) >= 2:
                break
            warning("Please enter a location.")
            continue
        result = geocoding(place, key)
        if result[0] == 200 and result[1] != "null":
            stops.append(result)
    if quit_program:
        break
 
    points = ""
    for stop in stops:
        points = points + "&point=" + str(stop[1]) + "%2C" + str(stop[2])
    paths_url = route_url + urllib.parse.urlencode({"key": key, "vehicle": vehicle}) + points
    paths_status, paths_data = call_api(paths_url)
    if paths_status is None:
        continue
 
    route_names = " -> ".join(stop[3] for stop in stops)
 
    if paths_status == 200:
        path = paths_data["paths"][0]
 
        # Fuel estimate only makes sense for car trips
        fuel = None
        if vehicle == "car":
            if units == "km":
                efficiency = ask_number("Car fuel efficiency in km per liter (Enter to skip): ")
                price_prompt = "Fuel price per liter (Enter to skip): "
            else:
                efficiency = ask_number("Car fuel efficiency in miles per gallon (Enter to skip): ")
                price_prompt = "Fuel price per gallon (Enter to skip): "
            if efficiency is not None:
                price = ask_number(price_prompt)
                if price is not None:
                    fuel = (efficiency, price)
 
        print_summary(route_names, vehicle, path["distance"], path["time"], units, fuel)
        print_directions(path["instructions"], units)
        export_trip(route_names, vehicle, path, units)
    elif paths_status not in (401, 429):
        error(paths_data.get("message", "No route found."))
 
success("\nGoodbye!")
