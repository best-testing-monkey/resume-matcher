"""Static gazetteer data for geo.py (approximate city-centre coordinates)."""

# (name, lat, lon, country ISO-2)
CITIES = [
    # Netherlands
    ("Amsterdam", 52.3676, 4.9041, "NL"), ("Rotterdam", 51.9244, 4.4777, "NL"),
    ("Den Haag", 52.0705, 4.3007, "NL"), ("Utrecht", 52.0907, 5.1214, "NL"),
    ("Eindhoven", 51.4416, 5.4697, "NL"), ("Groningen", 53.2194, 6.5665, "NL"),
    ("Tilburg", 51.5555, 5.0913, "NL"), ("Almere", 52.3508, 5.2647, "NL"),
    ("Breda", 51.5719, 4.7683, "NL"), ("Nijmegen", 51.8126, 5.8372, "NL"),
    ("Apeldoorn", 52.2112, 5.9699, "NL"), ("Haarlem", 52.3874, 4.6462, "NL"),
    ("Arnhem", 51.9851, 5.8987, "NL"), ("Amersfoort", 52.1561, 5.3878, "NL"),
    ("Zaandam", 52.4391, 4.8294, "NL"), ("'s-Hertogenbosch", 51.6978, 5.3037, "NL"),
    ("Hoofddorp", 52.3061, 4.6907, "NL"), ("Maastricht", 50.8514, 5.6910, "NL"),
    ("Leiden", 52.1601, 4.4970, "NL"), ("Dordrecht", 51.8133, 4.6901, "NL"),
    ("Zoetermeer", 52.0575, 4.4931, "NL"), ("Zwolle", 52.5168, 6.0830, "NL"),
    ("Deventer", 52.2661, 6.1552, "NL"), ("Enschede", 52.2215, 6.8937, "NL"),
    ("Delft", 52.0116, 4.3571, "NL"), ("Alphen aan den Rijn", 52.1292, 4.6578, "NL"),
    ("Leeuwarden", 53.2012, 5.7999, "NL"), ("Alkmaar", 52.6324, 4.7534, "NL"),
    ("Heerlen", 50.8882, 5.9795, "NL"), ("Venlo", 51.3704, 6.1724, "NL"),
    ("Amstelveen", 52.3114, 4.8700, "NL"), ("Hilversum", 52.2292, 5.1669, "NL"),
    ("Hengelo", 52.2658, 6.7930, "NL"), ("Roosendaal", 51.5308, 4.4653, "NL"),
    ("Helmond", 51.4793, 5.6570, "NL"), ("Lelystad", 52.5185, 5.4714, "NL"),
    ("Tiel", 51.8869, 5.4287, "NL"), ("Weert", 51.2517, 5.7066, "NL"),
    ("Ede", 52.0480, 5.6658, "NL"), ("Veenendaal", 52.0283, 5.5583, "NL"),
    ("Gouda", 52.0115, 4.7104, "NL"), ("Nieuwegein", 52.0292, 5.0810, "NL"),
    ("Houten", 52.0285, 5.1685, "NL"), ("Vlissingen", 51.4423, 3.5736, "NL"),
    ("Middelburg", 51.4988, 3.6110, "NL"), ("Emmen", 52.7792, 6.9069, "NL"),
    ("Assen", 52.9925, 6.5649, "NL"), ("Den Helder", 52.9563, 4.7608, "NL"),
    ("Schiphol", 52.3105, 4.7683, "NL"), ("Capelle aan den IJssel", 51.9300, 4.5780, "NL"),
    ("Spijkenisse", 51.8450, 4.3290, "NL"), ("Sittard", 51.0000, 5.8686, "NL"),
    ("Roermond", 51.1942, 5.9870, "NL"), ("Bussum", 52.2733, 5.1647, "NL"),
    ("Woerden", 52.0857, 4.8833, "NL"), ("Harderwijk", 52.3422, 5.6203, "NL"),
    ("Purmerend", 52.5050, 4.9597, "NL"), ("Zeist", 52.0894, 5.2327, "NL"),
    # Belgium
    ("Brussels", 50.8503, 4.3517, "BE"), ("Antwerp", 51.2194, 4.4025, "BE"),
    ("Ghent", 51.0543, 3.7174, "BE"), ("Bruges", 51.2093, 3.2247, "BE"),
    ("Leuven", 50.8798, 4.7005, "BE"), ("Liège", 50.6326, 5.5797, "BE"),
    ("Charleroi", 50.4108, 4.4446, "BE"), ("Mechelen", 51.0259, 4.4776, "BE"),
    ("Hasselt", 50.9307, 5.3325, "BE"), ("Namur", 50.4674, 4.8720, "BE"),
    # Germany
    ("Berlin", 52.5200, 13.4050, "DE"), ("Hamburg", 53.5511, 9.9937, "DE"),
    ("Munich", 48.1351, 11.5820, "DE"), ("Cologne", 50.9375, 6.9603, "DE"),
    ("Frankfurt", 50.1109, 8.6821, "DE"), ("Stuttgart", 48.7758, 9.1829, "DE"),
    ("Düsseldorf", 51.2277, 6.7735, "DE"), ("Dortmund", 51.5136, 7.4653, "DE"),
    ("Essen", 51.4556, 7.0116, "DE"), ("Leipzig", 51.3397, 12.3731, "DE"),
    ("Bremen", 53.0793, 8.8017, "DE"), ("Hanover", 52.3759, 9.7320, "DE"),
    ("Nuremberg", 49.4521, 11.0767, "DE"), ("Dresden", 51.0504, 13.7373, "DE"),
    ("Bonn", 50.7374, 7.0982, "DE"), ("Münster", 51.9607, 7.6261, "DE"),
    ("Aachen", 50.7753, 6.0839, "DE"), ("Karlsruhe", 49.0069, 8.4037, "DE"),
    ("Mannheim", 49.4875, 8.4660, "DE"), ("Osnabrück", 52.2799, 8.0472, "DE"),
    # Luxembourg
    ("Luxembourg", 49.6116, 6.1319, "LU"),
    # France
    ("Paris", 48.8566, 2.3522, "FR"), ("Lille", 50.6292, 3.0573, "FR"),
    ("Lyon", 45.7640, 4.8357, "FR"), ("Marseille", 43.2965, 5.3698, "FR"),
    ("Strasbourg", 48.5734, 7.7521, "FR"), ("Nantes", 47.2184, -1.5536, "FR"),
    ("Toulouse", 43.6047, 1.4442, "FR"),
    # UK
    ("London", 51.5074, -0.1278, "GB"), ("Manchester", 53.4808, -2.2426, "GB"),
    ("Birmingham", 52.4862, -1.8904, "GB"), ("Edinburgh", 55.9533, -3.1883, "GB"),
]

