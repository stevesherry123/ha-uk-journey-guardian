# ADR 0006: Calling-point and strict schedule matching

- Status: accepted
- Date: 2026-09-03
- Provenance: first live TransportAPI acceptance check in v0.1.9

## Context

The calendar describes where the traveller leaves the train, while a station
board describes the train's ultimate destination. A valid London Euston to
Chester journey can therefore appear as a Holyhead service. During live
acceptance, destination substring scoring also treated `Chester` as evidence for
a Manchester service and selected a train eleven minutes later. That changed
derived leave-home advice using the wrong service.

## Decision

- Resolve both calendar endpoints to unique CRS station codes through the same
  brokered, quota-controlled station-resolution boundary.
- Include the intended destination CRS code as TransportAPI's `calling_at`
  filter and request calling-point detail on every live timetable request.
- Treat final-destination text only as bounded whole-name evidence. Never match a
  destination merely because its characters occur inside another place name.
- Prefer the calendar schedule as the authoritative service identity anchor.
  Reject a selected service whose scheduled departure differs by more than five
  minutes, even when other evidence appears plausible.
- Classify accepted observations as `exact_schedule` or `near_schedule` and
  publish the signed offset without retaining raw provider payloads.
- On rejection, retain the provider-free calendar journey and conservative
  timing, expose a stable privacy-safe error, and publish no rail observation.

## Consequences

- A train terminating beyond the traveller's destination can be matched safely
  because the provider confirms that it calls at the intended station.
- A first uncached manual check can consume three routine calls: origin Places,
  destination Places, and the filtered timetable. Cached resolutions avoid the
  repeated Places cost during the integration process lifetime.
- Provider omissions or timetable shifts beyond the narrow tolerance fail safe
  instead of moving travel advice to a different service.
- Automatic monitoring remains deferred; this decision only hardens the
  deliberately manual gateway accepted in ADR 0005.
