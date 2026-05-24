import math
import os
import streamlit as st
import pandas as pd
import folium
from datetime import timedelta
from streamlit_folium import st_folium

from flight_deals_core import (
    MAX_LEGS,
    search_flights,
    extract_flights,
    save_to_csv,
    format_email,
    send_email,
)

AIRPORTS_CSV = "airports.csv"
PRICE_HISTORY_CSV = "flight_price_history.csv"


@st.cache_data
def load_airports():
    airports = pd.read_csv(AIRPORTS_CSV)

    airports.columns = (
        airports.columns
        .str.strip()
        .str.lower()
        .str.replace(" ", "_")
    )

    required_columns = [
        "iata",
        "airport_name",
        "city",
        "state",
        "country",
        "lat",
        "lon",
    ]

    missing_columns = [
        col for col in required_columns
        if col not in airports.columns
    ]

    if missing_columns:
        st.error(f"airports.csv is missing columns: {missing_columns}")
        st.write("Columns found:", list(airports.columns))
        st.stop()

    airports["iata"] = airports["iata"].astype(str).str.upper().str.strip()
    airports["airport_name"] = airports["airport_name"].astype(str).str.strip()
    airports["city"] = airports["city"].astype(str).str.strip()
    airports["state"] = airports["state"].astype(str).str.strip()
    airports["lat"] = pd.to_numeric(airports["lat"], errors="coerce")
    airports["lon"] = pd.to_numeric(airports["lon"], errors="coerce")

    airports = airports.dropna(subset=["lat", "lon"])

    airports["display"] = (
        airports["city"] + ", "
        + airports["state"] + " - "
        + airports["airport_name"] + " ("
        + airports["iata"] + ")"
    )

    return airports


def load_price_history(csv_file=PRICE_HISTORY_CSV):
    if not os.path.exists(csv_file):
        return None

    try:
        history = pd.read_csv(
            csv_file,
            on_bad_lines="skip",
            engine="python"
        )
    except Exception as e:
        st.warning(f"Could not read price history CSV: {e}")
        return None

    if history.empty:
        return None

    required_columns = ["searched_at", "origin", "destination", "price"]

    missing_columns = [
        col for col in required_columns
        if col not in history.columns
    ]

    if missing_columns:
        st.warning(f"Price history file is missing columns: {missing_columns}")
        return None

    history["searched_at"] = pd.to_datetime(
        history["searched_at"],
        errors="coerce"
    )

    history["price"] = pd.to_numeric(
        history["price"],
        errors="coerce"
    )

    history = history.dropna(
        subset=["searched_at", "origin", "destination", "price"]
    )

    return history


def filter_new_best_deals(current_df, history_df):
    if history_df is None or history_df.empty:
        return current_df

    best_historical = (
        history_df
        .groupby(["origin", "destination"], as_index=False)["price"]
        .min()
        .rename(columns={"price": "historical_low_price"})
    )

    comparison = current_df.merge(
        best_historical,
        on=["origin", "destination"],
        how="left"
    )

    better_deals = comparison[
        comparison["historical_low_price"].isna()
        | (comparison["price"] < comparison["historical_low_price"])
    ]

    return better_deals

def generate_flexible_date_pairs(depart_date, return_date=None, flex_days=0):
    depart_dates = [
        depart_date + timedelta(days=offset)
        for offset in range(-flex_days, flex_days + 1)
    ]

    if return_date is None:
        return [
            (depart, None)
            for depart in depart_dates
        ]

    return_dates = [
        return_date + timedelta(days=offset)
        for offset in range(-flex_days, flex_days + 1)
    ]

    date_pairs = []

    for depart in depart_dates:
        for ret in return_dates:
            if ret > depart:
                date_pairs.append((depart, ret))

    return date_pairs

def get_iata_from_display(airports, display_value):
    match = airports.loc[
        airports["display"] == display_value,
        "iata"
    ]

    if match.empty:
        return ""

    return match.iloc[0]


