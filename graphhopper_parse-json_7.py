import os
import requests
import urllib.parse
 
geocode_url = "https://graphhopper.com/api/1/geocode?"
route_url = "https://graphhopper.com/api/1/route?"
key = ""  # Paste your GraphHopper API key here (never upload it to GitHub)
 
 
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
 
 
def geocoding(location, key):
    while location == "":
        location = input("Enter the location again: ")
    url = geocode_url + urllib.parse.urlencode({"q": location, "limit": "1", "key": key})
    replydata = requests.get(url)
    json_data = replydata.json()
    json_status = replydata.status_code
 
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
        if json_status != 200:
            error("Geocode API status " + str(json_status) + ": " + json_data["message"])
        else:
            error('Could not find "' + location + '".')
    return json_status, lat, lng, new_loc
 
 
heading("GRAPHHOPPER TRIP PLANNER")
info("Type q at any prompt to quit.")
 
while True:
    heading("VEHICLE PROFILES: car, bike, foot")
    profile = ["car", "bike", "foot"]
    vehicle = input(Color.BOLD + "Enter a vehicle profile from the list above: " + Color.END)
    if vehicle == "quit" or vehicle == "q":
        break
    elif vehicle in profile:
        vehicle = vehicle
    else:
        vehicle = "car"
        warning("No valid vehicle profile was entered. Using the car profile.")
 
    loc1 = input(Color.BOLD + "Starting Location: " + Color.END)
    if loc1 == "quit" or loc1 == "q":
        break
    orig = geocoding(loc1, key)
 
    loc2 = input(Color.BOLD + "Destination: " + Color.END)
    if loc2 == "quit" or loc2 == "q":
        break
    dest = geocoding(loc2, key)
 
    if orig[0] == 200 and dest[0] == 200 and orig[1] != "null" and dest[1] != "null":
        op = "&point=" + str(orig[1]) + "%2C" + str(orig[2])
        dp = "&point=" + str(dest[1]) + "%2C" + str(dest[2])
        paths_url = route_url + urllib.parse.urlencode({"key": key, "vehicle": vehicle}) + op + dp
        reply = requests.get(paths_url)
        paths_status = reply.status_code
        paths_data = reply.json()
 
        heading("Directions from " + orig[3] + " to " + dest[3] + " by " + vehicle)
 
        if paths_status == 200:
            miles = (paths_data["paths"][0]["distance"]) / 1000 / 1.61
            km = (paths_data["paths"][0]["distance"]) / 1000
            sec = int(paths_data["paths"][0]["time"] / 1000 % 60)
            min = int(paths_data["paths"][0]["time"] / 1000 / 60 % 60)
            hr = int(paths_data["paths"][0]["time"] / 1000 / 60 / 60)
            print(Color.BLUE + "Distance Traveled: " + Color.END + "{0:.1f} miles / {1:.1f} km".format(miles, km))
            print(Color.BLUE + "Trip Duration:     " + Color.END + "{0:02d}:{1:02d}:{2:02d}".format(hr, min, sec))
            print("-" * 60)
            for each in range(len(paths_data["paths"][0]["instructions"])):
                path = paths_data["paths"][0]["instructions"][each]["text"]
                distance = paths_data["paths"][0]["instructions"][each]["distance"]
                print("{0} ( {1:.1f} km / {2:.1f} miles )".format(path, distance / 1000, distance / 1000 / 1.61))
            print("-" * 60)
        else:
            error(paths_data["message"])
 
success("\nGoodbye!")
 
