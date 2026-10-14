import hashlib
import logging
import mimetypes
import smtplib
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from PIL import Image, UnidentifiedImageError

from .models import (
    EmailVerification,
    Order,
    PaymentProof,
    Category,
    Product,
    StoreSettings,
    User,
)
from .permissions import CanManageStore, IsVerifiedCustomer
from .serializers import (
    EmailLoginSerializer,
    ManagedCategorySerializer,
    ManagedOrderSerializer,
    ManagedProductSerializer,
    ManagedStoreSettingsSerializer,
    OrderSerializer,
    ProductSerializer,
    RegistrationSerializer,
    StoreSettingsSerializer,
)
from .services import (
    cancel_order,
    confirm_order,
    create_order,
    expire_stale_reservations,
)

logger = logging.getLogger(__name__)


class EmailDeliveryUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE


class RegisterView(generics.CreateAPIView):
    serializer_class = RegistrationSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        self.ensure_email_backend_configured()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        token = EmailVerification.issue(user)
        verification_url = f"{settings.FRONTEND_URL}/?verify={token}"
        try:
            send_mail(
                "Verifica tu correo - Tienda",
                f"Confirma tu correo abriendo este enlace (válido por 24 horas):\n{verification_url}",
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                fail_silently=False,
            )
        except (smtplib.SMTPException, OSError) as error:
            logger.exception("Brevo SMTP delivery failed during account registration.")
            user.delete()
            raise EmailDeliveryUnavailable(
                "No se pudo enviar el correo por Brevo. Revisa la clave SMTP, "
                "el remitente verificado y la conexión, y vuelve a intentarlo."
            ) from error
        detail = "Cuenta creada. Revisa tu correo para verificarla."
        if (
            settings.DEBUG
            and settings.EMAIL_BACKEND
            == "django.core.mail.backends.console.EmailBackend"
        ):
            detail = (
                "Cuenta creada. El enlace de verificación aparece en la terminal "
                "donde está ejecutándose Django."
            )
        return Response(
            {"detail": detail},
            status=status.HTTP_201_CREATED,
        )

    @staticmethod
    def ensure_email_backend_configured():
        if (
            settings.EMAIL_BACKEND
            == "django.core.mail.backends.smtp.EmailBackend"
            and not settings.EMAIL_HOST_PASSWORD
        ):
            raise EmailDeliveryUnavailable(
                "El correo no está configurado: falta EMAIL_HOST_PASSWORD en la "
                "misma terminal desde la que se inicia Django."
            )


class VerifyEmailView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        token = request.data.get("token", "")
        if not isinstance(token, str) or not token:
            raise ValidationError({"token": "El enlace de verificación no es válido."})
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        verification = get_object_or_404(
            EmailVerification, token_hash=token_hash
        )
        if verification.expires_at <= timezone.now():
            verification.delete()
            raise ValidationError(
                {"token": "El enlace venció. Solicita uno nuevo al administrador."}
            )
        verification.user.email_verified = True
        verification.user.save(update_fields=["email_verified"])
        verification.delete()
        return Response({"detail": "Correo verificado. Ya puedes iniciar sesión."})


class ResendEmailVerificationView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        RegisterView.ensure_email_backend_configured()
        email = request.data.get("email", "")
        if isinstance(email, str) and email.strip():
            user = User.objects.filter(
                email__iexact=email.strip(), email_verified=False
            ).first()
            if user:
                verification = EmailVerification.objects.filter(user=user).first()
                may_resend = (
                    verification is None
                    or verification.created_at <= timezone.now() - timedelta(minutes=2)
                )
                if may_resend:
                    token = EmailVerification.issue(user)
                    verification_url = f"{settings.FRONTEND_URL}/?verify={token}"
                    try:
                        send_mail(
                            "Verifica tu correo - Tienda",
                            f"Confirma tu correo abriendo este enlace (válido por 24 horas):\n{verification_url}",
                            settings.DEFAULT_FROM_EMAIL,
                            [user.email],
                            fail_silently=False,
                        )
                    except (smtplib.SMTPException, OSError) as error:
                        logger.exception("Brevo SMTP delivery failed during verification resend.")
                        raise EmailDeliveryUnavailable(
                            "Brevo no pudo enviar el correo. Revisa la clave SMTP, "
                            "el remitente verificado y la conexión, y vuelve a intentarlo."
                        ) from error
        if settings.EMAIL_BACKEND == "django.core.mail.backends.console.EmailBackend":
            detail = (
                "Si existe una cuenta pendiente y ya pasaron dos minutos, el enlace "
                "aparece en la terminal donde está ejecutándose Django."
            )
        else:
            detail = (
                "Si existe una cuenta pendiente para ese correo, enviaremos un "
                "nuevo enlace de verificación."
            )
        return Response({"detail": detail})


class LoginView(TokenObtainPairView):
    serializer_class = EmailLoginSerializer


