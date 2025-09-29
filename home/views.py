from django.shortcuts import render, redirect
from django.http import HttpResponse, FileResponse, JsonResponse
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.exceptions import ValidationError, AuthenticationFailed
from rest_framework import status
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from core import settings
from .authentication import KioskAuthentication
from .services import InstagramService, ImageUploadService, PayPalService
from .models import KioskHealthCheck, KioskClient, Order, CardImage
import logging
from paypalrestsdk import Payment
import json
from rest_framework import viewsets
from rest_framework.decorators import action
from .serializers import CardImageSerializer
from django.core.files.base import ContentFile
import base64
import stripe
import requests

stripe.api_key = settings.STRIPE_SECRET_KEY
logger = logging.getLogger(__name__)

def login_view(request):
    # Redirect to admin if already logged in
    if request.user.is_authenticated:
        return redirect('admin:index')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            next_url = request.GET.get('next', reverse('admin:index'))
            return redirect(next_url)
        else:
            return render(request, 'registration/login.html', {
                'error': 'Invalid credentials',
                'segment': 'login'
            })
    return render(request, 'registration/login.html', {
        'segment': 'login'
    })

@login_required
def index(request):
    return redirect('orders')

class KioskTestView(APIView):
    authentication_classes = [KioskAuthentication]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Test endpoint to verify kiosk authentication",
        responses={
            200: openapi.Response(
                description="Successful authentication",
                examples={
                    "application/json": {
                        "message": "Hello Kiosk!",
                        "kiosk_id": "uuid",
                        "login_name": "kiosk_name"
                    }
                }
            ),
            401: "Authentication credentials were not provided or are invalid"
        },
        tags=['Kiosk Authentication']
    )
    def get(self, request):
        return Response({
            "message": "Hello Kiosk!",
            "kiosk_id": str(request.user.id),
            "login_name": request.user.login_name
        })

class InstagramPostsView(APIView):
    authentication_classes = [KioskAuthentication]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Fetch recent posts from a public Instagram profile",
        manual_parameters=[
            openapi.Parameter(
                'username',
                openapi.IN_QUERY,
                description="Instagram username to fetch posts from",
                type=openapi.TYPE_STRING,
                required=True
            ),
            openapi.Parameter(
                'limit',
                openapi.IN_QUERY,
                description="Number of posts to fetch (default: 9)",
                type=openapi.TYPE_INTEGER,
                required=False,
                default=9
            )
        ],
        responses={
            200: openapi.Response(
                description="Successfully retrieved Instagram posts",
                examples={
                    "application/json": {
                        "success": True,
                        "posts": [
                            {
                                "shortcode": "ABC123",
                                "caption": "Post caption",
                                "likes": 100,
                                "date": "2024-01-20T12:00:00",
                                "image": "base64_encoded_image_data"
                            }
                        ]
                    }
                }
            ),
            400: "Invalid parameters provided",
            401: "Authentication credentials were not provided or are invalid",
            500: "Error fetching Instagram posts"
        },
        tags=['Instagram Integration']
    )
    def get(self, request):
        username = request.query_params.get('username')
        limit = request.query_params.get('limit', 9)
        
        if not username:
            raise ValidationError({'error': 'Instagram username is required'})
        
        try:
            limit = int(limit)
            if limit <= 0:
                raise ValueError("Limit must be greater than zero")
        except ValueError:
            raise ValidationError({'error': 'Invalid limit value'})

        instagram_service = InstagramService()
        try:
            # if instagram_service.authenticate('Photokiosk.ek', 'POIlkj123'):
            posts = instagram_service.get_profile_posts(username, limit)
            return Response({
                'success': True,
                'posts': posts
            }, 200)
            # else:
            #     return Response({
            #         'success': False,
            #         'message': str('failed to authenticate service')
            #     })
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e)
            }, status=500)
        finally:
            instagram_service.cleanup()

def upload_page(request, kiosk_uuid, image_uuid):
    """Public page for image upload"""
    return render(request, 'home/upload.html', {
        'kiosk_uuid': kiosk_uuid,
        'image_uuid': image_uuid
    })


