from typing import Any

from pydantic import BaseModel, ConfigDict


class CollectionConfiguration(BaseModel):
    model_config = ConfigDict(frozen=True)

    platform: str
    country: str
    city: str
    restaurant: str
    url: str | None = None
    location: str | None = None
    items: tuple[str, ...] = ()


_MARKETS: dict[str, dict[str, Any]] = {
    "UAE": {
        "city": "Dubai",
        "restaurants": [
            "McDonald's",
            "KFC",
            "Burger King",
            "Subway",
            "Pizza Hut",
            "Bikanervala",
            "Saravanaa Bhavan",
            "The Cheesecake Factory",
            "Wagamama",
            "Nando's",
            "Laffah",
            "Zaatar w Zeit",
            "Jazeel",
        ],
        "platforms": ["Talabat", "Deliveroo", "Noon Food"],
    },
    "India": {
        "city": "Mumbai",
        "restaurants": ["McDonald's", "KFC", "Burger King", "Subway"],
        "platforms": ["Swiggy", "Zomato", "Ownly"],
    },
    "USA": {
        "city": "New York",
        "restaurants": ["McDonald's", "KFC", "Burger King", "Subway"],
        "platforms": ["DoorDash", "Uber Eats", "Grubhub"],
    },
}

_VERIFIED_CONFIGURATIONS: dict[tuple[str, str, str, str], dict[str, Any]] = {
    ("talabat", "uae", "dubai", "mcdonald's"): {
        "url": (
            "https://www.talabat.com/uae/restaurant/699079/"
            "mcdonalds-media-city?aid=1213"
        ),
        "location": "Dubai Media City",
        "items": (
            "McChicken Medium Meal",
            "Spicy McChicken Medium Meal",
            "Big Mac Medium Meal",
            "Quarter Pounder with Cheese Medium Meal",
            "9 pcs Chicken McNuggets Medium Meal",
            "Cheeseburger Medium Meal",
            "Large Fries",
            "Apple Pie",
        ),
    },
    ("noon food", "uae", "dubai", "mcdonald's"): {
        "url": "https://food.noon.com/uae-en/outlet/MCDNLD5OYL/",
        "location": "Dubai Silicon Oasis",
        "items": (
            "Mcchicken Medium Meal",
            "Spicy Mcchicken Medium Meal",
            "Big Mac Medium Meal",
            "Quarter Pounder With Cheese Medium Meal",
            "9 Pcs Chicken Mcnuggets Medium Meal",
            "Cheeseburger Medium Meal",
            "Large Fries",
            "Apple Pie",
        ),
    },
    ("talabat", "uae", "dubai", "kfc"): {
        "url": "https://www.talabat.com/uae/restaurant/8406/kfc?aid=1277",
        "location": "Dubai Silicon Oasis",
        "items": (
            "Zinger Meal",
            "Twister Meal",
            "Mighty Zinger Meal",
            "Dinner Crispy Strips Meal",
            "22 Pc Mighty Bucket+ Dips",
            "Onion Rings",
            "Spicy Fries",
            "Fries",
        ),
    },
    ("noon food", "uae", "dubai", "kfc"): {
        "url": "https://food.noon.com/uae-en/outlet/KFC2N1Q6LE/",
        "location": "Dubai Silicon Oasis",
        "items": (
            "Zinger Meal",
            "Twister Meal",
            "Mighty Zinger Meal",
            "Dinner Crispy Strips Meal",
            "22 Pc Mighty Bucket+ Dips",
            "Onion Rings",
            "Spicy Fries",
            "Fries",
        ),
    },
    ("talabat", "uae", "dubai", "burger king"): {
        "url": "https://www.talabat.com/uae/restaurant/664005/burger-king-dsodubai-silicon-oasis?aid=1277",
        "location": "Dubai Silicon Oasis",
        "items": (
            "Whopper Meal Medium",
            "Chicken Royale Meal Medium",
            "French Fries Medium",
            "Big King Meal Medium",
            "Chicken Fillet Meal Medium",
            "Chicken Nuggets 9 Pcs Meal Medium",
            "Big King Xl Meal Medium",
            "Whopper Jr Meal Medium",
        ),
    },
    ("noon food", "uae", "dubai", "burger king"): {
        "url": "https://food.noon.com/uae-en/outlet/BRGRKN9RJL/",
        "location": "Discovery Gardens",
        "items": (
            "Whopper Meal Medium",
            "Chicken Royale Meal Medium",
            "French Fries Medium",
            "Big King Meal Medium",
            "Chicken Fillet Meal Medium",
            "Chicken Nuggets 9 Pcs Meal Medium",
            "Big King Xl Meal Medium",
            "Whopper Jr Meal Medium",
        ),
    },
    ("talabat", "uae", "dubai", "subway"): {
        "url": "https://www.talabat.com/uae/restaurant/35208/subway96?aid=1277",
        "location": "Dubai Silicon Oasis",
        "items": (
            "Italian B.M.T 6 Inch Meal",
            "Chicken Teriyaki 6 Inch Meal",
            "Oven Roasted Chicken 6 Inch Meal",
            "Tuna 6 Inch Meal",
            "Steak And Cheese 6 Inch Meal",
            "Peri Peri Chicken 6 Inch Meal",
            "Sub Halloumi 6 Inch Meal",
            "Spicy Mexican 6 inch meal",
        ),
    },
    ("noon food", "uae", "dubai", "subway"): {
        "url": "https://food.noon.com/uae-en/outlet/SBWY5BPXCY/",
        "location": "Discovery Gardens",
        "items": (
            "Italian B.M.T 6 Inch Meal",
            "Chicken Teriyaki 6 Inch Meal",
            "Oven Roasted Chicken 6 Inch Meal",
            "Tuna 6 Inch Meal",
            "Steak And Cheese 6 Inch Meal",
            "Peri Peri Chicken 6 Inch Meal",
            "Sub Halloumi 6 Inch Meal",
            "Spicy Mexican 6 Inch Meal",
        ),
    },
    ("talabat", "uae", "dubai", "bikanervala"): {
        "url": "https://www.talabat.com/uae/restaurant/19980/bikanervala-dubai-international-city?aid=1292",
        "location": "International City",
        "items": (
            "Crispy Samosa",
            "Pyaaz Kachori",
            "Raj Kachori",
            "Mumbai Style Vada Pav",
            "Shahi Paneer meal",
            "Masala Dosa",
            "Plain Dosa",
            "South Indian Thali",
        ),
    },
    ("noon food", "uae", "dubai", "bikanervala"): {
        "url": "https://food.noon.com/uae-en/outlet/BKNRVL2F36/",
        "location": "Discovery Gardens",
        "items": (
            "Crispy Samosa",
            "Pyaaz Kachori",
            "Raj Kachori",
            "Mumbai Style Vada Pav",
            "Shahi Paneer Meal",
            "Masala Dosa",
            "Plain Dosa",
            "South Indian Thali",
        ),
    },
    ("talabat", "uae", "dubai", "saravanaa bhavan"): {
        "url": "https://www.talabat.com/uae/restaurant/601485/saravana-bhavan-al-karama?aid=1250",
        "location": "Al Karama",
        "items": (
            "Masala Dosa",
            "Plain Dosa",
            "Podi Dosa",
            "Mysore Dosa",
            "Ghee Pongal",
            "Onion Dosa",
            "Rava Dosa",
            "Pongal Vadai",
        ),
    },
    ("noon food", "uae", "dubai", "saravanaa bhavan"): {
        "url": "https://food.noon.com/uae-en/outlet/SRVNBHQJ52/",
        "location": "Karama",
        "items": (
            "Masala Dosa",
            "Plain Dosa",
            "Podi Dosa",
            "Mysore Dosa",
            "Ghee Pongal",
            "Onion Dosa",
            "Rava Dosa",
            "Pongal Vadai",
        ),
    },
    ("talabat", "uae", "dubai", "the cheesecake factory"): {
        "url": "https://www.talabat.com/uae/restaurant/34851/the-cheesecake-factory-dubai-festival-city?aid=1263",
        "location": "DIFC",
        "items": (
            "Fettuccine Alfredo With Chicken",
            "Crusted Chicken Romano",
            "Factory Nachos",
            "Chicken Madeira",
            "Chicken Bellagio",
            "Chicken Piccata",
            "Godiva Chocolate Cheesecake",
            "Oreo Dream Extreme Cheesecake",
        ),
    },
    ("talabat", "uae", "dubai", "wagamama"): {
        "url": "https://www.talabat.com/uae/restaurant/689537/wagamama-dubai-hills?aid=8907",
        "location": "Dubai Hills",
        "items": (
            "KATSU CURRY CHICKEN",
            "CHICKEN GYOZA",
            "CHICKEN RAMEN",
            "MINI PAD THAI CHICKEN",
            "TERIYAKI DONBURI CHICKEN",
            "YAKI SOBA CHICKEN PRAWNS",
            "KOREAN BBQ BEEF BAO BUN",
            "BAO PLATTER",
        ),
    },
    ("talabat", "uae", "dubai", "nando's"): {
        "url": "https://www.talabat.com/uae/restaurant/684257/nandos-dubai-silicon-oasis?aid=1277",
        "location": "Dubai Silicon Oasis",
        "items": (
            "1/4 Chicken + 1 Regular Side",
            "Chicken Livers & a Portuguese Roll",
            "1/2 Chicken + 2 Regular Sides",
            "1/2 Chicken + 1 Regular Side",
            "Grilled Chicken Strips & Spicy Rice + 1 Regular Side",
            "Chicken Butterfly + 2 Regular Sides",
            "PERi-Crackle Avo Burger + 1 Regular Side",
            "NEW Saucy 3 Chicken Wings",
        ),
    },
    ("noon food", "uae", "dubai", "nando's"): {
        "url": "https://food.noon.com/uae-en/outlet/NNDSE0R3DU/",
        "location": "Dubai Silicon Oasis",
        "items": (
            "1/4 Chicken + 1 Regular Side",
            "Chicken Livers & a Portuguese Roll",
            "1/2 Chicken + 2 Regular Sides",
            "1/2 Chicken + 1 Regular Side",
            "Grilled Chicken Strips & Spicy Rice + 1 Regular Side",
            "Chicken Butterfly + 2 Regular Sides",
            "PERi-Crackle Avo Burger + 1 Regular Side",
            "NEW Saucy 3 Chicken Wings",
        ),
    },
    ("talabat", "uae", "dubai", "laffah"): {
        "url": "https://www.talabat.com/uae/restaurant/762630/laffah-dso?aid=1277",
        "location": "Dubai Silicon Oasis",
        "items": (
            "Small chicken shawarma SAJ",
            "Grilled Chicken Half",
            "Small Garlic",
            "Big chicken shawarma SAJ",
            "Chicken Arabic Meal SAJ",
            "Slices potato",
            "Mix meal",
            "Value meal",
        ),
    },
    ("noon food", "uae", "dubai", "laffah"): {
        "url": "https://food.noon.com/uae-en/outlet/LFFHI8LCTW/",
        "location": "Dubai Silicon Oasis",
        "items": (
            "Small chicken shawarma SAJ",
            "Grilled Chicken Half",
            "Small Garlic",
            "Big chicken shawarma SAJ",
            "Chicken Arabic Meal SAJ",
            "Slices potato",
            "Mix meal",
            "Value meal",
        ),
    },
    ("talabat", "uae", "dubai", "zaatar w zeit"): {
        "url": "https://www.talabat.com/uae/restaurant/726762/zaatar-w-zeit-by-robots-dso?aid=1277",
        "location": "Dubai Silicon Oasis",
        "items": (
            "Zaatar",
            "Wild Zaatar",
            "Lahmeh Bi Ajine",
            "Kashkawan",
            "Halloumi",
            "Zaatar & Labneh",
            "Zaatar & Cheese",
            "Jebneh",
        ),
    },
    ("noon food", "uae", "dubai", "zaatar w zeit"): {
        "url": "https://food.noon.com/uae-en/outlet/ZTRWZTKHT2/",
        "location": "Dubai Silicon Oasis",
        "items": (
            "Zaatar",
            "Wild Zaatar",
            "Lahmeh Bi Ajine",
            "Kashkawan",
            "Halloumi",
            "Zaatar & Labneh",
            "Zaatar & Cheese",
            "Jebneh",
        ),
    },
    ("talabat", "uae", "dubai", "jazeel"): {
        "url": "https://www.talabat.com/uae/restaurant/622958/jazeel-restaurant-cafe?aid=1277",
        "location": "Dubai Silicon Oasis",
        "items": (
            "Grilled chicken 800g",
            "Boneless Chicken",
            "Fattoush",
            "Muttabal Jazeel",
            "Mix Grill - 1 Kilo",
            "Jazeel Mix Grill - 1 Kilo",
            "Lentil Soup",
            "Vegetable Soup",
        ),
    },
    ("noon food", "uae", "dubai", "jazeel"): {
        "url": "https://food.noon.com/uae-en/outlet/JZLRST1RPF/",
        "location": "Dubai Silicon Oasis",
        "items": (
            "Grilled chicken 800g",
            "Boneless Chicken",
            "Fattoush",
            "Muttabal Jazeel",
            "Mix Grill - 1 Kilo",
            "Jazeel Mix Grill - 1 Kilo",
            "Lentil Soup",
            "Vegetable Soup",
        ),
    },
}


