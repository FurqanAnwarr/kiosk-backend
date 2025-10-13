import hmac, hashlib
from django.http import JsonResponse
from home.models import KioskDevice


class KioskAuthMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        kiosk_id = request.headers.get("X-Kiosk-ID")
        signature = request.headers.get("X-Kiosk-Signature")

        if kiosk_id and signature:
            try:
                kiosk = KioskDevice.objects.get(kiosk_id=kiosk_id)
            except KioskDevice.DoesNotExist:
                return JsonResponse({"error": "Invalid kiosk"}, status=403)

            if kiosk.status == "disabled":
                return JsonResponse({"error": "Kiosk disabled"}, status=403)

            expected_sig = hmac.new(
                kiosk.secret_key_hash.encode(), kiosk_id.encode(), hashlib.sha256
            ).hexdigest()

            if not hmac.compare_digest(expected_sig, signature):
                return JsonResponse({"error": "Invalid signature"}, status=403)

            # Update heartbeat
            kiosk.last_seen_at = timezone.now()
            kiosk.save(update_fields=["last_seen_at"])

        return self.get_response(request)