def get_default_airport_display(airports, iata_code):
    match = airports.loc[
        airports["iata"] == iata_code,
        "display"
    ]

    if match.empty:
        return airports["display"].iloc[0]

    return match.iloc[0]


def make_curved_route_points(
    lat1,
    lon1,
    lat2,
    lon2,
    points=40,
    curve_strength=-0.25
):
    route = []

    mid_lat = (lat1 + lat2) / 2
    mid_lon = (lon1 + lon2) / 2

    dx = lon2 - lon1
    dy = lat2 - lat1

    distance = math.sqrt(dx ** 2 + dy ** 2)

    if distance == 0:
        return [[lat1, lon1], [lat2, lon2]]

    offset_lat = -dx * curve_strength
    offset_lon = dy * curve_strength

    control_lat = mid_lat + offset_lat
    control_lon = mid_lon + offset_lon

    for i in range(points + 1):
        t = i / points

        lat = (
            (1 - t) ** 2 * lat1
            + 2 * (1 - t) * t * control_lat
            + t ** 2 * lat2
        )

        lon = (
            (1 - t) ** 2 * lon1
            + 2 * (1 - t) * t * control_lon
            + t ** 2 * lon2
        )

        route.append([lat, lon])

    return route


def build_clickable_airport_map(airports, origin_iata, destination_iatas):
    m = folium.Map(
        location=[39.5, -98.35],
        zoom_start=4,
        tiles="OpenStreetMap",
    )

    origin_row = airports.loc[airports["iata"] == origin_iata]

    if not origin_row.empty:
        origin_lat = origin_row.iloc[0]["lat"]
        origin_lon = origin_row.iloc[0]["lon"]

        for destination_iata in destination_iatas:
            destination_row = airports.loc[
                airports["iata"] == destination_iata
            ]

            if destination_row.empty:
                continue

            dest_lat = destination_row.iloc[0]["lat"]
            dest_lon = destination_row.iloc[0]["lon"]

            curved_points = make_curved_route_points(
                origin_lat,
                origin_lon,
                dest_lat,
                dest_lon,
                curve_strength=-0.25,
            )

            folium.PolyLine(
                locations=curved_points,
                color="blue",
                weight=2,
                opacity=0.75,
                dash_array="8,8",
                tooltip=f"{origin_iata} → {destination_iata}",
            ).add_to(m)

    for _, airport in airports.iterrows():
        iata = airport["iata"]

        if iata == origin_iata:
            color = "green"
            radius = 9
        elif iata in destination_iatas:
            color = "blue"
            radius = 8
        else:
            color = "gray"
            radius = 5

        popup_text = (
            f"{airport['city']}, {airport['state']}<br>"
            f"{airport['airport_name']}<br>"
            f"<b>{iata}</b>"
        )

        folium.CircleMarker(
            location=[airport["lat"], airport["lon"]],
            radius=radius,
            popup=popup_text,
            tooltip=iata,
            color=color,
            fill=True,
            fill_opacity=0.8,
        ).add_to(m)

    return m


