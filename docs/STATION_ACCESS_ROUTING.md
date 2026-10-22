# Station Access Routing

Choose the source for each train origin in **Configure > Station access profiles**.
Existing mode-only lines remain valid. They select a physical mode for Google
Routes when configured, not an automatic Waze provider.

```text
EXC|Example Central=waze:sensor.example_route
SMP=transit
NTH=walking
```

The first example binds an existing HA Waze Travel Time sensor to trains leaving
the explicitly configured origin. It does not use that sensor for a train leaving
another station, including the return leg. Configure the Waze sensor with the
intended origin and station destination beforehand. The origin can be a fixed
location or a person/device tracker: Journey Guardian reads the resulting
duration and does not rewrite the native Waze route or its tracking behaviour.

Use only the sensor entity ID, not its coordinates, route description or URL.
The sensor must report positive, finite minutes, up to 240, and have reported in
the last 15 minutes. Restored, unavailable, unknown, malformed or stale states are
not live estimates. Fresh identical reports count: an unchanged duration is not
automatically stale. Waze normally polls every five minutes in HA; custom source
polling must remain compatible with the freshness limit.

The optional `|Station name` supplies an exact calendar-origin alias when events
contain names rather than CRS codes. Matching ignores case, extra whitespace and
the map's leading `zzz ` prefix, not station-name differences. Explicit CRS codes
take priority; conflicting identities are not guessed. Duplicate codes/aliases
are rejected. Previously resolved CRS identities can also match legacy profiles
without another Places request. No station alias is inferred from a sensor name.

Journey Guardian reads the existing local sensor during normal calendar reviews.
**Test station route now** and the bounded automatic access checkpoints ask HA to
refresh that selected sensor first. Its native integration controls Waze requests;
Journey Guardian does not add a second Waze client or use rail API quota. If the
selected sensor fails, a `waze_` error explains the fallback and Google is not
contacted for that profile.

The existing **Minimum station access allowance** still applies. For example,
a 20-minute Waze reading with a 30-minute minimum uses 30 minutes. Preparation,
early-warning and station-arrival buffers are not changed by selecting Waze.

Verify **Station access routing** shows `working`, source `waze_sensor`, mode
`driving`, provider duration and applied duration. Check **Prepare at** and
**Leave home at** against the itinerary. A route correction during preparation
can change the alarm window; plan any restart/configuration change accordingly.

The profile contains private station names and entity IDs. Downloadable diagnostics
redact it; timing diagnostics expose only safe provenance, durations and error
categories, not sensor IDs, addresses, coordinates or street names.

## Implementation History

The original live-routing implementation (`f0b32c5`) added Google Routes and a
fixed fallback, not a Waze sensor reader. The initial station-profile change
(`055b2d6`) added CRS-to-mode overrides only. It did not select a routing provider,
and plain-name calendar origins could miss CRS-only profiles before resolution.
v0.2.12 closes that integration/parity omission through the existing field. It
does not claim that a previous published Waze adapter was deleted.

See [HA's Waze documentation](https://www.home-assistant.io/integrations/waze_travel_time/)
for the native sensor and polling configuration.
