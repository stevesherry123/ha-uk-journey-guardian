"""Pure TransportAPI quota policy."""


def can_reserve_call(
    *,
    calls_used: int,
    daily_limit: int,
    urgent_reserve: int,
    urgent: bool,
) -> bool:
    """Return whether one more call is permitted by the shared allowance."""
    if calls_used >= daily_limit:
        return False
    if urgent:
        return True
    return calls_used < daily_limit - urgent_reserve
