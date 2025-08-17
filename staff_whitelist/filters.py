# staff_whitelist/filters.py
import django_filters as df
from .models import StaffWhitelist

class StaffWhitelistFilter(df.FilterSet):
    # ?is_active=true/false/1/0
    is_active = df.BooleanFilter()
    # ?role=admin|user
    role = df.ChoiceFilter(choices=StaffWhitelist.Role.choices)

    class Meta:
        model = StaffWhitelist
        fields = ["is_active", "role"]
