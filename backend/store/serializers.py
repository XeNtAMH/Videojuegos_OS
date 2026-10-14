from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.db import transaction

from .models import (
    Category,
    EmailVerification,
    Order,
    OrderItem,
    PaymentProof,
    Product,
    ProductImage,
    StoreSettings,
    User,
)


class RegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)

    class Meta:
        model = User
        fields = ("email", "password", "first_name", "last_name", "phone")

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User.objects.create_user(password=password, **validated_data)
        return user


class EmailLoginSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        if not self.user.email_verified:
            raise serializers.ValidationError(
                {"detail": "Verifica tu correo electrónico antes de iniciar sesión."}
            )
        return data


class ProductImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields = ("id", "image_url", "alt_text")

    def get_image_url(self, obj):
        if obj.image_url:
            return obj.image_url
        if obj.image:
            request = self.context.get("request")
            url = obj.image.url
            return request.build_absolute_uri(url) if request else url
        return ""


class ProductSerializer(serializers.ModelSerializer):
    images = ProductImageSerializer(many=True, read_only=True)
    available_stock = serializers.IntegerField(read_only=True)
    category = serializers.SerializerMethodField()
    zelle_eligible = serializers.SerializerMethodField()

    def get_category(self, obj):
        return obj.category.name if obj.category_id else "Sin categoría"

    def get_zelle_eligible(self, obj):
        return bool(
            obj.category_id
            and obj.category.name.strip().casefold() in {"disco de ps5", "consola"}
        )

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "description",
            "category",
            "price_cup",
            "available_stock",
            "zelle_eligible",
            "images",
        )


class ProductImageInputSerializer(serializers.Serializer):
    image_url = serializers.URLField(max_length=1000, required=False, allow_blank=True)
    alt_text = serializers.CharField(max_length=160, required=False, allow_blank=True)
    sort_order = serializers.IntegerField(min_value=0, max_value=32767, required=False)

    def validate(self, attrs):
        if not attrs.get("image_url", "").strip():
            raise serializers.ValidationError(
                {"image_url": "Escribe un enlace para cada imagen del producto."}
            )
        return attrs


class ManagedProductSerializer(serializers.ModelSerializer):
    category = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.filter(is_active=True),
        required=False,
        allow_null=True,
    )
    images = ProductImageInputSerializer(many=True, required=False)
    available_stock = serializers.IntegerField(read_only=True)
    category_name = serializers.SerializerMethodField()

    def get_category_name(self, obj):
        return obj.category.name if obj.category_id else "Sin categoría"

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "description",
            "category",
            "category_name",
            "price_cup",
            "stock",
            "reserved_stock",
            "available_stock",
            "is_active",
            "images",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "reserved_stock", "available_stock", "created_at", "updated_at")

    def validate(self, attrs):
        category = attrs.get(
            "category",
            self.instance.category if self.instance and self.instance.category_id else None,
        )
        if category is None:
            raise serializers.ValidationError(
                {"category": "Selecciona una categoría activa para el producto."}
            )
        return attrs

    def validate_stock(self, value):
        if self.instance and value < self.instance.reserved_stock:
            raise serializers.ValidationError(
                f"No puede ser menor que las {self.instance.reserved_stock} unidades reservadas."
            )
        return value

    @transaction.atomic
    def create(self, validated_data):
        images = validated_data.pop("images", [])
        product = Product.objects.create(**validated_data)
        self._save_images(product, images)
        return product

    @transaction.atomic
    def update(self, instance, validated_data):
        images = validated_data.pop("images", None)
        product = super().update(instance, validated_data)
        if images is not None:
            product.images.all().delete()
            self._save_images(product, images)
        return product

    @staticmethod
    def _save_images(product, images):
        for index, image in enumerate(images):
            image["sort_order"] = image.get("sort_order", index)
            ProductImage.objects.create(product=product, **image)


class ManagedCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("id", "name", "is_active")


class StoreSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoreSettings
        fields = (
            "store_name",
            "whatsapp_number",
            "bpa_card_number",
            "zelle_account",
            "bpa_instructions",
            "mobile_balance_instructions",
            "zelle_instructions",
            "pickup_instructions",
            "returns_policy",
        )


class ManagedStoreSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoreSettings
        fields = (
            "store_name",
            "whatsapp_number",
            "bpa_card_number",
            "zelle_account",
            "bpa_instructions",
            "mobile_balance_instructions",
            "zelle_instructions",
            "pickup_instructions",
            "returns_policy",
        )


class OrderItemSerializer(serializers.ModelSerializer):
    line_total_cup = serializers.IntegerField(read_only=True)
    category_name = serializers.SerializerMethodField()
    product_image_url = serializers.SerializerMethodField()

    def get_category_name(self, obj):
        if obj.category_name:
            return obj.category_name
        return obj.product.category.name if obj.product.category_id else "Sin categoría"

    def get_product_image_url(self, obj):
        if obj.product_image_url:
            return obj.product_image_url
        image = obj.product.images.order_by("sort_order", "id").first()
        if not image:
            return ""
        return image.image_url or (image.image.url if image.image else "")

    class Meta:
        model = OrderItem
        fields = (
            "product_name",
            "category_name",
            "product_image_url",
            "unit_price_cup",
            "quantity",
            "line_total_cup",
        )


class PaymentProofSerializer(serializers.ModelSerializer):
    proof_url = serializers.SerializerMethodField()

    class Meta:
        model = PaymentProof
        fields = ("id", "proof_url", "submitted_at")

    def get_proof_url(self, obj):
        request = self.context.get("request")
        url = f"/api/orders/{obj.order_id}/proofs/{obj.pk}/"
        return request.build_absolute_uri(url) if request else url


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    proofs = PaymentProofSerializer(many=True, read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    payment_method_label = serializers.CharField(
        source="get_payment_method_display", read_only=True
    )

    class Meta:
        model = Order
        fields = (
            "id",
            "items",
            "payment_method",
            "payment_method_label",
            "status",
            "status_label",
            "total_cup",
            "transaction_number",
            "customer_note",
            "payment_rejection_reason",
            "created_at",
            "reservation_expires_at",
            "proofs",
        )
        read_only_fields = fields


class ManagedOrderSerializer(OrderSerializer):
    customer_name = serializers.CharField(source="user.get_full_name", read_only=True)
    customer_email = serializers.EmailField(source="user.email", read_only=True)
    customer_phone = serializers.CharField(source="user.phone", read_only=True)

    class Meta(OrderSerializer.Meta):
        fields = OrderSerializer.Meta.fields + (
            "customer_name",
            "customer_email",
            "customer_phone",
        )