def handle_upload(request, kiosk_uuid, image_uuid):
    """Handle the image upload from the public page"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    if 'images' not in request.FILES:
        return JsonResponse({'error': 'No images provided'}, status=400)
    
    images_list = []
    
    for image_file in request.FILES.getlist('images'):
        image_data = image_file.read()
        base64_image = base64.b64encode(image_data).decode('utf-8')
        images_list.append(base64_image)
        
        ImageUploadService.store_image(kiosk_uuid, image_uuid, images_list)

    return JsonResponse({'success': True, 'images': images_list})

class CreatePaymentIntentAPI(APIView):
    authentication_classes = []  # disable session / CSRF
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            amount = request.data.get("amount")
            if not amount:
                return Response({"error": "amount is required"}, status=status.HTTP_400_BAD_REQUEST)

            currency = request.data.get("currency", "usd")

            # Create PaymentIntent on Stripe
            intent = stripe.PaymentIntent.create(
                amount=int(amount),  # must be integer (in cents)
                currency=currency,
                payment_method_types=["card_present"],
                capture_method="automatic"
            )

            return Response(intent, status=status.HTTP_201_CREATED)

        except stripe.error.StripeError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class ProcessPaymentIntentAPI(APIView):
    authentication_classes = []  # disable session / CSRF
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            reader_id = request.data.get("reader_id")
            payment_intent = request.data.get("payment_intent")

            if not reader_id:
                return Response({"error": "reader_id is required"}, status=status.HTTP_400_BAD_REQUEST)
            if not payment_intent:
                return Response({"error": "payment_intent is required"}, status=status.HTTP_400_BAD_REQUEST)

            # Call Stripe API: /v1/terminal/readers/{reader_id}/process_payment_intent
            resp = stripe.terminal.Reader.process_payment_intent(
                reader_id,
                payment_intent=payment_intent
            )

            return Response(resp, status=status.HTTP_200_OK)

        except stripe.error.StripeError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CreateReaderAPI(APIView):
    authentication_classes = []  # disable session / CSRF
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            registration_code = request.data.get("registration_code")
            label = request.data.get("label")
            location = request.data.get("location")

            if not registration_code or not label or not location:
                return Response(
                    {"error": "registration_code, label, and location are required"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Call Stripe API
            reader = stripe.terminal.Reader.create(
                registration_code=registration_code,
                label=label,
                location=location
            )

            return Response(reader, status=status.HTTP_201_CREATED)

        except stripe.error.StripeError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CreateLocationAPI(APIView):
    authentication_classes = []  # disable session / CSRF
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            display_name = request.data.get("display_name")
            address = request.data.get("address")

            if not display_name or not address:
                return Response(
                    {"error": "display_name and address are required"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Required address fields
            required_fields = ["line1", "city", "state", "country", "postal_code"]
            for field in required_fields:
                if field not in address:
                    return Response(
                        {"error": f"Missing address field: {field}"},
                        status=status.HTTP_400_BAD_REQUEST
                    )

            # Call Stripe API
            location = stripe.terminal.Location.create(
                display_name=display_name,
                address={
                    "line1": address["line1"],
                    "city": address["city"],
                    "state": address["state"],
                    "country": address["country"],
                    "postal_code": address["postal_code"]
                }
            )

            return Response(location, status=status.HTTP_201_CREATED)

        except stripe.error.StripeError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class PresentPaymentMethodAPI(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        reader_id = request.data.get("reader_id")
        if not reader_id:
            return Response({"error": "reader_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        url = f"https://api.stripe.com/v1/test_helpers/terminal/readers/{reader_id}/present_payment_method"
        headers = {"Authorization": f"Bearer {settings.STRIPE_SECRET_KEY}"}

        resp = requests.post(url, headers=headers)
        try:
            data = resp.json()
            print(data)
        except Exception:
            data = {"error": "Invalid response from Stripe"}

        return Response(data, status=resp.status_code)

class ListReadersAPI(APIView):
    print(settings.STRIPE_SECRET_KEY)

    authentication_classes = []  # disable session / CSRF
    permission_classes = [AllowAny]

    def get(self, request):
        try:
            # Call Stripe API to list readers
            readers = stripe.terminal.Reader.list()
            return Response(readers, status=status.HTTP_200_OK)
        except stripe.error.StripeError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class ImageUploadFlowAPI(APIView):
    """
    API Documentation for the complete Image Upload Flow
    """
    authentication_classes = [KioskAuthentication]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="""
        Complete flow for image upload and retrieval:

        1. Generate UUIDs:
           - Generate a kiosk_uuid and image_uuid
           - These will be used to track the image upload

        2. Public Upload URL:
           - Format: /upload/{kiosk_uuid}/{image_uuid}/
           - This is a public page where users can upload images
           - No authentication required
           - Method: GET (to view page), POST (to upload)

        3. Poll for Image:
           - Endpoint: /api/kiosk/image/{kiosk_uuid}/{image_uuid}/
           - Requires kiosk authentication
           - Returns 404 if image not yet uploaded
           - Returns 200 with image data when ready
           - Image data is base64 encoded
           - Cache timeout: 5 minutes

        Example Flow:
        1. Generate UUIDs
        2. Share upload URL with user
        3. User uploads image
        4. Poll status API until image is available
        5. Retrieve and process image
        """,
        responses={
            200: openapi.Response(
                description="Example response formats for different endpoints",
                examples={
                    "application/json": {
                        "Upload Response": {
                            "success": True
                        },
                        "Status Check - Pending": {
                            "status": "pending"
                        },
                        "Status Check - Ready": {
                            "status": "ready",
                            "image": "base64_encoded_image_data"
                        }
                    }
                }
            ),
            401: "Authentication credentials were not provided",
            403: "Authentication credentials are invalid"
        },
        tags=['Image Upload']
    )
    def get(self, request):
        """Documentation endpoint for the image upload flow"""
        return Response({
            "message": "This is a documentation endpoint. Please refer to the Swagger docs for the complete flow."
        })

class ImageStatusAPI(APIView):
    """API endpoint for checking image upload status"""
    authentication_classes = [KioskAuthentication]
    permission_classes = [IsAuthenticated]

    def handle_exception(self, exc):
        if isinstance(exc, AuthenticationFailed):
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_401_UNAUTHORIZED,
                headers={'WWW-Authenticate': 'Basic realm="Kiosk API"'}
            )
        return super().handle_exception(exc)

    @swagger_auto_schema(
        operation_description="""
        Check if an image has been uploaded and retrieve it.
        
        This endpoint is used to poll for image availability after a user has uploaded
        an image through the public upload page. The image data is cached for 5 minutes
        after upload.
        
        Authentication:
        - Requires kiosk authentication
        - Use Basic Auth with kiosk credentials
        
        Polling Strategy:
        - Recommended polling interval: 1-2 seconds
        - Maximum wait time: 5 minutes (cache timeout)
        - Stop polling when status is 'ready'
        """,
        manual_parameters=[
            openapi.Parameter(
                'kiosk_uuid',
                openapi.IN_PATH,
                description="UUID of the kiosk",
                type=openapi.TYPE_STRING,
                format=openapi.FORMAT_UUID,
                required=True
            ),
            openapi.Parameter(
                'image_uuid',
                openapi.IN_PATH,
                description="UUID of the image",
                type=openapi.TYPE_STRING,
                format=openapi.FORMAT_UUID,
                required=True
            )
        ],
        responses={
            200: openapi.Response(
                description="Image found and ready",
                examples={
                    "application/json": {
                        "status": "ready",
                        "image": "base64_encoded_image_data"
                    }
                }
            ),
            401: "Authentication credentials were not provided",
            403: "Authentication credentials are invalid",
            404: openapi.Response(
                description="Image not yet uploaded or expired",
                examples={
                    "application/json": {
                        "status": "pending"
                    }
                }
            )
        },
        tags=['Image Upload']
    )
    def get(self, request, kiosk_uuid, image_uuid):
        """Check if image is available and return it"""
        images_data = ImageUploadService.get_image(kiosk_uuid, image_uuid)
        
        if not images_data:
            return Response({
                'status': 'pending'
            }, status=404)
        
        return Response({
            'status': 'ready',
            'images': images_data
        })

class KioskHealthCheckView(APIView):
    authentication_classes = [KioskAuthentication]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Get the health status of the kiosk and create a health check entry",
        responses={
            200: openapi.Response(
                description="Successful response with health status",
                examples={
                    "application/json": {
                        "kiosk_id": "uuid",
                        "login_name": "kiosk_name",
                        "is_healthy": True,
                        "last_checked": "2024-12-09T12:00:00Z",
                        "health_message": "Health check entry created successfully"
                    }
                }
            ),
            401: "Authentication credentials were not provided or are invalid"
        },
        tags=['Kiosk Health Check']
    )
    def get(self, request):
        kiosk = request.user
        logger.info(f"Creating health check entry for kiosk: {kiosk.login_name}")

        health_check, created = KioskHealthCheck.objects.update_or_create(
            kiosk=kiosk,
            defaults={
                'is_healthy': True,
                'health_message': "Health check entry created successfully"
            }
        )

        return Response({
            "kiosk_id": str(kiosk.id),
            "login_name": kiosk.login_name,
            "is_healthy": health_check.is_healthy,
            "last_checked": health_check.last_checked,
            "health_message": health_check.health_message,
        })

class CreatePaymentLinkAPI(APIView):
    authentication_classes = [KioskAuthentication]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Create a PayPal payment link",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['transaction_id', 'kiosk_id', 'price', 'num_pictures'],
            properties={
                'transaction_id': openapi.Schema(type=openapi.TYPE_STRING, description='Transaction ID'),
                'kiosk_id': openapi.Schema(type=openapi.TYPE_STRING, description='Kiosk ID'),
                'price': openapi.Schema(type=openapi.TYPE_NUMBER, description='Price of the transaction'),
                'num_pictures': openapi.Schema(type=openapi.TYPE_INTEGER, description='Number of pictures'),
            },
        ),
        responses={
            200: openapi.Response(
                description="Payment link created successfully",
                examples={
                    "application/json": {
                        "approval_url": "https://www.paypal.com/checkoutnow?token=EC-123456789"
                    }
                }
            ),
            400: "Invalid kiosk ID",
            500: "Failed to create payment link"
        },
        tags=['Payment']
    )
    def post(self, request):
        transaction_id = request.data.get('transaction_id')
        kiosk_id = request.data.get('kiosk_id')
        price = request.data.get('price')
        num_pictures = request.data.get('num_pictures')

        if not KioskClient.objects.filter(id=kiosk_id).exists():
            return Response({"error": "Invalid kiosk ID"}, status=400)

        paypal_service = PayPalService()
        payment = paypal_service.create_payment(transaction_id, kiosk_id, price, num_pictures)

        if payment:
            approval_url = next(link.href for link in payment.links if link.rel == "approval_url")
            return Response({"approval_url": approval_url}, status=200)
        else:
            return Response({"error": "Failed to create payment link"}, status=500)

class CheckPaymentStatusAPI(APIView):
    authentication_classes = [KioskAuthentication]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Check the status of a PayPal payment",
        manual_parameters=[
            openapi.Parameter(
                'transaction_id',
                openapi.IN_PATH,
                description="Transaction ID",
                type=openapi.TYPE_STRING,
                required=True
            )
        ],
        responses={
            200: openapi.Response(
                description="Payment status retrieved successfully",
                examples={
                    "application/json": {
                        "status": "completed"
                    }
                }
            ),
            404: "Order not found",
            500: "Failed to fetch payment status"
        },
        tags=['Payment']
    )
    def get(self, request, transaction_id):
        try:
            order = Order.objects.get(transaction_id=transaction_id)
            return Response({"status": order.status}, status=200)
        except Order.DoesNotExist:
            return Response({"error": "Order not found"}, status=404)

class PaypalAPIWebhook(APIView):
    permission_classes = [AllowAny]
    @csrf_exempt
    @swagger_auto_schema(
        operation_description="Handle PayPal webhook events",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'event_type': openapi.Schema(type=openapi.TYPE_STRING, description='Type of the PayPal event'),
                'resource': openapi.Schema(type=openapi.TYPE_OBJECT, description='Resource data from PayPal'),
            },
        ),
        responses={
            200: openapi.Response(
                description="Webhook processed successfully",
                examples={
                    "application/json": {
                        "status": "success"
                    }
                }
            ),
        },
        tags=['Webhook']
    )
    def post(self, request):
        payload = json.loads(request.body)
        logger.info(f"Logging payload: {payload}")
        event_type = payload.get('event_type')
        resource = payload.get('resource', {})

        if event_type in ['PAYMENT.CAPTURE.COMPLETED', 'PAYMENT.SALE.COMPLETED']:
            logger.info(f"Payment completed: {payload}")
            order = Order.objects.filter(paypal_payment_id=resource.get('parent_payment')).first()
            if order:
                order.status = 'completed'
                order.paypal_response = payload
                order.save()
        elif event_type in ['PAYMENT.CAPTURE.DENIED' 'PAYMENT.SALE.DENIED']:
            logger.warning(f"Payment denied: {payload}")
            order = Order.objects.filter(paypal_payment_id=resource.get('parent_payment')).first()
            if order:
                order.status = 'denied'
                order.paypal_response = payload
                order.save()

        return JsonResponse({'status': 'success'})

class PaypalAPIExecute(APIView):
    permission_classes = [AllowAny]
    @swagger_auto_schema(
        operation_description="Execute a PayPal payment after user approval",
        manual_parameters=[
            openapi.Parameter(
                'paymentId',
                openapi.IN_QUERY,
                description="PayPal payment ID",
                type=openapi.TYPE_STRING,
                required=True
            ),
            openapi.Parameter(
                'PayerID',
                openapi.IN_QUERY,
                description="PayPal payer ID",
                type=openapi.TYPE_STRING,
                required=True
            )
        ],
        responses={
            200: openapi.Response(
                description="Payment executed successfully",
                examples={
                    "application/json": {
                        "success": True,
                        "message": "Payment executed successfully"
                    }
                }
            ),
            400: "Missing paymentId or PayerID",
            500: "Payment execution failed"
        },
        tags=['Payment']
    )
    def get(self, request):
        payment_id = request.GET.get('paymentId')
        payer_id = request.GET.get('PayerID')

        if not payment_id or not payer_id:
            logger.error("Payment execution failed: Missing paymentId or PayerID")
            return JsonResponse({'success': False, 'message': 'Payment execution failed'}, status=400)

        payment = Payment.find(payment_id)

        if payment.execute({"payer_id": payer_id}):
            logger.info(f"Payment executed successfully for payment ID {payment_id}")
            return JsonResponse({'success': True, 'message': 'Payment executed successfully'})
        else:
            logger.error(f"Error while executing payment: {payment.error}")
            return JsonResponse({'success': False, 'message': 'Payment execution failed'}, status=500)

class PaypalAPICancel(APIView):
    permission_classes = [AllowAny]
    @swagger_auto_schema(
        operation_description="Handle PayPal payment cancellation",
        responses={
            200: openapi.Response(
                description="Payment was cancelled",
                examples={
                    "application/json": {
                        "success": False,
                        "message": "Payment was cancelled"
                    }
                }
            )
        },
        tags=['Payment']
    )
    def get(self, request):
        logger.info("Payment was cancelled by the user.")
        return JsonResponse({'success': False, 'message': 'Payment was cancelled'})

class CardImageAPI(APIView):
    authentication_classes = [KioskAuthentication]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Get all available card images",
        responses={
            200: openapi.Response(
                description="List of card images",
                examples={
                    "application/json": {
                        "cards": [
                            {
                                "id": "uuid",
                                "title": "Card Title",
                                "description": "Card Description",
                                "image_url": "https://example.com/image.jpg",
                                "version": 1
                            }
                        ]
                    }
                }
            )
        },
        tags=['Cards']
    )
    def get(self, request):
        cards = CardImage.objects.filter(is_enabled=True)
        cards_data = [
            {
                "id": str(card.id),
                "image_url": f"{settings.MEDIA_URL}{card.image}",
                "version": card.version,
                "is_enabled": card.is_enabled,
                "created_at": card.created_at.isoformat(),
                "updated_at": card.updated_at.isoformat(),
            }
            for card in cards
        ]

        return Response({"cards": cards_data}, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        operation_description="Get cards that need updating based on version",
        manual_parameters=[
            openapi.Parameter(
                'versions',
                openapi.IN_QUERY,
                description="JSON array of {id: version} pairs",
                type=openapi.TYPE_STRING,
                required=True
            )
        ],
        tags=['Cards']
    )
    def post(self, request):
        try:
            versions = json.loads(request.data.get('versions', '{}'))
            updates_needed = []
            
            for card_id, client_version in versions.items():
                try:
                    card = CardImage.objects.get(id=card_id, is_enabled=True)
                    if card.version > int(client_version):
                        updates_needed.append(card)
                except CardImage.DoesNotExist:
                    continue
                    
            serializer = CardImageSerializer(updates_needed, many=True)
            return Response({"updates": serializer.data})
        except json.JSONDecodeError:
            return Response(
                {"error": "Invalid versions format"}, 
                status=400
            )