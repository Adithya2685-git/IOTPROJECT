import requests
import json
import time
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Configuration ---
AUTH_CREDENTIALS = ("admin", "admin")
HEADERS = {
    "X-M2M-Origin": "admin:admin",
    "Accept": "application/json"
}

# MongoDB config
MONGO_URI = "mongodb://localhost:27017/" # Default MongoDB URI
MONGO_DB_NAME = "om2m_data"         # Database name in MongoDB
MONGO_COLLECTION_NAME = "sensor_readings" # Collection name to store all sensor data

# Define the list of data sources to monitor
# Add more dictionaries to this list for each sensor/data source you have
# Use ?rcn=4 for latest N entries, use /la for the single latest entry
OM2M_DATA_SOURCES = [
    {
        'name': 'voice_audio',
        'url': "http://192.168.158.66:8080/~/in-cse/in-name/voice_command/audio_upload?rcn=4"
    },
    {
        'name': 'gas_sensor',
        'url': "http://192.168.158.66:8080/~/in-cse/in-name/gas_sensor/data/la"
    },
    {
        'name': 'fall_sensor',
        'url': "http://192.168.158.66:8080/~/in-cse/in-name/fall_sensor/fall_data/la"
    },
    # Add other sources here, e.g.:
    # {
    #     'name': 'temperature_sensor',
    #     'url': "http://192.168.158.66:8080/~/in-cse/in-name/temp_sensor_ae/temp_container?rcn=4"
    # },
]


# Fetch interval in seconds
FETCH_INTERVAL = 4

# --- Database Connection ---
def get_mongo_collection():
    """ Establishes MongoDB connection and returns the collection object. """
    try:
        client = MongoClient(MONGO_URI)
        # The ismaster command is cheap and does not require auth.
        client.admin.command('ismaster')
        db = client[MONGO_DB_NAME]
        collection = db[MONGO_COLLECTION_NAME]
        logging.info(f"Connected to MongoDB: Database '{MONGO_DB_NAME}', Collection '{MONGO_COLLECTION_NAME}'")
        # Ensure an index on 'ri' for faster lookups/updates and uniqueness
        collection.create_index('ri', unique=True)
        logging.info("Ensured unique index on 'ri' field.")
        return collection
    except ConnectionFailure as e:
        logging.error(f"Could not connect to MongoDB: {e}")
        logging.error("Please ensure MongoDB server is running and accessible at " + MONGO_URI)
        return None
    except OperationFailure as e:
         logging.error(f"MongoDB operation failed (e.g., index creation): {e}")
         return None
    except Exception as e:
        logging.error(f"An unexpected error occurred during MongoDB connection: {e}")
        return None

# --- OM2M Fetching and Parsing Functions ---

def fetch_om2m_data(url):
    """ Fetches data from a specific OM2M URL. """
    logging.info(f"Fetching data from: {url}")
    try:
        response = requests.get(url, auth=AUTH_CREDENTIALS, headers=HEADERS)
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        data = response.json()
        logging.info(f"Successfully fetched data from {url}")
        return data
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching data from OM2M URL {url}: {e}")
        return None # Return None on error
    except json.JSONDecodeError as e:
        logging.error(f"Error decoding JSON response from OM2M URL {url}: {e}")
        # logging.debug(f"Response text: {response.text[:500]}...") # Log part of the response
        return None
    except Exception as e:
        logging.error(f"An unexpected error occurred during fetching from URL {url}: {e}")
        return None

def extract_entries_from_response(data):
    """
    Extracts m2m:cin entries from various typical OM2M response structures,
    including responses for ?rcn=4 and /la.
    Returns a list of m2m:cin dictionaries.
    """
    if data is None:
        return []

    # Case 1: Response from ?rcn=4 - list/dict under m2m:cnt -> m2m:cin
    if isinstance(data, dict) and "m2m:cnt" in data:
        container_data = data["m2m:cnt"]
        if isinstance(container_data, dict) and "m2m:cin" in container_data:
            entries = container_data["m2m:cin"]
            if isinstance(entries, dict):
                return [entries] # Single CIN under m2m:cnt (less common for rcn=4 list)
            elif isinstance(entries, list):
                return entries # List of CINs under m2m:cnt (common for rcn=4)
            # else: unexpected type, fall through

    # Case 2: Response from /la - single m2m:cin, possibly under m2m:rsp -> pc
    if isinstance(data, dict):
        # Check for direct m2m:cin (less common for /la via HTTP GET, but possible)
        if "m2m:cin" in data and isinstance(data["m2m:cin"], dict):
             return [data["m2m:cin"]]

        # Check for m2m:rsp -> pc -> m2m:cin (very common for /la via HTTP GET)
        if "m2m:rsp" in data and isinstance(data["m2m:rsp"], dict):
            rsp_data = data["m2m:rsp"]
            if "pc" in rsp_data and isinstance(rsp_data["pc"], dict):
                pc_data = rsp_data["pc"]
                if "m2m:cin" in pc_data and isinstance(pc_data["m2m:cin"], dict):
                    return [pc_data["m2m:cin"]] # Found a single CIN under pc

    # If none of the expected structures match
    # logging.warning("Could not find m2m:cin entries in the expected structures of the response.")
    return []