def build_selected_flight_map(airports, selected_row):
    m = folium.Map(
        location=[39.5, -98.35],
        zoom_start=4,
        tiles="OpenStreetMap",
    )

    leg_airports = []

    for i in range(1, MAX_LEGS + 1):
        from_col = f"leg_{i}_from"
        to_col = f"leg_{i}_to"

        if from_col in selected_row.index and to_col in selected_row.index:
            from_iata = selected_row.get(from_col)
            to_iata = selected_row.get(to_col)

            if pd.notna(from_iata) and pd.notna(to_iata):
                leg_airports.append((from_iata, to_iata))

    map_points = []

    for leg_number, (from_iata, to_iata) in enumerate(leg_airports, start=1):
        from_row = airports.loc[airports["iata"] == from_iata]
        to_row = airports.loc[airports["iata"] == to_iata]

        if from_row.empty or to_row.empty:
            continue

        from_lat = from_row.iloc[0]["lat"]
        from_lon = from_row.iloc[0]["lon"]
        to_lat = to_row.iloc[0]["lat"]
        to_lon = to_row.iloc[0]["lon"]

        map_points.extend([
            [from_lat, from_lon],
            [to_lat, to_lon],
        ])

        curved_points = make_curved_route_points(
            from_lat,
            from_lon,
            to_lat,
            to_lon,
            curve_strength=-0.25,
        )

        folium.PolyLine(
            locations=curved_points,
            color="orange",
            weight=4,
            opacity=0.9,
            dash_array="8,8",
            tooltip=f"Leg {leg_number}: {from_iata} → {to_iata}",
        ).add_to(m)

        for airport_iata in [from_iata, to_iata]:
            airport_row = airports.loc[airports["iata"] == airport_iata]

            if airport_row.empty:
                continue

            airport = airport_row.iloc[0]

            folium.CircleMarker(
                location=[airport["lat"], airport["lon"]],
                radius=9,
                popup=(
                    f"{airport['city']}, {airport['state']}<br>"
                    f"{airport['airport_name']}<br>"
                    f"<b>{airport_iata}</b>"
                ),
                tooltip=airport_iata,
                color="orange",
                fill=True,
                fill_opacity=0.9,
            ).add_to(m)

    if map_points:
        m.fit_bounds(map_points)

    return m

def get_deal_color(score):
    if score >= 85:
        return "green"
    elif score >= 70:
        return "blue"
    elif score >= 55:
        return "orange"
    return "red"


def build_deal_results_map(airports, df):
    m = folium.Map(
        location=[39.5, -98.35],
        zoom_start=4,
        tiles="OpenStreetMap",
    )

    best_by_destination = (
        df.sort_values(["deal_score", "price"], ascending=[False, True])
        .groupby("destination", as_index=False)
        .first()
    )

    for _, row in best_by_destination.iterrows():
        destination = row["destination"]

        airport_row = airports.loc[airports["iata"] == destination]

        if airport_row.empty:
            continue

        airport = airport_row.iloc[0]
        color = get_deal_color(row.get("deal_score", 0))

        popup_text = (
            f"<b>{destination}</b><br>"
            f"{airport['city']}, {airport['state']}<br>"
            f"{airport['airport_name']}<br>"
            f"Price: {row.get('price_label', '')}<br>"
            f"Deal Score: {row.get('deal_score', '')}/100 "
            f"({row.get('deal_rating', '')})<br>"
            f"Travel Time: {row.get('duration_display', '')}<br>"
            f"Stops: {row.get('stops', '')}"
        )

        folium.CircleMarker(
            location=[airport["lat"], airport["lon"]],
            radius=10,
            popup=popup_text,
            tooltip=f"{destination}: {row.get('deal_score', '')}/100",
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.85,
        ).add_to(m)

    return m

st.set_page_config(
    page_title="Flight Deal Tracker",
    page_icon="✈️",
    layout="wide",
)

st.title("✈️ Flight Deal Tracker")
st.caption(
    "Search flights, save price history to CSV, "
    "and email yourself current deals."
)

airports = load_airports()
airport_options = airports["display"].tolist()

if "origin_iata" not in st.session_state:
    st.session_state.origin_iata = "PDX"

if "destination_iatas" not in st.session_state:
    st.session_state.destination_iatas = ["LAX", "SFO", "JFK"]

if "flight_results_df" not in st.session_state:
    st.session_state.flight_results_df = None

if "results_saved_to_csv" not in st.session_state:
    st.session_state.results_saved_to_csv = False

if "email_sent_for_current_results" not in st.session_state:
    st.session_state.email_sent_for_current_results = False


