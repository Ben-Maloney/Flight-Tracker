# Flight-Tracker
✈️ Flight Deal Tracker

A live flight search and travel discovery application built with Python and Streamlit.

This project searches live Google Flights data through the SerpApi API, scores deals based on multiple travel factors, tracks historical pricing, visualizes routes on interactive maps, and helps identify whether a flight is a strong purchase opportunity.

🌐 Live Demo

Add your deployed Streamlit URL here:

https://flight-tracker-3gwkf5rvccwvse6xtsuran.streamlit.app/

Features
🔎 Flight Search
Search flights between airports using IATA codes
Supports one-way and round-trip travel
Flexible date searching
Weekend getaway mode
Explore Anywhere mode
💸 Deal Scoring

Flights are automatically scored from 0–100 based on:

Price
Total travel time
Number of stops
Layover duration

Each result includes:

Deal score
Deal rating
Explanation of why the score was assigned

Example:

Cheap fare, nonstop, short trip
📉 Price Drop Tracking

The app compares current search results against historical searches stored in CSV history.

Highlights include:

Price drops since the last search
Historical lows
Average historical pricing
Buy-now recommendations

Example recommendations:

Buy now
Consider buying
Wait
Neutral
🗺 Interactive Maps

Built using Folium.

Features include:

Airport selector map
Route visualization
Deal heat mapping
Selected flight path mapping
Explore Anywhere destination mapping
✈ Airline Filtering

Users can:

Include only selected airlines
Exclude selected airlines
Review summarized airline information for each itinerary
📊 Historical Price Tracking

Search results can be stored locally in CSV format.

Historical tracking supports:

Price trend charts
Historical lows
Route-specific analysis
Buy-now recommendations
Tech Stack
Python
Streamlit
pandas
Folium
Streamlit Folium
SerpApi
GitHub
Streamlit Cloud
Deployment

The application is deployed publicly using:

GitHub
Streamlit Cloud

Environment secrets are securely managed through Streamlit Cloud Secrets.

Portfolio Context

This project was developed as a full-stack data application demonstrating:

API integration
Data transformation
Interactive web app development
Mapping and geospatial visualization
User-focused analytics
Historical trend analysis
Deployment workflows
GitHub version control
Cloud deployment
Notes

This public demo is intended as a portfolio and demonstration application.

To manage API usage and maintain reliability, search limits and feature restrictions may apply.

Future Enhancements

Potential future additions include:

Smart airport groups (NYC, LON, etc.)
Calendar heatmaps
Hotel + flight integration
Mobile card layouts
User-saved searches
Price alert subscriptions
Advanced airline analytics

Benjamin Maloney

Data Analyst II — Portland Fire & Rescue

Focused on analytics, visualization, geospatial analysis, operational intelligence, and public-sector data systems.

LinkedIn: https://www.linkedin.com/in/benjamin-maloney-3bb0812b/
GitHub: https://github.com/Ben-Maloney/Flight-Tracker