from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin

# Unregister the default User admin
admin.site.unregister(User)

# Create a custom User admin that hides the UUID username in the list
class CustomUserAdmin(UserAdmin):
    list_display = ('display_name', 'email', 'is_staff', 'is_active', 'date_joined')
    
    def display_name(self, obj):
        # Show the first_name (where we saved the typed username), fallback to original username
        return obj.first_name if obj.first_name else obj.username
    display_name.short_description = 'User Name'

admin.site.register(User, CustomUserAdmin)