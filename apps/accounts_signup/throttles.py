from rest_framework.throttling import SimpleRateThrottle

class OTPRequestIPThrottle(SimpleRateThrottle):
    scope = "otp_ip"
    def get_cache_key(self, request, view):
        ident = self.get_ident(request) 
        return self.cache_format % {"scope": self.scope, "ident": ident}

class OTPRequestEmailThrottle(SimpleRateThrottle):
    scope = "otp_email"
    def get_cache_key(self, request, view):
        email = (request.data.get("email") or "").strip().lower()
        if not email:
            return None 
        return self.cache_format % {"scope": self.scope, "ident": email}

class OTPResendIPThrottle(SimpleRateThrottle):
    scope = "resend_ip"
    def get_cache_key(self, request, view):
        ident = self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}

class OTPResendEmailThrottle(SimpleRateThrottle):
    scope = "resend_email"
    def get_cache_key(self, request, view):
        email = (request.data.get("email") or "").strip().lower()
        if not email:
            return None
        return self.cache_format % {"scope": self.scope, "ident": email}
    
class StatusIPThrottle(SimpleRateThrottle):
    scope = "status_ip"
    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}

class StatusEmailThrottle(SimpleRateThrottle):
    scope = "status_email"
    def get_cache_key(self, request, view):
        email = (request.data.get("email") or request.query_params.get("email") or "").strip().lower()
        if not email:
            return None
        return self.cache_format % {"scope": self.scope, "ident": email}
