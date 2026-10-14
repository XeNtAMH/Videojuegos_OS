import hashlib
import secrets
import uuid
from datetime import timedelta

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.validators import FileExtensionValidator, MinValueValidator, URLValidator
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("El correo electrónico es obligatorio.")
        user = self.model(email=self.normalize_email(email), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("email_verified", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("El administrador debe tener is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("El administrador debe tener is_superuser=True.")
        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    class Role(models.TextChoices):
        CUSTOMER = "customer", "Cliente"
        OWNER = "owner", "Dueño"

    username = None
    email = models.EmailField(unique=True)
    phone = models.CharField("celular", max_length=30)
    email_verified = models.BooleanField(default=False)
    role = models.CharField(
        max_length=12, choices=Role.choices, default=Role.CUSTOMER
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["phone", "first_name", "last_name"]
    objects = UserManager()

    def __str__(self):
        return self.get_full_name() or self.email

    @property
    def can_manage_store(self):
        return self.is_superuser or self.role == self.Role.OWNER


class EmailVerification(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    token_hash = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now=True)

    @classmethod
    def issue(cls, user):
        token = secrets.token_urlsafe(32)
        cls.objects.update_or_create(
            user=user,
            defaults={
                "token_hash": hashlib.sha256(token.encode()).hexdigest(),
                "expires_at": timezone.now() + timedelta(hours=24),
            },
        )
        return token


class Category(models.Model):
    name = models.CharField(max_length=80, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categorías"

    def __str__(self):
        return self.name


class Product(models.Model):
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    category = models.ForeignKey(
        Category,
        related_name="products",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    price_cup = models.PositiveIntegerField(
        validators=[MinValueValidator(1)], verbose_name="precio CUP"
    )
    stock = models.PositiveIntegerField(default=0)
    reserved_stock = models.PositiveIntegerField(default=0, editable=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category__name", "name"]

    @property
    def available_stock(self):
        return max(0, self.stock - self.reserved_stock)

    def __str__(self):
        return self.name


def validate_image_url(value):
    URLValidator(schemes=["http", "https"])(value)


def product_image_path(instance, filename):
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
    return f"products/{uuid.uuid4().hex}.{extension}"


class ProductImage(models.Model):
    product = models.ForeignKey(
        Product, related_name="images", on_delete=models.CASCADE
    )
    image_url = models.URLField(
        max_length=1000,
        blank=True,
        validators=[validate_image_url],
        verbose_name="enlace de la imagen",
    )
    image = models.ImageField(
        upload_to=product_image_path, blank=True, editable=False
    )
    alt_text = models.CharField(max_length=160, blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"Foto de {self.product.name}"


class StoreSettings(models.Model):
    store_name = models.CharField(max_length=120, default="Tienda Gamer Cuba")
    whatsapp_number = models.CharField(max_length=30, default="5350000000")
    bpa_card_number = models.CharField(
        max_length=19, default="0000-0000-0000-0000"
    )
    zelle_account = models.CharField(
        max_length=254, default="zelle@example.com"
    )
    bpa_instructions = models.TextField(blank=True)
    mobile_balance_instructions = models.TextField(blank=True)
    zelle_instructions = models.TextField(blank=True)
    pickup_instructions = models.TextField(
        default="La ubicación y hora de recogida se coordinan por WhatsApp."
    )
    returns_policy = models.TextField(
        default="No se aceptan cambios ni devoluciones."
    )

    def __str__(self):
        return self.store_name

    @classmethod
    def current(cls):
        settings, _ = cls.objects.get_or_create(pk=1)
        return settings


class Order(models.Model):
    class PaymentMethod(models.TextChoices):
        CASH = "cash", "Efectivo CUP"
        BPA = "bpa", "Transferencia BPA"
        MOBILE = "mobile", "Saldo móvil"
        ZELLE = "zelle", "Zelle"

    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente de pago/coordinación"
        PROOF_SUBMITTED = "proof_submitted", "Comprobante recibido"
        PAYMENT_REJECTED = "payment_rejected", "Comprobante rechazado"
        CONFIRMED = "confirmed", "Confirmado"
        PREPARING = "preparing", "Preparando"
        READY = "ready", "Listo para recoger"
        COMPLETED = "completed", "Completado"
        CANCELLED = "cancelled", "Cancelado"
        EXPIRED = "expired", "Reserva vencida"

    user = models.ForeignKey(User, related_name="orders", on_delete=models.PROTECT)
    payment_method = models.CharField(max_length=12, choices=PaymentMethod.choices)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    total_cup = models.PositiveIntegerField()
    transaction_number = models.CharField(max_length=100, blank=True)
    customer_note = models.TextField(blank=True)
    payment_rejection_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    reservation_expires_at = models.DateTimeField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Pedido #{self.pk} - {self.user}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    product_name = models.CharField(max_length=160)
    category_name = models.CharField(max_length=80, blank=True)
    product_image_url = models.URLField(max_length=1000, blank=True)
    unit_price_cup = models.PositiveIntegerField()
    quantity = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])

    @property
    def line_total_cup(self):
        return self.unit_price_cup * self.quantity

    def __str__(self):
        return f"{self.quantity} x {self.product_name}"


def proof_image_path(instance, filename):
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
    return f"private/payment-proofs/{instance.order_id}/{uuid.uuid4().hex}.{extension}"


class PaymentProof(models.Model):
    order = models.ForeignKey(Order, related_name="proofs", on_delete=models.CASCADE)
    image = models.ImageField(
        upload_to=proof_image_path,
        validators=[FileExtensionValidator(["jpg", "jpeg", "png", "webp"])],
    )
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"Comprobante de pedido #{self.order_id}"
