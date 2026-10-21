# Restart recovery

From v0.2.7, ordinary successful reviews save minimal booked intent alongside
the latest matched rail observation. The inner storage schema is versioned;
old observation-only records can still restore evidence for an exact matching
calendar booking, but cannot restore a booking without the calendar.

If the calendar is unavailable after reload/restart, a saved booking can be
shown only after its booked departure and before its original booked end, for
a booking no longer than 24 hours. The integration entry/calendar scope must
match. A future booking cannot start alarms from this outage fallback. Healthy
calendar removal or selection of another booking takes precedence; simulations
neither restore nor overwrite real intent.

Recovered intent is labelled `calendar_recovered`. Data health stays off, the
calendar error remains visible, and automatic departure-board checks pause.
It is not evidence of boarding, departure, arrival or an unchanged booking.
An already registered arrival collector has separate bounded recovery rules.

Earlier rail evidence must match the booking and configured provider, have aware
timestamps and valid types, and be no more than six hours old. It is labelled
retained/historical, not a new current observation. Restoring it cannot itself
produce a fresh rail alert. Restart-safe notification and checkpoint ledgers
continue to prevent repeating claimed work. Invalid evidence is ignored safely.

The local recovery file contains endpoint names/codes and booked times, plus
normalized rail evidence. It excludes raw calendar titles, descriptions,
locations, coordinates and credentials. Protect HA storage and backups; this
data is private, not anonymous. Downloaded diagnostics exclude booked intent.
Logical expiry controls use; an offline HA installation cannot erase expired
data until it runs again. Do not edit or upload private storage files.

The isolated rehearsal reconstructs the integration against HA's test storage;
this is not a fresh OS/HA process reboot or physical notification-delivery test.
Keep independent alarms for real travel. This slice does not implement HA
Repairs, early-termination detection or replacement-train search.
