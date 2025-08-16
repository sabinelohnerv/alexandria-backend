from rest_framework.throttling import SimpleRateThrottle

class LoginIPThrottle(SimpleRateThrottle):
    scope = "login_ip"
    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}

class LoginEmailThrottle(SimpleRateThrottle):
    scope = "login_email"
    def get_cache_key(self, request, view):
        email = (request.data.get("email") or request.data.get("username") or "").strip().lower()
        if not email:
            return None
        return self.cache_format % {"scope": self.scope, "ident": email}
