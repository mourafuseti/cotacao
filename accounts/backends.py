from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

from .validators import normalize_cnpj


class CNPJOrEmailBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        identifier = username or kwargs.get("email") or kwargs.get("cnpj")
        if not identifier or not password:
            return None

        UserModel = get_user_model()
        identifier = str(identifier).strip()
        try:
            if "@" in identifier:
                user = UserModel._default_manager.get(email__iexact=identifier)
            else:
                user = UserModel._default_manager.get(cnpj=normalize_cnpj(identifier))
        except UserModel.DoesNotExist:
            UserModel().set_password(password)
            return None
        except UserModel.MultipleObjectsReturned:
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