_ADDITIONAL_VERIFIED_CONFIGURATIONS: dict[tuple[str, str, str, str, str], dict[str, Any]] = {
    ("Talabat", "UAE", "Dubai", "McDonald's", "Dubai Silicon Oasis"): {
        "url": "https://www.talabat.com/uae/restaurant/742270/mcdonalds-dso?aid=1277",
        "items": (
            "McChicken Medium Meal",
            "Spicy McChicken Medium Meal",
            "Happy Meal 4pcs Chicken McNuggets with Fries",
            "Happy Meal Chickenburger with Fries",
            "9 pcs Chicken McNuggets",
            "Large Fries",
            "McCrispy Deluxe",
            "McCrispy Deluxe Large Meal",
        ),
    },
    ("Talabat", "UAE", "Dubai", "McDonald's", "Deira"): {
        "url": "https://www.talabat.com/uae/restaurant/759989/mcdonalds-al-ghurair-extension?aid=1277",
        "items": (
            "McChicken Medium Meal",
            "Happy Meal Chickenburger with Fries",
            "Happy Meal 4pcs Chicken McNuggets with Fries",
            "Double Cheeseburger Medium Meal",
            "Big Tasty Medium Meal",
            "Big Tasty Large Meal",
            "McCrispy Deluxe",
            "McCrispy Deluxe Large Meal",
        ),
    },
    ("Noon Food", "UAE", "Dubai", "McDonald's", "Deira"): {
        "url": "https://food.noon.com/uae-en/outlet/MCDNLDB619/",
        "items": (
            "McChicken Medium Meal",
            "Happy Meal Chickenburger with Fries",
            "Happy Meal 4pcs Chicken McNuggets with Fries",
            "Double Cheeseburger Medium Meal",
            "Big Tasty Medium Meal",
            "Big Tasty Large Meal",
            "McCrispy Deluxe",
            "McCrispy Deluxe Large Meal",
        ),
    },
    ("Noon Food", "UAE", "Dubai", "Subway", "Dubai Silicon Oasis"): {
        "url": "https://food.noon.com/uae-en/outlet/SBWYWFS5OX/",
        "items": (
            "Italian B.M.T 6 Inch Meal",
            "Chicken Teriyaki 6 Inch Meal",
            "Oven Roasted Chicken 6 Inch Meal",
            "Tuna 6 Inch Meal",
            "Steak And Cheese 6 Inch Meal",
            "Peri Peri Chicken 6 Inch Meal",
            "Sub Halloumi 6 Inch Meal",
            "Spicy Mexican 6 Inch Meal",
        ),
    },
}


