# GraphHopper Trip Planner

DEVASC Project Activity 3 (Option 1: Feature Enhancements), Team Syntax Error

A Python command-line app that plans routes using the GraphHopper Geocoding and Routing APIs. It enhances the final code from Cisco DEVASC Lab 4.9.2, "Integrate a REST API in a Python Application". The lab now uses GraphHopper in place of MapQuest.

## Features

| # | Feature | Branch |
|---|---------|--------|
| 1 | Colored output for headings, success, warning and error messages | `feature-ui-colors` |
| 2 | Numbered travel mode menu (car, bike, foot) and a kilometers/miles choice | `feature-units-mode` |
| 3 | Multiple stops, up to 5 places in one route | `feature-multi-stops` |
| 4 | Trip summary, turn-by-turn directions table, and a fuel cost estimate for car trips | `feature-summary-table` |
| 5 | Export to .txt/.csv, clear error messages, and an API key prompt so the key is never stored in the code | `feature-export-errors` |

## Requirements

- Python 3
- The `requests` library: `pip install requests`
- A free GraphHopper API key from https://graphhopper.com (Dashboard → API Keys)

## How to run

```
git clone https://github.com/caessey/syntax-error.git
cd syntax-error
python3 graphhopper_parse-json_7.py
```

When asked, paste your GraphHopper API key. You can also set it as an environment variable named `GRAPHHOPPER_API_KEY` so the app does not ask.

Type `q` at any prompt to quit.

## Example

1. Travel mode: `1` (Car)
2. Units: `1` (Kilometers)
3. Starting location: `Quezon City`
4. Destination: `Tagaytay`
5. Next stop: `Batangas City`, then press Enter to finish
6. Fuel efficiency `12` km/L, price `65` per liter (or press Enter to skip)
7. Save as `2` (.csv)

The app shows a trip summary and a directions table, then saves the trip to a file such as `trip_20261103_200032.csv`.

## Code structure

Each feature is marked in the code with a `# FEATURE n` comment header.

| Function | What it does |
|----------|--------------|
| `info()`, `success()`, `warning()`, `error()`, `heading()` | Print colored messages (Feature 1) |
| `convert_distance()` | Converts meters to km or miles (Feature 2) |
| `shorten()`, `ask_number()`, `print_summary()`, `print_directions()` | Trip summary, fuel cost and directions table (Feature 4) |
| `get_api_key()` | Reads the API key from the environment or asks the user (Feature 5) |
| `call_api()` | Sends API requests and handles network, key and limit errors (Feature 5) |
| `export_trip()` | Saves the trip to .txt or .csv (Feature 5) |
| `geocoding()` | Turns a place name into coordinates (from the original lab) |

The main loop at the bottom asks for trip settings and stops (Features 2 and 3), calls the Routing API, then shows and exports the results.

## How to continue the project

1. Create a new branch from `main`, for example `feature-route-map`.
2. Add your feature as a new function with a `# FEATURE n` header and a docstring.
3. Open a pull request into `main` and ask a teammate to review it before merging.

## Backlog (future enhancements)

- Interactive map of the route
- Trip history log
- Avoid tolls or highways option
- Round-trip calculation
- Live weather at the destination
- GUI or web version