# alias -> canonical city name (alias text is normalised by geo.py)
CITY_ALIASES = {
    "'s-Gravenhage": "Den Haag", "s-Gravenhage": "Den Haag", "The Hague": "Den Haag",
    "Den Bosch": "'s-Hertogenbosch", "Hertogenbosch": "'s-Hertogenbosch",
    "Frankfurt am Main": "Frankfurt", "Frankfurt a.M.": "Frankfurt",
    "München": "Munich", "Köln": "Cologne", "Hannover": "Hanover",
    "Nürnberg": "Nuremberg", "Antwerpen": "Antwerp", "Anvers": "Antwerp",
    "Brussel": "Brussels", "Bruxelles": "Brussels", "Gent": "Ghent",
    "Brugge": "Bruges", "Luik": "Liège", "Liege": "Liège",
    "Luxemburg": "Luxembourg", "Luxembourg City": "Luxembourg",
    "Aken": "Aachen", "Zaanstad": "Zaandam", "Schiphol-Rijk": "Schiphol",
    "Heerhugowaard": "Alkmaar", "Haarlemmermeer": "Hoofddorp",
    "Maastricht-Airport": "Maastricht", "Londen": "London",
    "Parijs": "Paris", "Rijsel": "Lille", "Lyons": "Lyon",
    "Greater London": "London", "Dusseldorf": "Düsseldorf",
}