def _key(*values: str) -> tuple[str, ...]:
    return tuple(value.strip().lower() for value in values)


def _build_catalog() -> tuple[CollectionConfiguration, ...]:
    configurations = []
    for country, market in _MARKETS.items():
        for restaurant in market["restaurants"]:
            for platform in market["platforms"]:
                values: dict[str, Any] = {
                    "platform": platform,
                    "country": country,
                    "city": market["city"],
                    "restaurant": restaurant,
                }
                values.update(_VERIFIED_CONFIGURATIONS.get(
                    _key(platform, country, market["city"], restaurant),
                    {},
                ))
                configurations.append(CollectionConfiguration(**values))
    for key, verified in _ADDITIONAL_VERIFIED_CONFIGURATIONS.items():
        platform, country, city, restaurant, location = key
        configurations.append(CollectionConfiguration(
            platform=platform,
            country=country,
            city=city,
            restaurant=restaurant,
            location=location,
            **verified,
        ))
    return tuple(configurations)


CONFIGURATION_CATALOG = _build_catalog()


def get_default_configuration() -> CollectionConfiguration:
    return find_configuration(
        platform="Talabat",
        country="UAE",
        city="Dubai",
        restaurant="McDonald's",
    )


def find_configuration(
    *,
    platform: str,
    country: str,
    city: str,
    restaurant: str,
    location: str | None = None,
) -> CollectionConfiguration:
    target = _key(platform, country, city, restaurant)
    for configuration in CONFIGURATION_CATALOG:
        if _key(
            configuration.platform,
            configuration.country,
            configuration.city,
            configuration.restaurant,
        ) == target and (
            location is None
            or _key(configuration.location or "") == _key(location)
        ):
            return configuration
    raise ValueError(
        "No configuration found for "
        f"{platform}/{country}/{city}/{restaurant}"
        + (f"/{location}" if location else "")
    )


