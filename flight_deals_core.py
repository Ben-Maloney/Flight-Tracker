import os
import csv
import smtplib
import requests
from datetime import datetime
from email.mime.text import MIMEText
from dotenv import load_dotenv

load_dotenv()

SERPAPI_KEY = os.getenv("SERPAPI_KEY")
EMAIL_FROM = os.getenv("EMAIL_FROM")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_TO = os.getenv("EMAIL_TO")

CSV_FILE = "flight_price_history.csv"
MAX_LEGS = 4


def minutes_to_hours_minutes(minutes):
    if minutes is None:
        return ""

    try:
        minutes = int(minutes)
    except (TypeError, ValueError):
        return ""

    hours = minutes // 60
    mins = minutes % 60

    if hours and mins:
        return f"{hours}h {mins}m"
    if hours:
        return f"{hours}h"
    return f"{mins}m"


def parse_flight_time(time_text):
    if not time_text:
        return None

    formats = [
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %I:%M %p",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(time_text, fmt)
        except ValueError:
            pass

    return None


def format_flight_time(time_text):
    dt = parse_flight_time(time_text)

    if not dt:
        return time_text or ""

    formatted = dt.strftime("%b %d, %Y %I:%M %p")
    return formatted.replace(" 0", " ")


def calculate_time_between(arrival_time, next_departure_time):
    arrival_dt = parse_flight_time(arrival_time)
    departure_dt = parse_flight_time(next_departure_time)

    if not arrival_dt or not departure_dt:
        return None

    diff_minutes = int((departure_dt - arrival_dt).total_seconds() / 60)
    return max(diff_minutes, 0)


def calculate_layover_minutes(flight):
    total_duration = flight.get("total_duration")

    if total_duration is None:
        return None

    legs = flight.get("flights", [])
    leg_duration_total = 0

    for leg in legs:
        leg_duration = leg.get("duration")
        if leg_duration:
            leg_duration_total += leg_duration

    return max(total_duration - leg_duration_total, 0)


def calculate_deal_score(price, duration_minutes, stops, total_layover_minutes):
    """
    Deal score from 0–100.
    Higher is better.

    Factors:
    - Lower price = better
    - Shorter travel time = better
    - Fewer stops = better
    - Less layover time = better
    """

    try:
        price = float(price)
        duration_minutes = float(duration_minutes or 0)
        stops = int(stops or 0)
        total_layover_minutes = float(total_layover_minutes or 0)
    except (TypeError, ValueError):
        return 0, "Unknown"

    score = 100

    # Price penalty
    if price > 200:
        score -= min((price - 200) / 10, 35)

    # Duration penalty
    if duration_minutes > 180:
        score -= min((duration_minutes - 180) / 30, 20)

    # Stops penalty
    score -= stops * 10

    # Layover penalty
    if total_layover_minutes > 60:
        score -= min((total_layover_minutes - 60) / 20, 20)

    score = max(0, min(100, round(score)))

    if score >= 85:
        label = "Excellent"
    elif score >= 70:
        label = "Good"
    elif score >= 55:
        label = "Fair"
    else:
        label = "Weak"

    return score, label


def search_flights(
    origin,
    destination,
    depart_date,
    return_date=None,
    stops="0",
    adults=1,
    children=0,
    infants_in_seat=0,
    infants_on_lap=0
):
    params = {
        "engine": "google_flights",
        "api_key": SERPAPI_KEY,
        "departure_id": origin,
        "arrival_id": destination,
        "outbound_date": depart_date,
        "currency": "USD",
        "hl": "en",
        "stops": stops,
        "adults": adults,
        "children": children,
        "infants_in_seat": infants_in_seat,
        "infants_on_lap": infants_on_lap,
        "deep_search": "true",
    }

    if return_date:
        params["return_date"] = return_date
        params["type"] = "1"
    else:
        params["type"] = "2"

    response = requests.get("https://serpapi.com/search", params=params)
    response.raise_for_status()
    return response.json()


def get_booking_options(booking_token):
    if not booking_token:
        return []

    params = {
        "engine": "google_flights",
        "api_key": SERPAPI_KEY,
        "booking_token": booking_token,
        "currency": "USD",
        "hl": "en",
    }

    try:
        response = requests.get("https://serpapi.com/search", params=params)
        response.raise_for_status()
        data = response.json()
        return data.get("booking_options", [])
    except requests.RequestException:
        return []


def get_best_booking_link(booking_token):
    if not booking_token:
        return "", "No booking token returned"

    booking_options = get_booking_options(booking_token)

    if not booking_options:
        return "", "Booking options unavailable"

    first_option = booking_options[0]

    link = (
        first_option.get("link")
        or first_option.get("booking_link")
        or first_option.get("url")
        or ""
    )

    if link:
        return link, "Booking link available"

    return "", "Booking option found, but no direct link"

def flight_matches_airline_filter(flight, allowed_airlines=None, excluded_airlines=None):
    allowed_airlines = allowed_airlines or []
    excluded_airlines = excluded_airlines or []

    legs = flight.get("flights", [])
    airlines = {
        leg.get("airline", "").strip()
        for leg in legs
        if leg.get("airline")
    }

    if excluded_airlines:
        if any(airline in excluded_airlines for airline in airlines):
            return False

    if allowed_airlines:
        return any(airline in allowed_airlines for airline in airlines)

    return True

def extract_flights(
    data,
    origin,
    destination,
    include_booking_links=True,
    adults=1,
    children=0,
    infants_in_seat=0,
    infants_on_lap=0,
    allowed_airlines=None,
    excluded_airlines=None
):
    flights = data.get("best_flights", []) + data.get("other_flights", [])
    results = []

    passenger_count = adults + children + infants_in_seat + infants_on_lap

    for flight in flights:
        if not flight_matches_airline_filter(
            flight,
            allowed_airlines=allowed_airlines,
            excluded_airlines=excluded_airlines
        ):
            continue
        price = flight.get("price")
        duration = flight.get("total_duration")
        layover_minutes = calculate_layover_minutes(flight)
        booking_token = flight.get("booking_token")
        google_flights_url = flight.get("google_flights_url", "")

        if price is None:
            continue

        booking_link = ""
        booking_status = "Booking link not requested"

        if include_booking_links:
            booking_link, booking_status = get_best_booking_link(booking_token)

        if not booking_link and google_flights_url:
            booking_link = google_flights_url
            booking_status = "Google Flights link used as fallback"

        legs = flight.get("flights", [])
        stops_count = max(len(legs) - 1, 0)

        deal_score, deal_rating = calculate_deal_score(
            price=price,
            duration_minutes=duration,
            stops=stops_count,
            total_layover_minutes=layover_minutes
        )

        row = {
            "searched_at": datetime.now().isoformat(timespec="seconds"),
            "origin": origin,
            "destination": destination,
            "passengers": passenger_count,
            "price": price,
            "price_label": f"${price} total for {passenger_count} passenger(s)",
            "deal_score": deal_score,
            "deal_rating": deal_rating,
            "duration_minutes": duration,
            "duration_display": minutes_to_hours_minutes(duration),
            "total_layover_minutes": layover_minutes,
            "total_layover_display": minutes_to_hours_minutes(layover_minutes),
            "number_of_legs": len(legs),
            "stops": stops_count,
            "booking_status": booking_status,
            "booking_link": booking_link,
        }

        route_parts = []
        email_leg_lines = []

        for i, leg in enumerate(legs[:MAX_LEGS], start=1):
            airline = leg.get("airline", "Unknown airline")
            flight_number = leg.get("flight_number", "")
            leg_duration = leg.get("duration")

            dep = leg.get("departure_airport", {})
            arr = leg.get("arrival_airport", {})

            dep_airport = dep.get("id", "")
            dep_time_raw = dep.get("time", "")
            arr_airport = arr.get("id", "")
            arr_time_raw = arr.get("time", "")

            dep_time = format_flight_time(dep_time_raw)
            arr_time = format_flight_time(arr_time_raw)
            leg_duration_display = minutes_to_hours_minutes(leg_duration)

            route_parts.append(f"{dep_airport} → {arr_airport}")

            row[f"leg_{i}_airline"] = airline
            row[f"leg_{i}_flight_number"] = flight_number
            row[f"leg_{i}_from"] = dep_airport
            row[f"leg_{i}_depart_time"] = dep_time
            row[f"leg_{i}_to"] = arr_airport
            row[f"leg_{i}_arrive_time"] = arr_time
            row[f"leg_{i}_flight_time"] = leg_duration_display

            email_leg_lines.append(
                f"Leg {i}: {airline} {flight_number} | "
                f"{dep_airport} departs {dep_time} → "
                f"{arr_airport} arrives {arr_time} | "
                f"Flight time {leg_duration_display}"
            )

            if i < len(legs):
                next_leg = legs[i]
                next_dep = next_leg.get("departure_airport", {})
                next_dep_time_raw = next_dep.get("time", "")

                layover_airport = arr_airport
                layover_time_minutes = calculate_time_between(
                    arr_time_raw,
                    next_dep_time_raw
                )
                layover_time_display = minutes_to_hours_minutes(layover_time_minutes)

                row[f"layover_{i}_airport"] = layover_airport
                row[f"layover_{i}_time"] = layover_time_display

                email_leg_lines.append(
                    f"Layover {i}: {layover_time_display} in {layover_airport}"
                )

        row["route"] = " | ".join(route_parts)
        row["flight_details_email"] = " || ".join(email_leg_lines)

        results.append(row)

    return results


def get_csv_fieldnames():
    fields = [
        "searched_at",
        "origin",
        "destination",
        "search_depart_date",
        "search_return_date",
        "date_flexibility",
        "passengers",
        "price",
        "price_label",
        "deal_score",
        "deal_rating",
        "duration_minutes",
        "duration_display",
        "total_layover_minutes",
        "total_layover_display",
        "number_of_legs",
        "stops",
        "route",
    ]

    for i in range(1, MAX_LEGS + 1):
        fields.extend([
            f"leg_{i}_airline",
            f"leg_{i}_flight_number",
            f"leg_{i}_from",
            f"leg_{i}_depart_time",
            f"leg_{i}_to",
            f"leg_{i}_arrive_time",
            f"leg_{i}_flight_time",
        ])

        if i < MAX_LEGS:
            fields.extend([
                f"layover_{i}_airport",
                f"layover_{i}_time",
            ])

    fields.extend([
        "booking_status",
        "booking_link",
        "flight_details_email",
    ])

    return fields


def save_to_csv(results):
    file_exists = os.path.exists(CSV_FILE)
    fieldnames = get_csv_fieldnames()

    with open(CSV_FILE, "a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
            extrasaction="ignore"
        )

        if not file_exists:
            writer.writeheader()

        writer.writerows(results)


def format_email(results, max_results=10):
    if not results:
        return "No flights matched your criteria."

    results = sorted(
        results,
        key=lambda x: (-(x.get("deal_score", 0)), x.get("price", 999999))
    )[:max_results]

    lines = ["Current flight deals:\n"]

    for i, flight in enumerate(results, start=1):
        lines.append(
            f"{i}. {flight['origin']} → {flight['destination']} | "
            f"{flight.get('price_label', '$' + str(flight['price']))} | "
            f"Deal Score: {flight.get('deal_score', '')}/100 "
            f"({flight.get('deal_rating', '')}) | "
            f"Total travel time: {flight.get('duration_display', '')} | "
            f"Total layover time: {flight.get('total_layover_display', '0m')} | "
            f"{flight['stops']} stop(s)"
        )

        lines.append("   Trip details:")

        for detail in flight.get("flight_details_email", "").split(" || "):
            if detail:
                lines.append(f"   - {detail}")

        lines.append(f"   Booking status: {flight.get('booking_status', '')}")

        if flight.get("booking_link"):
            lines.append(f"   Booking link: {flight['booking_link']}")

        lines.append("")

    return "\n".join(lines)


def send_email(subject, body):
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_FROM, EMAIL_PASSWORD)
        server.send_message(msg)