class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response(
            {
                "id": user.pk,
                "email": user.email,
                "name": user.get_full_name(),
                "phone": user.phone,
                "role": "superuser" if user.is_superuser else user.role,
                "can_manage_store": user.can_manage_store,
            }
        )


class ProductListView(generics.ListAPIView):
    serializer_class = ProductSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        expire_stale_reservations()
        queryset = Product.objects.filter(is_active=True).prefetch_related("images")
        category = self.request.query_params.get("category")
        if category:
            queryset = queryset.filter(category__name=category)
        return queryset


class StoreSettingsView(generics.RetrieveAPIView):
    serializer_class = StoreSettingsSerializer
    permission_classes = [AllowAny]

    def get_object(self):
        return StoreSettings.current()


class ManagedStoreSettingsView(generics.RetrieveUpdateAPIView):
    serializer_class = ManagedStoreSettingsSerializer
    permission_classes = [IsAuthenticated, CanManageStore]

    def get_object(self):
        return StoreSettings.current()


class ManagedProductViewSet(viewsets.ModelViewSet):
    serializer_class = ManagedProductSerializer
    permission_classes = [IsAuthenticated, CanManageStore]
    queryset = Product.objects.select_related("category").prefetch_related("images")

    def destroy(self, request, *args, **kwargs):
        product = self.get_object()
        if product.orderitem_set.exists():
            raise ValidationError(
                {"product": "Este producto está asociado a pedidos y no se puede borrar. Desactívalo."}
            )
        return super().destroy(request, *args, **kwargs)


class ManagedCategoryViewSet(viewsets.ModelViewSet):
    serializer_class = ManagedCategorySerializer
    permission_classes = [IsAuthenticated, CanManageStore]
    queryset = Category.objects.all()

