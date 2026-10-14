import json
import smtplib
from datetime import timedelta
from io import BytesIO
from unittest.mock import MagicMock, patch
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core import mail
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.exceptions import ValidationError
from urllib.parse import parse_qs, urlparse

from .models import (
    Category,
    EmailVerification,
    Order,
    PaymentProof,
    Product,
    ProductImage,
    User,
)
from .services import cancel_order, confirm_order, create_order, expire_stale_reservations
from .email_backend import BrevoEmailBackend


def valid_png():
    stream = BytesIO()
    Image.new("RGB", (2, 2), "red").save(stream, format="PNG")
    return SimpleUploadedFile(
        "receipt.png", stream.getvalue(), content_type="image/png"
    )


class IsolatedMediaTestCase(TestCase):
    def setUp(self):
        super().setUp()
        self.test_media = tempfile.TemporaryDirectory()
        media_settings = override_settings(MEDIA_ROOT=self.test_media.name)
        media_settings.enable()
        self.addCleanup(self.test_media.cleanup)
        self.addCleanup(media_settings.disable)


class OrderInventoryTests(IsolatedMediaTestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="buyer@example.com",
            password="correct-horse-battery-staple",
            first_name="Ana",
            last_name="Compradora",
            phone="+5355555555",
            email_verified=True,
        )
        self.category = Category.objects.create(name="Disco de Ps5")
        self.product = Product.objects.create(
            name="Disco PS5",
            description="Juego físico",
            category=self.category,
            price_cup=12000,
            stock=4,
        )

    def order(self, method=Order.PaymentMethod.BPA, quantity=1):
        return create_order(
            user=self.user,
            items=[{"product_id": self.product.pk, "quantity": quantity}],
            payment_method=method,
            transaction_number=(
                "TX-12345"
                if method in (Order.PaymentMethod.BPA, Order.PaymentMethod.ZELLE)
                else ""
            ),
        )

    def test_order_reserves_stock_then_confirmation_deducts_it(self):
        order = self.order()

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 4)
        self.assertEqual(self.product.available_stock, 3)
        self.assertEqual(order.total_cup, 12000)

        with self.assertRaises(ValidationError):
            confirm_order(order.pk)

        PaymentProof.objects.create(order=order, image=valid_png())
        Order.objects.filter(pk=order.pk).update(status=Order.Status.PROOF_SUBMITTED)
        confirm_order(order.pk)
        self.product.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(self.product.stock, 3)
        self.assertEqual(self.product.reserved_stock, 0)
        self.assertEqual(order.status, Order.Status.CONFIRMED)

    def test_cash_order_can_be_confirmed_without_a_proof(self):
        order = self.order(Order.PaymentMethod.CASH)
        confirm_order(order.pk)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 3)

    def test_cancelling_order_releases_reserved_stock(self):
        order = self.order(quantity=2)
        cancel_order(order)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 4)
        self.assertEqual(self.product.reserved_stock, 0)
        self.assertEqual(self.product.available_stock, 4)

    def test_zelle_requires_an_eligible_item(self):
        self.category.name = "Videojuegos"
        self.category.save(update_fields=["name"])

        with self.assertRaises(ValidationError):
            self.order(Order.PaymentMethod.ZELLE)

    def test_bpa_and_zelle_require_transaction_number(self):
        with self.assertRaises(ValidationError):
            create_order(
                user=self.user,
                items=[{"product_id": self.product.pk, "quantity": 1}],
                payment_method=Order.PaymentMethod.BPA,
            )
        with self.assertRaises(ValidationError):
            create_order(
                user=self.user,
                items=[{"product_id": self.product.pk, "quantity": 1}],
                payment_method=Order.PaymentMethod.ZELLE,
                transaction_number="   ",
            )

    def test_expired_order_is_closed_and_stock_is_released(self):
        order = self.order(quantity=3)
        Order.objects.filter(pk=order.pk).update(
            reservation_expires_at=timezone.now() - timedelta(seconds=1)
        )

        expire_stale_reservations()
        order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(order.status, Order.Status.EXPIRED)
        self.assertEqual(self.product.reserved_stock, 0)
        self.assertEqual(self.product.available_stock, 4)

    def test_cancel_cannot_change_confirmed_orders(self):
        order = self.order(Order.PaymentMethod.CASH)
        confirm_order(order.pk)

        with self.assertRaises(ValidationError):
            cancel_order(order)


