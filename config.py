from configurations import get_default_configuration


DEFAULT_CONFIGURATION = get_default_configuration()

PLATFORM = DEFAULT_CONFIGURATION.platform
COUNTRY = DEFAULT_CONFIGURATION.country
CITY = DEFAULT_CONFIGURATION.city
RESTAURANT = DEFAULT_CONFIGURATION.restaurant
LOCATION = DEFAULT_CONFIGURATION.location
RESTAURANT_URL = DEFAULT_CONFIGURATION.url
ITEMS = list(DEFAULT_CONFIGURATION.items)

# Directory for JSON backup files (created automatically if missing)
OUTPUT_DIR = "output"