with st.sidebar:
    st.header("Flight Search")

    map_click_action = st.radio(
        "When I click an airport on the map:",
        [
            "Add as destination",
            "Set as origin",
        ],
    )

    origin_display = st.selectbox(
        "Flying from",
        options=airport_options,
        index=airport_options.index(
            get_default_airport_display(
                airports,
                st.session_state.origin_iata,
            )
        ),
        help="Start typing a city, airport, or airport code.",
    )

    origin = get_iata_from_display(
        airports,
        origin_display,
    )

    st.session_state.origin_iata = origin

    explore_anywhere = st.checkbox(
        "Explore anywhere from origin",
        value=False,
        help=(
            "Search many destinations from your selected origin. "
            "This can use a lot of SerpApi credits."
        ),
    )

    max_explore_destinations = st.number_input(
        "Max destinations to search",
        min_value=1,
        max_value=min(150, len(airports) - 1),
        value=25,
        step=5,
        disabled=not explore_anywhere,
    )

    if explore_anywhere:
        destinations = (
            airports.loc[airports["iata"] != origin, "iata"]
            .head(max_explore_destinations)
            .tolist()
        )

        st.session_state.destination_iatas = destinations

        st.info(
            f"Explore Anywhere enabled: searching "
            f"{len(destinations)} destinations from {origin}."
        )

    else:
        default_destinations = [
            get_default_airport_display(airports, iata)
            for iata in st.session_state.destination_iatas
            if iata in airports["iata"].values
        ]

        destination_displays = st.multiselect(
            "Flying to",
            options=airport_options,
            default=default_destinations,
            help=(
                "Start typing a city, airport, or airport code. "
                "Example: Chicago shows ORD and MDW."
            ),
        )

        destinations = [
            get_iata_from_display(airports, display)
            for display in destination_displays
        ]

        st.session_state.destination_iatas = destinations

        if st.button("Clear destinations"):
            st.session_state.destination_iatas = []
            st.rerun()

    st.header("Travel Dates")

    round_trip = st.checkbox(
        "Round trip",
        value=True,
    )

    date_col1, date_col2 = st.columns(2)

    with date_col1:
        depart_date = st.date_input("Departure date")

    with date_col2:
        return_date = None

        if round_trip:
            return_date = st.date_input("Return date")

    flex_label = st.selectbox(
        "Date flexibility",
        [
            "Exact dates",
            "±1 day",
            "±3 days",
        ]
    )

    flex_days_map = {
        "Exact dates": 0,
        "±1 day": 1,
        "±3 days": 3,
    }

    flex_days = flex_days_map[flex_label]

    max_price = st.number_input(
        "Max total price for email alert",
        min_value=0,
        value=500,
        step=25,
        help="This is the total price for all selected passengers.",
    )

    stops_label = st.selectbox(
        "Layover preference",
        [
            "Any number of stops",
            "Nonstop only",
            "1 stop or fewer",
            "2 stops or fewer",
        ],
    )

    stops_map = {
        "Any number of stops": "0",
        "Nonstop only": "1",
        "1 stop or fewer": "2",
        "2 stops or fewer": "3",
    }

    stops = stops_map[stops_label]

    st.header("Airline Filters")

    airline_filter_mode = st.radio(
        "Airline filter mode",
        [
            "No airline filter",
            "Only selected airlines",
            "Exclude selected airlines"
        ]
    )

    common_airlines = [
        "Alaska",
        "American",
        "Delta",
        "United",
        "Southwest",
        "JetBlue",
        "Frontier",
        "Spirit",
        "Hawaiian",
        "Sun Country"
    ]

    selected_airlines = st.multiselect(
        "Select airlines",
        options=common_airlines,
        default=[]
    )

    allowed_airlines = None
    excluded_airlines = None

    if airline_filter_mode == "Only selected airlines":
        allowed_airlines = selected_airlines

    elif airline_filter_mode == "Exclude selected airlines":
        excluded_airlines = selected_airlines

    st.header("Passengers")

    adults = st.number_input(
        "Adults",
        min_value=1,
        value=1,
        step=1,
    )

    children = st.number_input(
        "Children",
        min_value=0,
        value=0,
        step=1,
    )

    infants_in_seat = st.number_input(
        "Infants in seat",
        min_value=0,
        value=0,
        step=1,
    )

    infants_on_lap = st.number_input(
        "Infants on lap",
        min_value=0,
        value=0,
        step=1,
    )

    passenger_count = (
        adults
        + children
        + infants_in_seat
        + infants_on_lap
    )

    st.info(
        f"Prices shown are total prices for "
        f"{passenger_count} passenger(s)."
    )

    st.header("Output Options")

    include_booking_links = st.checkbox(
        "Try to include booking links",
        value=True,
        help=(
            "Booking links require an extra lookup "
            "and may not be available for every result."
        ),
    )

    email_results = st.checkbox(
        "Email new best deals only",
        value=True,
    )

    save_history = st.checkbox(
        "Save results to CSV history",
        value=True,
    )


