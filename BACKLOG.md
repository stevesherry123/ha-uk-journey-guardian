# Development backlog

This backlog deliberately uses generic terminology. Real stations, destinations,
addresses, calendars, people, notification targets, and credentials must remain
inside each user's Home Assistant installation.

## Core journey engine

- editable traveller profiles with preparation and station-arrival buffers
- destination profiles supporting any number of regular destinations
- rail station name and CRS-code resolution without hard-coded personal routes
- lightweight monitoring for every leg of a split journey
- delayed-service checks after scheduled departure when a train has not departed
- provider failure handling, stale-data warnings, and quota-safe fallbacks

## Routing and notifications

- Google Routes estimates for walking, cycling, and road station-access legs
- configurable notification, announcement, and wearable adapters
- enhanced manual review using the same traveller and destination decision tree
- optional UK local-transit comparison for suitable destination profiles

## Distribution

- publish alpha releases for installation as a HACS custom repository
- create non-identifying brand assets
- add and pass HACS Action and Hassfest validation
- document supported Home Assistant versions and upgrade migrations
- submit to the HACS default catalogue after the integration is stable