class OrderApiTests(IsolatedMediaTestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="api-buyer@example.com",
            password="correct-horse-battery-staple",
            first_name="Ana",
            last_name="Compradora",
            phone="+5355555555",
            email_verified=True,
        )
        category = Category.objects.create(name="Consola")
        self.product = Product.objects.create(
            name="Consola",
            category=category,
            price_cup=50000,
            stock=2,
        )
        ProductImage.objects.create(
            product=self.product,
            image_url="https://images.example.com/ps5-disc.png",
            alt_text="Disco PS5",
        )
        self.client = APIClient()
        access = str(RefreshToken.for_user(self.user).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    def test_transfer_checkout_requires_proof_and_private_proof_access(self):
        product_response = self.client.get("/api/products/")
        self.assertEqual(product_response.status_code, 200)
        self.assertEqual(product_response.data[0]["category"], "Consola")
        self.assertTrue(product_response.data[0]["zelle_eligible"])
        self.assertEqual(
            product_response.data[0]["images"][0]["image_url"],
            "https://images.example.com/ps5-disc.png",
        )

        missing_transaction_response = self.client.post(
            "/api/orders/",
            {
                "items": [{"product_id": self.product.pk, "quantity": 1}],
                "payment_method": "bpa",
            },
            format="json",
        )
        self.assertEqual(missing_transaction_response.status_code, 400)
        self.assertEqual(Order.objects.count(), 0)

        response = self.client.post(
            "/api/orders/",
            {
                "items": '[{"product_id": %d, "quantity": 1}]' % self.product.pk,
                "payment_method": "bpa",
                "transaction_number": "TX-001",
                "proof": valid_png(),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 201)
        order_id = response.data["id"]
        self.assertEqual(response.data["status"], Order.Status.PROOF_SUBMITTED)
        self.assertEqual(response.data["transaction_number"], "TX-001")
        self.assertEqual(len(response.data["proofs"]), 1)
        order_item = response.data["items"][0]
        self.assertEqual(order_item["category_name"], "Consola")
        self.assertEqual(
            order_item["product_image_url"],
            "https://images.example.com/ps5-disc.png",
        )

        proof_id = response.data["proofs"][0]["id"]
        file_url = f"/api/orders/{order_id}/proofs/{proof_id}/"
        proof_file_response = self.client.get(file_url)
        self.assertEqual(proof_file_response.status_code, 200)
        proof_file_response.close()

        other_user = User.objects.create_user(
            email="other@example.com",
            password="another-correct-horse-battery",
            phone="+5355551234",
            email_verified=True,
        )
        other_token = str(RefreshToken.for_user(other_user).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {other_token}")
        self.assertEqual(self.client.get(file_url).status_code, 403)

    def test_all_transfer_methods_require_proof_during_order_creation(self):
        for method, transaction_number in (
            ("bpa", "TX-11"),
            ("mobile", ""),
            ("zelle", "TX-12"),
        ):
            with self.subTest(method=method):
                response = self.client.post(
                    "/api/orders/",
                    {
                        "items": [{"product_id": self.product.pk, "quantity": 1}],
                        "payment_method": method,
                        "transaction_number": transaction_number,
                    },
                    format="json",
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn("proof", response.data)
        self.assertEqual(Order.objects.count(), 0)

    def test_cash_order_does_not_require_proof(self):
        response = self.client.post(
            "/api/orders/",
            {
                "items": [{"product_id": self.product.pk, "quantity": 1}],
                "payment_method": "cash",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["proofs"], [])

    def test_order_creation_requires_login_and_verified_email(self):
        order_payload = {
            "items": [{"product_id": self.product.pk, "quantity": 1}],
            "payment_method": "cash",
        }
        self.client.credentials()
        self.assertEqual(
            self.client.post("/api/orders/", order_payload, format="json").status_code,
            401,
        )

        unverified_user = User.objects.create_user(
            email="unverified@example.com",
            password="another-correct-horse-battery",
            phone="+5355551235",
            email_verified=False,
        )
        access = str(RefreshToken.for_user(unverified_user).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        self.assertEqual(
            self.client.post("/api/orders/", order_payload, format="json").status_code,
            403,
        )


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class RegistrationApiTests(IsolatedMediaTestCase):
    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
        EMAIL_HOST_PASSWORD="",
    )
    def test_registration_reports_missing_smtp_password_instead_of_using_console(self):
        response = self.client.post(
            "/api/auth/register/",
            {
                "email": "smtp-not-configured@example.com",
                "password": "TriX!ravel_9284_Golden",
                "first_name": "Cliente",
                "last_name": "Nuevo",
                "phone": "+5355559876",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 503)
        self.assertIn("EMAIL_HOST_PASSWORD", response.data["detail"])
        self.assertFalse(User.objects.filter(email="smtp-not-configured@example.com").exists())

    @patch("backend.store.views.send_mail", side_effect=OSError("SMTP connection failed"))
    def test_registration_reports_brevo_failure_and_removes_unverified_account(self, send_mail_mock):
        with override_settings(
            EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
            EMAIL_HOST_PASSWORD="configured-secret",
        ):
            with self.assertLogs("backend.store.views", level="ERROR") as logs:
                response = self.client.post(
                    "/api/auth/register/",
                    {
                        "email": "smtp-failed@example.com",
                        "password": "TriX!ravel_9284_Golden",
                        "first_name": "Cliente",
                        "last_name": "Nuevo",
                        "phone": "+5355559876",
                    },
                    format="json",
                )
        self.assertEqual(response.status_code, 503)
        self.assertIn("Brevo", response.data["detail"])
        self.assertFalse(User.objects.filter(email="smtp-failed@example.com").exists())
        send_mail_mock.assert_called_once()
        self.assertIn("SMTP connection failed", logs.output[0])

    def test_email_must_be_verified_before_login(self):
        response = self.client.post(
            "/api/auth/register/",
            {
                "email": "new-customer@example.com",
                "password": "TriX!ravel_9284_Golden",
                "first_name": "Cliente",
                "last_name": "Nuevo",
                "phone": "+5355559876",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            self.client.post(
                "/api/auth/login/",
                {
                    "email": "new-customer@example.com",
                    "password": "TriX!ravel_9284_Golden",
                },
                format="json",
            ).status_code,
            400,
        )

        verification_url = mail.outbox[0].body.splitlines()[-1]
        verification_token = parse_qs(urlparse(verification_url).query)["verify"][0]
        verify_response = self.client.post(
            "/api/auth/verify-email/",
            {"token": verification_token},
            format="json",
        )
        self.assertEqual(verify_response.status_code, 200)
        login_response = self.client.post(
            "/api/auth/login/",
            {
                "email": "new-customer@example.com",
                "password": "TriX!ravel_9284_Golden",
            },
            format="json",
        )
        self.assertEqual(login_response.status_code, 200)

    def test_registration_can_resend_verification_after_cooldown(self):
        response = self.client.post(
            "/api/auth/register/",
            {
                "email": "resend-customer@example.com",
                "password": "TriX!ravel_9284_Golden",
                "first_name": "Cliente",
                "last_name": "Nuevo",
                "phone": "+5355559876",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(mail.outbox), 1)

        resend_url = "/api/auth/resend-verification/"
        self.assertEqual(
            self.client.post(
                resend_url,
                {"email": "resend-customer@example.com"},
                format="json",
            ).status_code,
            200,
        )
        self.assertEqual(len(mail.outbox), 1)

        verification = EmailVerification.objects.get(
            user__email="resend-customer@example.com"
        )
        EmailVerification.objects.filter(pk=verification.pk).update(
            created_at=timezone.now() - timedelta(minutes=3)
        )
        resend_response = self.client.post(
            resend_url,
            {"email": "resend-customer@example.com"},
            format="json",
        )
        self.assertEqual(resend_response.status_code, 200)
        self.assertEqual(len(mail.outbox), 2)


class BrevoEmailBackendTests(TestCase):
    @override_settings(BREVO_API_KEY="test-api-key")
    @patch("backend.store.email_backend.urlopen")
    def test_backend_posts_transactional_email_to_brevo_api(self, urlopen_mock):
        response = MagicMock()
        response.status = 201
        urlopen_mock.return_value.__enter__.return_value = response
        message = mail.EmailMultiAlternatives(
            subject="Verifica tu correo",
            body="Abre el enlace",
            from_email="Tienda Gamer <pedro@example.com>",
            to=["cliente@example.com"],
        )

        sent = BrevoEmailBackend().send_messages([message])

        self.assertEqual(sent, 1)
        request = urlopen_mock.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(request.full_url, BrevoEmailBackend.api_url)
        self.assertEqual(request.get_header("Api-key"), "test-api-key")
        self.assertEqual(payload["sender"], {"email": "pedro@example.com", "name": "Tienda Gamer"})
        self.assertEqual(payload["to"], [{"email": "cliente@example.com"}])
        self.assertEqual(payload["subject"], "Verifica tu correo")
        self.assertEqual(payload["textContent"], "Abre el enlace")

    @override_settings(BREVO_API_KEY="")
    def test_backend_requires_brevo_api_key(self):
        message = mail.EmailMessage(subject="test", body="test", to=["test@example.com"])
        with self.assertRaisesRegex(smtplib.SMTPException, "BREVO_API_KEY"):
            BrevoEmailBackend().send_messages([message])


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }
)
class AdminPanelTests(IsolatedMediaTestCase):
    def setUp(self):
        super().setUp()
        self.customer = User.objects.create_user(
            email="customer@example.com",
            password="correct-horse-battery-staple",
            phone="+5355554321",
            email_verified=True,
        )
        self.admin_user = get_user_model().objects.create_superuser(
            email="owner@example.com",
            password="correct-horse-battery-staple",
            phone="+5355550000",
            first_name="Dueño",
            last_name="Tienda",
        )
        category = Category.objects.create(name="Accesorios")
        self.product = Product.objects.create(
            name="Control",
            category=category,
            price_cup=8000,
            stock=2,
        )
        self.order = create_order(
            user=self.customer,
            items=[{"product_id": self.product.pk, "quantity": 1}],
            payment_method=Order.PaymentMethod.BPA,
            transaction_number="BPA-12345",
        )
        self.proof = PaymentProof.objects.create(
            order=self.order, image=valid_png()
        )
        Order.objects.filter(pk=self.order.pk).update(
            status=Order.Status.PROOF_SUBMITTED
        )
        self.client.force_login(self.admin_user)

    def test_superuser_can_create_cash_order_with_products_from_admin(self):
        response = self.client.post(
            "/admin/store/order/add/",
            {
                "user": str(self.customer.pk),
                "payment_method": Order.PaymentMethod.CASH,
                "transaction_number": "",
                "customer_note": "Coordinar por teléfono",
                "items-TOTAL_FORMS": "1",
                "items-INITIAL_FORMS": "0",
                "items-MIN_NUM_FORMS": "1",
                "items-MAX_NUM_FORMS": "1000",
                "items-0-product": str(self.product.pk),
                "items-0-quantity": "1",
            },
        )

        self.assertEqual(response.status_code, 302)
        created_order = Order.objects.exclude(pk=self.order.pk).get()
        self.assertEqual(created_order.payment_method, Order.PaymentMethod.CASH)
        self.assertEqual(created_order.total_cup, self.product.price_cup)
        self.assertEqual(created_order.items.count(), 1)
        self.assertEqual(created_order.items.get().quantity, 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.reserved_stock, 2)

    def test_superuser_cannot_create_electronic_order_without_proof(self):
        response = self.client.post(
            "/admin/store/order/add/",
            {
                "user": str(self.customer.pk),
                "payment_method": Order.PaymentMethod.MOBILE,
                "transaction_number": "",
                "customer_note": "",
                "items-TOTAL_FORMS": "1",
                "items-INITIAL_FORMS": "0",
                "items-MIN_NUM_FORMS": "1",
                "items-MAX_NUM_FORMS": "1000",
                "items-0-product": str(self.product.pk),
                "items-0-quantity": "1",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Adjunta la captura obligatoria del pago.")
        self.assertEqual(Order.objects.count(), 1)

    def test_superuser_can_create_electronic_order_with_required_proof(self):
        response = self.client.post(
            "/admin/store/order/add/",
            {
                "user": str(self.customer.pk),
                "payment_method": Order.PaymentMethod.BPA,
                "transaction_number": "BPA-ADMIN-123",
                "customer_note": "",
                "items-TOTAL_FORMS": "1",
                "items-INITIAL_FORMS": "0",
                "items-MIN_NUM_FORMS": "1",
                "items-MAX_NUM_FORMS": "1000",
                "items-0-product": str(self.product.pk),
                "items-0-quantity": "1",
                "proof": valid_png(),
            },
        )

        self.assertEqual(response.status_code, 302)
        created_order = Order.objects.exclude(pk=self.order.pk).get()
        self.assertEqual(created_order.status, Order.Status.PROOF_SUBMITTED)
        self.assertEqual(created_order.transaction_number, "BPA-ADMIN-123")
        self.assertEqual(created_order.proofs.count(), 1)

    def test_superuser_can_delete_selected_orders_and_release_reservations(self):
        proof_path = self.proof.image.name
        self.assertTrue(self.proof.image.storage.exists(proof_path))

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                "/admin/store/order/",
                {
                    "action": "delete_selected",
                    "_selected_action": str(self.order.pk),
                    "post": "yes",
                },
            )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Order.objects.filter(pk=self.order.pk).exists())
        self.assertFalse(PaymentProof.objects.filter(pk=self.proof.pk).exists())
        self.assertFalse(self.proof.image.storage.exists(proof_path))
        self.product.refresh_from_db()
        self.assertEqual(self.product.reserved_stock, 0)

    def test_owner_can_open_private_proof_and_reject_with_reason(self):
        proof_response = self.client.get(
            f"/admin/store/order/private-proof/{self.proof.pk}/"
        )
        self.assertEqual(proof_response.status_code, 200)
        self.assertIn("private, no-store", proof_response["Cache-Control"])
        proof_response.close()

        action_url = "/admin/store/order/"
        confirm_page = self.client.post(
            action_url,
            {
                "action": "reject_selected_orders",
                "_selected_action": str(self.order.pk),
            },
        )
        self.assertEqual(confirm_page.status_code, 200)
        self.assertContains(confirm_page, "Motivo del rechazo")

        result = self.client.post(
            action_url,
            {
                "action": "reject_selected_orders",
                "_selected_action": str(self.order.pk),
                "apply": "1",
                "rejection_reason": "No coincide el número de transacción.",
            },
        )
        self.assertEqual(result.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PAYMENT_REJECTED)
        self.assertEqual(
            self.order.payment_rejection_reason,
            "No coincide el número de transacción.",
        )

    def test_product_admin_selects_existing_category_and_image_url(self):
        category = Category.objects.create(name="Controles")
        response = self.client.get("/admin/store/product/add/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Controles")

        product_response = self.client.post(
            "/admin/store/product/add/",
            {
                "name": "Mando inalámbrico",
                "description": "Compatible con consola",
                "category": str(category.pk),
                "price_cup": "9500",
                "stock": "5",
                "reserved_stock": "0",
                "is_active": "on",
                "images-TOTAL_FORMS": "1",
                "images-INITIAL_FORMS": "0",
                "images-MIN_NUM_FORMS": "0",
                "images-MAX_NUM_FORMS": "1000",
                "images-0-image_url": "https://example.com/controller.png",
                "images-0-alt_text": "Mando inalámbrico",
                "images-0-sort_order": "0",
            },
        )
        self.assertEqual(product_response.status_code, 302)
        product = Product.objects.get(name="Mando inalámbrico")
        image = ProductImage.objects.get(product=product)
        self.assertEqual(image.image_url, "https://example.com/controller.png")

    def test_superuser_can_create_owner_account_safely_in_admin(self):
        response = self.client.post(
            "/admin/store/user/add/",
            {
                "email": "new-owner@example.com",
                "first_name": "Dueño",
                "last_name": "Nuevo",
                "phone": "+5355550001",
                "role": User.Role.OWNER,
                "email_verified": "on",
                "password1": "S3cure_Unique!Owner_Password_421",
                "password2": "S3cure_Unique!Owner_Password_421",
            },
        )
        self.assertEqual(response.status_code, 302)
        owner = User.objects.get(email="new-owner@example.com")
        self.assertTrue(owner.check_password("S3cure_Unique!Owner_Password_421"))
        self.assertTrue(owner.email_verified)
        self.assertTrue(owner.can_manage_store)
        self.assertFalse(owner.is_staff)


class OwnerApiTests(IsolatedMediaTestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            email="owner-api-customer@example.com",
            password="AValidStrongPass_987!",
            first_name="Cliente",
            last_name="Comprador",
            phone="+5355551234",
            email_verified=True,
        )
        self.owner = User.objects.create_user(
            email="store-owner@example.com",
            password="AValidStrongPass_987!",
            role=User.Role.OWNER,
            email_verified=True,
        )
        self.category = Category.objects.create(name="Disco de Ps5")
        self.product = Product.objects.create(
            name="Juego físico",
            category=self.category,
            price_cup=12000,
            stock=3,
        )
        self.client = APIClient()

    def test_customer_cannot_access_owner_endpoints(self):
        self.client.force_authenticate(self.customer)
        for url in (
            "/api/owner/products/",
            "/api/owner/categories/",
            "/api/owner/orders/",
            "/api/owner/settings/",
        ):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 403)

    def test_superuser_can_manage_store_without_owner_role(self):
        superuser = User.objects.create_superuser(
            email="store-superuser@example.com",
            password="AValidStrongPass_987!",
            phone="+5355550002",
        )
        self.assertEqual(superuser.role, User.Role.CUSTOMER)
        self.assertTrue(superuser.email_verified)
        self.client.force_authenticate(superuser)

        response = self.client.get("/api/owner/products/")
        self.assertEqual(response.status_code, 200)
        identity_response = self.client.get("/api/auth/me/")
        self.assertEqual(identity_response.data["role"], "superuser")
        self.assertTrue(identity_response.data["can_manage_store"])

    def test_owner_can_create_category_and_product_with_image_urls(self):
        self.client.force_authenticate(self.owner)
        category_response = self.client.post(
            "/api/owner/categories/",
            {"name": "Consolas", "is_active": True},
            format="json",
        )
        self.assertEqual(category_response.status_code, 201)

        product_response = self.client.post(
            "/api/owner/products/",
            {
                "name": "Consola de prueba",
                "description": "Descripción",
                "category": category_response.data["id"],
                "price_cup": 90000,
                "stock": 2,
                "is_active": True,
                "images": [{"image_url": "https://example.com/console.png"}],
            },
            format="json",
        )
        self.assertEqual(product_response.status_code, 201)
        self.assertEqual(product_response.data["category_name"], "Consolas")
        self.assertEqual(
            product_response.data["images"][0]["image_url"],
            "https://example.com/console.png",
        )

    def test_owner_can_review_order_and_approve_after_viewing_private_proof(self):
        ProductImage.objects.create(
            product=self.product,
            image_url="https://example.com/ordered-game.png",
            alt_text="Juego pedido",
        )
        order = create_order(
            user=self.customer,
            items=[{"product_id": self.product.pk, "quantity": 1}],
            payment_method=Order.PaymentMethod.BPA,
            transaction_number="BPA-98765",
        )
        proof = PaymentProof.objects.create(order=order, image=valid_png())
        Order.objects.filter(pk=order.pk).update(status=Order.Status.PROOF_SUBMITTED)
        self.client.force_authenticate(self.owner)

        list_response = self.client.get("/api/owner/orders/")
        self.assertEqual(list_response.status_code, 200)
        order_data = list_response.data[0]
        self.assertEqual(order_data["customer_name"], "Cliente Comprador")
        self.assertEqual(order_data["customer_email"], self.customer.email)
        self.assertEqual(order_data["customer_phone"], self.customer.phone)
        self.assertEqual(order_data["items"][0]["product_name"], self.product.name)
        self.assertEqual(order_data["items"][0]["category_name"], "Disco de Ps5")
        self.assertEqual(
            order_data["items"][0]["product_image_url"],
            "https://example.com/ordered-game.png",
        )

        proof_response = self.client.get(
            f"/api/orders/{order.pk}/proofs/{proof.pk}/"
        )
        self.assertEqual(proof_response.status_code, 200)
        proof_response.close()

        approval_response = self.client.post(
            f"/api/owner/orders/{order.pk}/approve/",
            {},
            format="json",
        )
        self.assertEqual(approval_response.status_code, 200)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 2)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CONFIRMED)

    def test_owner_can_reject_payment_proof_with_reason(self):
        order = create_order(
            user=self.customer,
            items=[{"product_id": self.product.pk, "quantity": 1}],
            payment_method=Order.PaymentMethod.BPA,
            transaction_number="BPA-98765",
        )
        PaymentProof.objects.create(order=order, image=valid_png())
        Order.objects.filter(pk=order.pk).update(status=Order.Status.PROOF_SUBMITTED)
        self.client.force_authenticate(self.owner)

        response = self.client.post(
            f"/api/owner/orders/{order.pk}/reject/",
            {"reason": "No se recibió la transferencia."},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAYMENT_REJECTED)
        self.assertEqual(order.payment_rejection_reason, "No se recibió la transferencia.")

    def test_owner_can_update_store_payment_and_contact_settings(self):
        self.client.force_authenticate(self.owner)
        response = self.client.patch(
            "/api/owner/settings/",
            {
                "whatsapp_number": "+5355550000",
                "bpa_card_number": "1111-2222-3333-4444",
                "zelle_account": "payments@example.com",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["whatsapp_number"], "+5355550000")
        self.assertEqual(response.data["bpa_card_number"], "1111-2222-3333-4444")
        self.assertEqual(response.data["zelle_account"], "payments@example.com")

    def test_owner_can_rename_or_delete_category_and_products_are_unassigned(self):
        self.client.force_authenticate(self.owner)
        rename_response = self.client.patch(
            f"/api/owner/categories/{self.category.pk}/",
            {"name": "Juegos físicos"},
            format="json",
        )
        self.assertEqual(rename_response.status_code, 200)
        self.assertEqual(rename_response.data["name"], "Juegos físicos")

        delete_response = self.client.delete(
            f"/api/owner/categories/{self.category.pk}/"
        )
        self.assertEqual(delete_response.status_code, 204)
        self.product.refresh_from_db()
        self.assertIsNone(self.product.category)

        public_product_response = self.client.get("/api/products/")
        self.assertEqual(public_product_response.data[0]["category"], "Sin categoría")
        self.assertFalse(public_product_response.data[0]["zelle_eligible"])

        product_update_response = self.client.patch(
            f"/api/owner/products/{self.product.pk}/",
            {"name": "Juego pendiente"},
            format="json",
        )
        self.assertEqual(product_update_response.status_code, 400)
        self.assertIn("category", product_update_response.data)