st.subheader("Airport Selector Map")
st.caption(
    "Green = origin. Blue = selected destinations. "
    "Curved dotted lines show selected routes. "
    "Click an airport to either add it as a destination or set it as your origin."
)

airport_map = build_clickable_airport_map(
    airports=airports,
    origin_iata=origin,
    destination_iatas=destinations,
)

map_data = st_folium(
    airport_map,
    width=1100,
    height=500,
)

clicked_iata = map_data.get("last_object_clicked_tooltip")

if clicked_iata:
    clicked_iata = clicked_iata.upper()

    if clicked_iata in airports["iata"].values:
        if map_click_action == "Set as origin":
            st.session_state.origin_iata = clicked_iata
            st.rerun()

        elif map_click_action == "Add as destination":
            if not explore_anywhere:
                if clicked_iata not in st.session_state.destination_iatas:
                    st.session_state.destination_iatas.append(clicked_iata)
                    st.rerun()
            else:
                st.warning(
                    "Map destination clicks are disabled while Explore Anywhere is on."
                )


search_button = st.button(
    "Search Flights",
    type="primary",
)

if search_button:

    st.session_state.results_saved_to_csv = False
    st.session_state.email_sent_for_current_results = False

    if not origin or not destinations:
        st.error(
            "Please enter an origin and at least one destination."
        )
        st.stop()

    all_results = []

    date_pairs = generate_flexible_date_pairs(
        depart_date=depart_date,
        return_date=return_date if round_trip else None,
        flex_days=flex_days
    )

    total_searches = len(destinations) * len(date_pairs)

    progress_bar = st.progress(0)
    status_text = st.empty()

    search_counter = 0

    with st.spinner("Searching flights..."):

        for destination in destinations:

            for search_depart_date, search_return_date in date_pairs:

                search_counter += 1

                status_text.write(
                    f"Searching {origin} → {destination} | "
                    f"{search_depart_date}"
                    f"{' to ' + str(search_return_date) if search_return_date else ''} "
                    f"({search_counter} of {total_searches})..."
                )

                try:

                    data = search_flights(
                        origin=origin,
                        destination=destination,
                        depart_date=str(search_depart_date),
                        return_date=(
                            str(search_return_date)
                            if search_return_date
                            else None
                        ),
                        stops=stops,
                        adults=adults,
                        children=children,
                        infants_in_seat=infants_in_seat,
                        infants_on_lap=infants_on_lap,
                    )

                    results = extract_flights(
                        data=data,
                        origin=origin,
                        destination=destination,
                        include_booking_links=include_booking_links,
                        adults=adults,
                        children=children,
                        infants_in_seat=infants_in_seat,
                        infants_on_lap=infants_on_lap,
                        allowed_airlines=allowed_airlines,
                        excluded_airlines=excluded_airlines,
                    )

                    for result in results:

                        result["search_depart_date"] = str(
                            search_depart_date
                        )

                        result["search_return_date"] = (
                            str(search_return_date)
                            if search_return_date
                            else ""
                        )

                        result["date_flexibility"] = flex_label

                    all_results.extend(results)

                except Exception as e:

                    st.error(
                        f"Search failed for "
                        f"{origin} → {destination} "
                        f"on {search_depart_date}: {e}"
                    )

                progress_bar.progress(
                    search_counter / total_searches
                )

    status_text.empty()
    progress_bar.empty()

    if not all_results:
        st.warning("No flights found.")
        st.stop()

    df = pd.DataFrame(all_results)

    df = df.sort_values(
        ["deal_score", "price"],
        ascending=[False, True]
    )

    st.session_state.flight_results_df = df


