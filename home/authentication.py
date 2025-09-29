from rest_framework import authentication
from rest_framework import exceptions
from django.utils import timezone
from .models import KioskClient
import base64

class KioskAuthentication(authentication.BaseAuthentication):
    def authenticate(self, request):
        auth_header = request.META.get('HTTP_AUTHORIZATION')
        if not auth_header:
            return None

        try:
            auth_type, auth_string = auth_header.split(' ', 1)
            if auth_type.lower() != 'basic':
                return None

            decoded = base64.b64decode(auth_string).decode('utf-8')
            username, password = decoded.split(':', 1)
            
            try:
                kiosk = KioskClient.objects.get(login_name=username)
            except KioskClient.DoesNotExist:
                raise exceptions.AuthenticationFailed('Invalid kiosk credentials')

            if not kiosk.is_active:
                raise exceptions.AuthenticationFailed('Kiosk is inactive')

            if not kiosk.check_password(password):
                raise exceptions.AuthenticationFailed('Invalid kiosk credentials')

            # Update last login
            kiosk.last_login = timezone.now()
            kiosk.save(update_fields=['last_login'])

            return (kiosk, None)
        except (ValueError, UnicodeDecodeError):
            raise exceptions.AuthenticationFailed('Invalid authorization header')

    def authenticate_header(self, request):
        """Return the authentication header format expected"""
        return 'Basic realm="Kiosk API"'