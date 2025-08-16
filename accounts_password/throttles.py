from rest_framework.throttling import SimpleRateThrottle

class PwdResetIPThrottle(SimpleRateThrottle):
    scope = "pwd_reset_ip"
    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}

class PwdResetEmailThrottle(SimpleRateThrottle):
    scope = "pwd_reset_email"
    def get_cache_key(self, request, view):
        email = (request.data.get("email") or "").strip().lower()
        if not email:
            return None
        return self.cache_format % {"scope": self.scope, "ident": email}

class PwdResendIPThrottle(SimpleRateThrottle):
    scope = "pwd_resend_ip"
    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}

class PwdResendEmailThrottle(SimpleRateThrottle):
    scope = "pwd_resend_email"
    def get_cache_key(self, request, view):
        email = (request.data.get("email") or "").strip().lower()
        if not email:
            return None
        return self.cache_format % {"scope": self.scope, "ident": email}

class PwdStatusIPThrottle(SimpleRateThrottle):
    scope = "pwd_status_ip"
    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}

class PwdStatusEmailThrottle(SimpleRateThrottle):
    scope = "pwd_status_email"
    def get_cache_key(self, request, view):
        email = (request.data.get("email") or request.query_params.get("email") or "").strip().lower()
        if not email:
            return None
        return self.cache_format % {"scope": self.scope, "ident": email}