def _collector_available(platform: str) -> bool:
    from collectors import COLLECTORS

    key = platform.strip().lower().replace(" ", "_")
    return key in COLLECTORS


def is_configured(configuration: CollectionConfiguration) -> bool:
    return configuration.url is not None and bool(configuration.items)


def is_executable(configuration: CollectionConfiguration) -> bool:
    return is_configured(configuration) and _collector_available(configuration.platform)


def configuration_status(configuration: CollectionConfiguration) -> str:
    if is_executable(configuration):
        return "executable"
    if is_configured(configuration):
        return "configured"
    return "planned"


def _serialize(configuration: CollectionConfiguration) -> dict[str, Any]:
    return {
        **configuration.model_dump(),
        "items": list(configuration.items),
        "configured": is_configured(configuration),
        "collector_available": _collector_available(configuration.platform),
        "status": configuration_status(configuration),
    }


def list_configurations() -> list[dict[str, Any]]:
    return [_serialize(configuration) for configuration in CONFIGURATION_CATALOG]


def get_executable_configurations() -> list[CollectionConfiguration]:
    return [
        configuration
        for configuration in CONFIGURATION_CATALOG
        if is_executable(configuration)
    ]


def get_configuration(
    *,
    platform: str,
    country: str,
    city: str,
    restaurant: str,
    location: str | None = None,
) -> CollectionConfiguration:
    configuration = find_configuration(
        platform=platform,
        country=country,
        city=city,
        restaurant=restaurant,
        location=location,
    )
    if not is_executable(configuration):
        raise ValueError(
            f"Configuration is {configuration_status(configuration)} and cannot be collected: "
            f"{platform}/{country}/{city}/{restaurant}"
        )
    return configuration