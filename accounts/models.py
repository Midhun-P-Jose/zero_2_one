from django.db import models
from django.contrib.auth.models import User

# Monkey-patch the default User model's string representation
# so it displays the user's chosen name (saved in first_name) instead of the UUID hash.
def user_str(self):
    if self.first_name:
        return f"{self.first_name} ({self.email})" if self.email else self.first_name
    return self.email if self.email else self.username

User.add_to_class('__str__', user_str)
