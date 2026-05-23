import pandas as pd

SOURCE_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"

TOP_AIRPORTS = [
    "ATL", "DFW", "DEN", "ORD", "LAX", "JFK", "LAS", "MCO", "MIA", "CLT",
    "SEA", "PHX", "EWR", "SFO", "IAH", "BOS", "FLL", "MSP", "LGA", "DTW",
    "PHL", "SLC", "BWI", "DCA", "SAN", "IAD", "TPA", "BNA", "AUS", "MDW",
    "DAL", "HOU", "STL", "RDU", "SMF", "MSY", "CLE", "OAK", "SJC", "SAT",
    "SNA", "PDX", "MCI", "IND", "PIT", "CMH", "JAX", "RSW", "CVG", "BDL",
    "BUR", "ONT", "PBI", "CHS", "OMA", "BUF", "ABQ", "TUL", "OKC", "BOI",
    "TUS", "ELP", "GEG", "RNO", "LGB", "MEM", "RIC", "ORF", "SDF", "BHM",
    "GRR", "DSM", "FAT", "XNA", "LIT", "ICT", "COS", "SYR", "ALB", "ROC",
    "PWM", "MHT", "SAV", "GSP", "AVL", "MYR", "PNS", "VPS", "MOB", "JAN",
    "BTR", "LFT", "SHV", "HRL", "CRP", "AMA", "LBB", "MAF", "FAR", "BIS",
    "FSD", "CID", "MLI", "MSN", "MKE", "GRB", "ATW", "TYS", "CHA", "HSV",
    "LEX", "DAY", "CAK", "ERI", "ABE", "AVP", "BTV", "ISP", "HPN", "SWF",
    "ECP", "SRQ", "PIE", "GSO", "ILM", "CAE", "ROA", "CHO", "FNT", "LAN",
    "AZO", "TVC", "BZN", "JAC", "FCA", "MSO", "GJT", "EGE", "ASE", "HDN",
    "SBA", "PSP", "BFL", "SBP", "MRY", "ACV", "EUG", "RDM", "PSC", "EAT",
]

df = pd.read_csv(SOURCE_URL)

df = df[
    (df["iso_country"] == "US") &
    (df["iata_code"].notna()) &
    (df["scheduled_service"] == "yes") &
    (df["type"].isin(["large_airport", "medium_airport"]))
].copy()

df["state"] = df["iso_region"].str.replace("US-", "", regex=False)

df = df.rename(columns={
    "iata_code": "iata",
    "name": "airport_name",
    "municipality": "city",
    "latitude_deg": "lat",
    "longitude_deg": "lon",
})

df = df[[
    "iata",
    "airport_name",
    "city",
    "state",
    "iso_country",
    "lat",
    "lon"
]].rename(columns={
    "iso_country": "country"
})

df["iata"] = df["iata"].str.upper().str.strip()

df = df[df["iata"].isin(TOP_AIRPORTS)].copy()

df["sort_order"] = df["iata"].apply(lambda x: TOP_AIRPORTS.index(x))
df = df.sort_values("sort_order").drop(columns=["sort_order"])

df.to_csv("airports.csv", index=False)

print(f"Created airports.csv with {len(df)} airports.")
print("Missing from source data:")

missing = [iata for iata in TOP_AIRPORTS if iata not in df["iata"].values]

if missing:
    print(missing)
else:
    print("None")