class ManagedOrderViewSet(viewsets.GenericViewSet):
    serializer_class = ManagedOrderSerializer
    permission_classes = [IsAuthenticated, CanManageStore]

    def get_queryset(self):
        expire_stale_reservations()
        queryset = (
            Order.objects.select_related("user")
            .prefetch_related(
                "items__product__category",
                "items__product__images",
                "proofs",
            )
            .order_by("-created_at")
        )
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        return queryset

    def list(self, request):
        queryset = self.get_queryset()
        return Response(self.get_serializer(queryset, many=True).data)

    def retrieve(self, request, pk=None):
        order = get_object_or_404(self.get_queryset(), pk=pk)
        return Response(self.get_serializer(order).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        order = confirm_order(pk)
        return Response(self.get_serializer(order).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def reject(self, request, pk=None):
        reason = str(request.data.get("reason", "")).strip()
        if not reason:
            raise ValidationError({"reason": "Escribe el motivo del rechazo."})
        order = get_object_or_404(
            Order.objects.select_for_update(), pk=pk
        )
        if order.payment_method == Order.PaymentMethod.CASH:
            raise ValidationError(
                {"payment_method": "Los pedidos en efectivo se coordinan con el cliente; no tienen comprobante que rechazar."}
            )
        if order.status not in (
            Order.Status.PENDING,
            Order.Status.PROOF_SUBMITTED,
            Order.Status.PAYMENT_REJECTED,
        ):
            raise ValidationError(
                {"status": "Este pedido ya no admite rechazo de comprobante."}
            )
        if order.reservation_expires_at <= timezone.now():
            expire_stale_reservations()
            raise ValidationError({"status": "La reserva del pedido venció."})
        order.status = Order.Status.PAYMENT_REJECTED
        order.payment_rejection_reason = reason
        order.save(
            update_fields=[
                "status",
                "payment_rejection_reason",
                "updated_at",
            ]
        )
        return Response(self.get_serializer(order).data)

    @action(detail=True, methods=["post"], url_path="preparing")
    def mark_preparing(self, request, pk=None):
        return self._transition(
            pk, Order.Status.CONFIRMED, Order.Status.PREPARING
        )

    @action(detail=True, methods=["post"], url_path="ready")
    def mark_ready(self, request, pk=None):
        return self._transition(
            pk, Order.Status.PREPARING, Order.Status.READY
        )

    @action(detail=True, methods=["post"], url_path="complete")
    def mark_complete(self, request, pk=None):
        return self._transition(
            pk, Order.Status.READY, Order.Status.COMPLETED
        )

    def _transition(self, pk, expected_status, next_status):
        with transaction.atomic():
            order = get_object_or_404(
                Order.objects.select_for_update().select_related("user"),
                pk=pk,
            )
            if order.status != expected_status:
                raise ValidationError(
                    {"status": f"Solo se puede cambiar desde {order.get_status_display()}."}
                )
            order.status = next_status
            order.save(update_fields=["status", "updated_at"])
        order = self.get_queryset().get(pk=pk)
        return Response(self.get_serializer(order).data)


class OrderViewSet(viewsets.GenericViewSet):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated, IsVerifiedCustomer]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        expire_stale_reservations()
        return (
            Order.objects.filter(user=self.request.user)
            .prefetch_related("items", "proofs")
            .order_by("-created_at")
        )

    def list(self, request):
        return Response(self.get_serializer(self.get_queryset(), many=True).data)

    def retrieve(self, request, pk=None):
        order = get_object_or_404(self.get_queryset(), pk=pk)
        return Response(self.get_serializer(order).data)

    @transaction.atomic
    def create(self, request):
        items = request.data.get("items", [])
        if isinstance(items, str):
            import json

            try:
                items = json.loads(items)
            except ValueError:
                raise ValidationError({"items": "El formato del carrito no es válido."})
        if not isinstance(items, list):
            raise ValidationError({"items": "El carrito debe ser una lista."})
        payment_method = request.data.get("payment_method", "")
        image = request.FILES.get("proof")
        if payment_method != Order.PaymentMethod.CASH:
            if not image:
                raise ValidationError(
                    {"proof": "Debes adjuntar la captura de la transferencia para crear el pedido."}
                )
            self.validate_proof_image(image, "proof")
        expire_stale_reservations()
        order = create_order(
            user=request.user,
            items=items,
            payment_method=payment_method,
            transaction_number=request.data.get("transaction_number", ""),
            customer_note=request.data.get("customer_note", ""),
        )
        if image:
            PaymentProof.objects.create(order=order, image=image)
            order.status = Order.Status.PROOF_SUBMITTED
            order.save(update_fields=["status", "updated_at"])
            order.refresh_from_db()
        return Response(
            self.get_serializer(order).data, status=status.HTTP_201_CREATED
        )

    @action(
        detail=True,
        methods=["post"],
        url_path="proof",
        parser_classes=[MultiPartParser, FormParser],
    )
    def submit_proof(self, request, pk=None):
        order = get_object_or_404(self.get_queryset(), pk=pk)
        if order.payment_method == Order.PaymentMethod.CASH:
            raise ValidationError({"proof": "Los pedidos en efectivo no requieren captura."})
        if order.status not in (
            Order.Status.PENDING,
            Order.Status.PAYMENT_REJECTED,
            Order.Status.PROOF_SUBMITTED,
        ):
            raise ValidationError({"status": "Este pedido no admite comprobantes."})
        if order.reservation_expires_at <= timezone.now():
            expire_stale_reservations()
            raise ValidationError({"status": "La reserva de este pedido venció."})
        transaction_number = order.transaction_number
        if order.payment_method in (
            Order.PaymentMethod.BPA,
            Order.PaymentMethod.ZELLE,
        ):
            transaction_number = str(
                request.data.get("transaction_number", order.transaction_number)
            ).strip()
            if not transaction_number:
                raise ValidationError(
                    {"transaction_number": "El número de transacción es obligatorio."}
                )
        image = request.FILES.get("image")
        if not image:
            raise ValidationError({"image": "Selecciona una captura del comprobante."})
        self.validate_proof_image(image)
        PaymentProof.objects.create(order=order, image=image)
        if order.payment_method in (
            Order.PaymentMethod.BPA,
            Order.PaymentMethod.ZELLE,
        ):
            order.transaction_number = transaction_number[:100]
        order.status = Order.Status.PROOF_SUBMITTED
        order.payment_rejection_reason = ""
        order.save(
            update_fields=[
                "transaction_number",
                "status",
                "payment_rejection_reason",
                "updated_at",
            ]
        )
        order.refresh_from_db()
        return Response(self.get_serializer(order).data, status=status.HTTP_201_CREATED)

    @staticmethod
    def validate_proof_image(image, field_name="image"):
        if image.size > 5 * 1024 * 1024:
            raise ValidationError({field_name: "La imagen no puede superar 5 MB."})
        extension = image.name.rsplit(".", 1)[-1].lower()
        if extension not in ("jpg", "jpeg", "png", "webp"):
            raise ValidationError({field_name: "Formato no admitido. Usa JPG, PNG o WEBP."})
        image.seek(0)
        try:
            image_content = Image.open(image)
            if image_content.format not in ("JPEG", "PNG", "WEBP"):
                raise ValidationError(
                    {field_name: "Formato no admitido. Usa JPG, PNG o WEBP."}
                )
            if image_content.width * image_content.height > 25_000_000:
                raise ValidationError({field_name: "La imagen supera la resolución permitida."})
            image_content.verify()
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
            raise ValidationError({field_name: "El archivo no es una imagen válida."})
        image.seek(0)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        order = get_object_or_404(self.get_queryset(), pk=pk)
        order = cancel_order(order)
        return Response(self.get_serializer(order).data)


class PaymentProofFileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, order_id, proof_id):
        proof = get_object_or_404(
            PaymentProof.objects.select_related("order"),
            pk=proof_id,
            order_id=order_id,
        )
        if (
            not request.user.can_manage_store
            and proof.order.user_id != request.user.id
        ):
            raise PermissionDenied("No tienes permiso para ver este comprobante.")
        response = FileResponse(
            proof.image.open("rb"),
            content_type=mimetypes.guess_type(proof.image.name)[0] or "application/octet-stream",
        )
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response
