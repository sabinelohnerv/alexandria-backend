from django.contrib import admin
from .models import StaffWhitelist

@admin.action(description="Marcar como ADMIN")
def mark_as_admin(modeladmin, request, queryset):
    queryset.update(role=StaffWhitelist.Role.ADMIN)

@admin.action(description="Marcar como USER")
def mark_as_user(modeladmin, request, queryset):
    queryset.update(role=StaffWhitelist.Role.USER)

@admin.register(StaffWhitelist)
class StaffWhitelistAdmin(admin.ModelAdmin):
    list_display = ("first_name", "last_name", "email", "role", "is_active", "created_by", "created_at")
    list_filter = ("role", "is_active", "created_at")
    search_fields = ("first_name", "last_name", "email")
    readonly_fields = ("created_at", "updated_at")
    actions = [mark_as_admin, mark_as_user]

    def save_model(self, request, obj, form, change):
        if not change and not obj.created_by:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
