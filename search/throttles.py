from rest_framework.throttling import ScopedRateThrottle

class BurstRateThrottle(ScopedRateThrottle):
    scope = "search_ask_burst"

class SustainedRateThrottle(ScopedRateThrottle):
    scope = "search_ask_sustained"