# Region/country centroids: name -> (lat, lon, country ISO-2)
REGIONS = {
    # Dutch provinces (representative centroid)
    "Noord-Holland": (52.50, 4.85, "NL"), "Zuid-Holland": (52.00, 4.45, "NL"),
    "Utrecht Province": (52.08, 5.15, "NL"), "Flevoland": (52.45, 5.55, "NL"),
    "Gelderland": (52.05, 5.95, "NL"), "Noord-Brabant": (51.55, 5.20, "NL"),
    "Limburg": (51.15, 5.90, "NL"), "Overijssel": (52.45, 6.45, "NL"),
    "Drenthe": (52.85, 6.60, "NL"), "Groningen Province": (53.20, 6.70, "NL"),
    "Friesland": (53.10, 5.85, "NL"), "Fryslan": (53.10, 5.85, "NL"),
    "Zeeland": (51.45, 3.80, "NL"),
    "Randstad": (52.10, 4.60, "NL"),
    # Country centroids
    "Netherlands": (52.10, 5.30, "NL"), "Nederland": (52.10, 5.30, "NL"),
    "Holland": (52.10, 5.30, "NL"), "The Netherlands": (52.10, 5.30, "NL"),
    "Belgium": (50.65, 4.65, "BE"), "Belgie": (50.65, 4.65, "BE"),
    "Belgique": (50.65, 4.65, "BE"),
    "Germany": (51.20, 10.00, "DE"), "Deutschland": (51.20, 10.00, "DE"),
    "Duitsland": (51.20, 10.00, "DE"),
    "Luxembourg (country)": (49.75, 6.10, "LU"),
    "France": (46.80, 2.50, "FR"), "Frankrijk": (46.80, 2.50, "FR"),
    "United Kingdom": (53.00, -1.50, "GB"), "UK": (53.00, -1.50, "GB"),
    "England": (52.80, -1.50, "GB"), "Great Britain": (53.00, -1.50, "GB"),
    "Scotland": (56.80, -4.20, "GB"), "Verenigd Koninkrijk": (53.00, -1.50, "GB"),
}

# Known places outside the neighbouring countries -> "too far".
FAR_PLACES = [
    "United States", "USA", "US", "United States of America", "Canada", "Mexico",
    "Brazil", "Argentina", "India", "China", "Japan", "Singapore", "Australia",
    "Ukraine", "Russia", "Spain", "Portugal", "Italy", "Poland", "Romania",
    "Bulgaria", "Greece", "Turkey", "Sweden", "Norway", "Finland", "Denmark",
    "Ireland", "Switzerland", "Austria", "Czech Republic", "Czechia", "Hungary",
    "Israel", "United Arab Emirates", "UAE", "Dubai", "South Africa", "Egypt",
    "Nigeria", "Kenya", "Pakistan", "Philippines", "Vietnam", "Indonesia",
    "Madrid", "Barcelona", "Lisbon", "Rome", "Milan", "Warsaw", "Krakow",
    "Prague", "Vienna", "Zurich", "Geneva", "Dublin", "Stockholm", "Copenhagen",
    "Oslo", "Helsinki", "Budapest", "Bucharest", "Athens", "Istanbul", "Kyiv",
    "New York", "San Francisco", "Los Angeles", "Chicago", "Boston", "Seattle",
    "Austin", "Toronto", "Sydney", "Tokyo", "Bangalore", "Bengaluru",
    "Hyderabad", "Mumbai", "Tel Aviv", "Cairo", "Lagos", "Nairobi",
    "Europe", "EMEA", "Worldwide", "Global", "Asia", "North America",
    "Latin America", "Africa",
]