if st.session_state.flight_results_df is not None:
    df = st.session_state.flight_results_df
    filtered_df = df[df["price"] <= max_price]

    history_df_before_save = load_price_history()

    if email_results and not st.session_state.email_sent_for_current_results:
        better_deals_df = filter_new_best_deals(
            current_df=filtered_df,
            history_df=history_df_before_save
        )

        if not better_deals_df.empty:
            body = format_email(
                better_deals_df.to_dict("records")
            )

            send_email(
                subject=f"New Best Flight Deals from {origin}",
                body=body,
            )

            st.success(
                f"Email sent for {len(better_deals_df)} new best deal(s)."
            )
        else:
            st.info("No new best deals found, so no email was sent.")

        st.session_state.email_sent_for_current_results = True

    if save_history and not st.session_state.results_saved_to_csv:
        save_to_csv(df.to_dict("records"))
        st.session_state.results_saved_to_csv = True

    st.success(
        f"Found {len(df)} flight options."
    )

    st.info(
        f"All displayed prices are total prices "
        f"for {passenger_count} passenger(s)."
    )

    metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)

    with metric_col1:
        st.metric(
            "Lowest Total Price",
            f"${df['price'].min()}",
        )

    with metric_col2:
        st.metric(
            "Best Deal Score",
            f"{df['deal_score'].max()}/100",
        )

    with metric_col3:
        st.metric(
            "Matching Alert Price",
            len(filtered_df),
        )

    with metric_col4:
        st.metric(
            "CSV Updated",
            "Yes" if st.session_state.results_saved_to_csv else "No",
        )

    if explore_anywhere:
        st.subheader("Explore Anywhere Summary")

        summary_df = (
            df.sort_values(["deal_score", "price"], ascending=[False, True])
            .groupby("destination", as_index=False)
            .first()
            .sort_values(["deal_score", "price"], ascending=[False, True])
        )

        summary_display = summary_df[[
            "destination",
            "price_label",
            "deal_score",
            "deal_rating",
            "duration_display",
            "total_layover_display",
            "stops",
            "route",
        ]].rename(columns={
            "destination": "Destination",
            "price_label": "Lowest Price",
            "deal_score": "Deal Score",
            "deal_rating": "Deal Rating",
            "duration_display": "Travel Time",
            "total_layover_display": "Layover Time",
            "stops": "Stops",
            "route": "Route",
        })

        st.dataframe(
            summary_display,
            use_container_width=True,
            hide_index=True,
        )

        st.subheader("Deal Map")

        st.caption(
            "Destinations are colored by best deal score: "
            "green = excellent, blue = good, orange = fair, red = weak."
        )

        deal_results_map = build_deal_results_map(
            airports=airports,
            df=df,
        )

        st_folium(
            deal_results_map,
            width=1100,
            height=500,
        )

    display_columns = [
        "searched_at",
        "origin",
        "destination",
        "search_depart_date",
        "search_return_date",
        "date_flexibility",
        "passengers",
        "price_label",
        "price",
        "deal_score",
        "deal_rating",
        "duration_display",
        "total_layover_display",
        "stops",
        "route",
    ]

    for i in range(1, MAX_LEGS + 1):
        display_columns.extend([
            f"leg_{i}_airline",
            f"leg_{i}_flight_number",
            f"leg_{i}_from",
            f"leg_{i}_depart_time",
            f"leg_{i}_to",
            f"leg_{i}_arrive_time",
            f"leg_{i}_flight_time",
        ])

        if i < MAX_LEGS:
            display_columns.extend([
                f"layover_{i}_airport",
                f"layover_{i}_time",
            ])

    display_columns.extend([
        "booking_status",
        "booking_link",
    ])

    display_columns = [
        col for col in display_columns
        if col in df.columns
        and not df[col].isna().all()
    ]

    column_renames = {
        "searched_at": "Searched At",
        "origin": "From",
        "destination": "To",
        "passengers": "Passengers",
        "price_label": "Price",
        "price": "Raw Price",
        "deal_score": "Deal Score",
        "deal_rating": "Deal Rating",
        "duration_display": "Total Travel Time",
        "total_layover_display": "Total Layover Time",
        "stops": "Stops",
        "route": "Route",
        "booking_status": "Booking Status",
        "booking_link": "Booking Link",
        "search_depart_date": "Search Depart Date",
        "search_return_date": "Search Return Date",
        "date_flexibility": "Date Flexibility",
    }

    for i in range(1, MAX_LEGS + 1):
        column_renames.update({
            f"leg_{i}_airline": f"Leg {i} Airline",
            f"leg_{i}_flight_number": f"Leg {i} Flight #",
            f"leg_{i}_from": f"Leg {i} From",
            f"leg_{i}_depart_time": f"Leg {i} Departs",
            f"leg_{i}_to": f"Leg {i} To",
            f"leg_{i}_arrive_time": f"Leg {i} Arrives",
            f"leg_{i}_flight_time": f"Leg {i} Flight Time",
        })

        if i < MAX_LEGS:
            column_renames.update({
                f"layover_{i}_airport": f"Layover {i} Airport",
                f"layover_{i}_time": f"Layover {i} Time",
            })

    df_display = df[display_columns].rename(
        columns=column_renames,
    )

    filtered_display = filtered_df[display_columns].rename(
        columns=column_renames,
    )

    st.subheader("Current Results")

    st.dataframe(
        df_display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Raw Price": st.column_config.NumberColumn(
                "Raw Price",
                format="$%d",
            ),
            "Deal Score": st.column_config.ProgressColumn(
                "Deal Score",
                min_value=0,
                max_value=100,
            ),
            "Booking Link": st.column_config.LinkColumn(
                "Booking Link",
                display_text="Book / View",
            ),
        },
    )

    st.subheader(
        f"Flights at or below ${max_price} total"
    )

    st.dataframe(
        filtered_display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Raw Price": st.column_config.NumberColumn(
                "Raw Price",
                format="$%d",
            ),
            "Deal Score": st.column_config.ProgressColumn(
                "Deal Score",
                min_value=0,
                max_value=100,
            ),
            "Booking Link": st.column_config.LinkColumn(
                "Booking Link",
                display_text="Book / View",
            ),
        },
    )

    st.subheader("Price History")

    history_df = load_price_history()

    if history_df is None:
        st.info("No price history yet. Run searches with CSV history enabled first.")
    else:
        available_routes = (
            history_df["origin"] + " → " + history_df["destination"]
        ).drop_duplicates().sort_values()

        selected_route = st.selectbox(
            "Choose route for price history",
            available_routes,
        )

        route_origin, route_destination = selected_route.split(" → ")

        route_history = history_df[
            (history_df["origin"] == route_origin)
            & (history_df["destination"] == route_destination)
        ].sort_values("searched_at")

        st.line_chart(
            route_history,
            x="searched_at",
            y="price",
        )

        st.metric(
            "Lowest price seen",
            f"${route_history['price'].min():.0f}",
        )

    st.subheader("Selected Flight Path Map")

    flight_options = []

    for idx, row in df.iterrows():
        label = (
            f"{idx}: "
            f"{row['origin']} → {row['destination']} | "
            f"{row['price_label']} | "
            f"Deal {row.get('deal_score', '')}/100 | "
            f"{row['duration_display']} | "
            f"{row['stops']} stop(s)"
        )

        flight_options.append((label, idx))

    selected_label = st.selectbox(
        "Choose a flight to map",
        options=[label for label, idx in flight_options],
    )

    selected_idx = dict(flight_options)[selected_label]
    selected_row = df.loc[selected_idx]

    selected_flight_map = build_selected_flight_map(
        airports=airports,
        selected_row=selected_row,
    )

    st_folium(
        selected_flight_map,
        width=1100,
        height=500,
    )

    st.download_button(
        label="Download current results as CSV",
        data=df.to_csv(index=False),
        file_name="current_flight_results.csv",
        mime="text/csv",
    )