# --- Data Storage Logic ---
def store_or_update_entries(collection, entries, source_name):
    """ Stores or updates fetched entries in MongoDB, adding source info. """
    if not entries:
        logging.info(f"No new entries found to process for source: {source_name}.")
        return

    logging.info(f"Processing {len(entries)} entries for storage from source: {source_name}...")
    inserted_count = 0
    updated_count = 0
    up_to_date_count = 0
    error_count = 0

    for entry in entries:
        # Ensure 'ri' exists, as it's our unique identifier
        if 'ri' not in entry:
            logging.warning(f"Skipping entry without 'ri' from source {source_name}: {entry}")
            error_count += 1
            continue

        resource_id = entry['ri']

        # Decide what fields to store. Add the source_name.
        # Note: The structure of 'con' will vary by sensor type.
        data_to_store = {
            'ri': entry.get('ri'),
            'source_name': source_name, # <-- Add the source name here
            'rn': entry.get('rn'), # Resource Name (optional)
            'ct': entry.get('ct'), # Creation Time
            'lt': entry.get('lt'), # Last Modified Time
            'st': entry.get('st'), # State Tag (useful for tracking changes)
            'cs': entry.get('cs'), # Content Size (optional)
            'con': entry.get('con'),# Content (the actual data, e.g., base64 audio, sensor value)
            # Add other standard CIN fields if needed, e.g., 'pi' (Parent ID)
            'pi': entry.get('pi')
        }

        # Optional: You might want to add logic here to parse the 'con' field
        # based on the 'source_name' if the data format in 'con' is structured.
        # Example:
        # if source_name == 'gas_sensor' and isinstance(data_to_store['con'], str):
        #     try:
        #         gas_values = {}
        #         # Assuming 'con' is like "CO:100,CH4:50"
        #         for item in data_to_store['con'].split(','):
        #              key, val = item.split(':')
        #              gas_values[key.strip()] = float(val.strip())
        #         data_to_store['parsed_content'] = gas_values
        #     except Exception as parse_error:
        #         logging.warning(f"Failed to parse 'con' for {source_name} ri {resource_id}: {parse_error}")


        try:
            # Use update_one with upsert=True to insert if ri doesn't exist, or update if it does
            result = collection.update_one(
                {'ri': resource_id},       # Filter: Find document by resource ID
                {'$set': data_to_store},   # Update: Set/replace fields with new data
                upsert=True                # Option: Insert if no matching document found
            )

            if result.upserted_id is not None:
                inserted_count += 1
                logging.info(f"Inserted new document with ri: {resource_id} from {source_name}")
            elif result.modified_count > 0:
                updated_count += 1
                logging.info(f"Updated document with ri: {resource_id} from {source_name}")
            else:
                 up_to_date_count += 1
                 # logging.debug(f"Document with ri: {resource_id} from {source_name} already up-to-date.") # Too verbose


        except OperationFailure as e:
            logging.error(f"MongoDB operation failed for ri {resource_id} from {source_name}: {e}")
            error_count += 1
        except Exception as e:
            logging.error(f"An unexpected error occurred storing ri {resource_id} from {source_name}: {e}")
            error_count += 1

    logging.info(f"Finished storing entries for {source_name}: Inserted {inserted_count}, Updated {updated_count}, Up-to-date {up_to_date_count}, Errors {error_count}")


# --- Main Execution Loop ---
def main():
    # Get MongoDB collection connection
    collection = get_mongo_collection()
    if collection is None:
        logging.critical("Failed to connect to MongoDB. Exiting.")
        return

    logging.info(f"Starting data fetch loop, cycling through {len(OM2M_DATA_SOURCES)} sources every {FETCH_INTERVAL} seconds...")

    while True:
        start_time = time.time()
        logging.info("-" * 30)
        logging.info(f"Starting fetch cycle at {time.ctime()}")

        for source in OM2M_DATA_SOURCES:
            source_name = source['name']
            source_url = source['url']
            logging.info(f"\n--- Fetching from source: {source_name} ---")

            # Fetch data from the current source URL
            raw_data = fetch_om2m_data(source_url)

            # Parse the response to get a list of entries (e.g., CINs)
            entries = extract_entries_from_response(raw_data)

            # Store or update the entries in MongoDB for this source
            store_or_update_entries(collection, entries, source_name)

        end_time = time.time()
        cycle_duration = end_time - start_time
        logging.info("-" * 30)
        logging.info(f"Fetch cycle finished in {cycle_duration:.2f} seconds.")

        # Calculate remaining time to sleep
        time_to_sleep = FETCH_INTERVAL - cycle_duration
        if time_to_sleep > 0:
            logging.info(f"Waiting for {time_to_sleep:.2f} seconds before next cycle...")
            time.sleep(time_to_sleep)
        else:
            logging.warning("Fetch cycle took longer than FETCH_INTERVAL. Proceeding immediately.")


if __name__ == "__main__":
    main()