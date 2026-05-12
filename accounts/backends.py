from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

class EmailBackend(ModelBackend):
    """
    Authenticates against settings.AUTH_USER_MODEL using email instead of username.
    """
    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        try:
            # username here is actually the email address passed from the form
            user = UserModel.objects.get(email__iexact=username)
        except UserModel.DoesNotExist:
            return None
        except UserModel.MultipleObjectsReturned:
            # Should not happen if clean_email enforces uniqueness, but just in case
            user = UserModel.objects.filter(email__iexact=username).order_by('id').first()

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
