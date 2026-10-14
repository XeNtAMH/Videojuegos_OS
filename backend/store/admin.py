import mimetypes

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import UserChangeForm
from django.contrib.auth.password_validation import validate_password
from django.contrib import messages
from django import forms
from django.http import FileResponse
from django.template.response import TemplateResponse
from django.urls import path
from django.utils.html import format_html
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import (
    EmailVerification,
    Category,
    Order,
    OrderItem,
    PaymentProof,
    Product,
    ProductImage,
    StoreSettings,
    User,
)
from .services import confirm_order, cancel_order, expire_stale_reservations

admin.site.site_header = "Gestión de Tienda Gamer"
admin.site.site_title = "Tienda Gamer"
admin.site.index_title = "Inventario y pedidos"


class StoreUserCreationForm(forms.ModelForm):
    password1 = forms.CharField(label="Contraseña", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirmar contraseña", widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ("email", "first_name", "last_name", "phone", "role", "email_verified")

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Las contraseñas no coinciden.")
        validate_password(password2, self.instance)
        return password2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
            self.save_m2m()
        return user


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    fields = ("image_url", "alt_text", "sort_order", "preview")
    readonly_fields = ("preview",)
    extra = 1

    @admin.display(description="Vista previa")
    def preview(self, obj):
        if not obj.pk:
            return "Guarda el producto para ver la imagen."
        url = obj.image_url
        if not url and obj.image:
            url = obj.image.url
        if not url:
            return "Añade un enlace de imagen."
        return format_html(
            '<a href="{}" target="_blank" rel="noopener noreferrer">'
            '<img src="{}" alt="Vista previa" style="max-height:80px;max-width:120px">'
            "</a>",
            url,
            url,
        )


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)
    ordering = ("name",)

class ProductAdminForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = "__all__"

    def clean_stock(self):
        stock = self.cleaned_data["stock"]
        if self.instance.pk and stock < self.instance.reserved_stock:
            raise forms.ValidationError(
                f"No puede ser menor que las {self.instance.reserved_stock} unidades reservadas."
            )
        return stock

    def clean_category(self):
        category = self.cleaned_data["category"]
        if not category or not category.is_active:
            raise forms.ValidationError(
                "La categoría está inactiva. Selecciona una categoría activa."
            )
        return category


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    form = ProductAdminForm
    list_display = (
        "name",
        "category",
        "price_cup",
        "stock",
        "reserved_stock",
        "available_stock_display",
        "is_active",
    )
    list_filter = ("category", "is_active")
    search_fields = ("name", "description")
    inlines = [ProductImageInline]

    @admin.display(description="Disponible")
    def available_stock_display(self, obj):
        return obj.available_stock


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    readonly_fields = (
        "product",
        "product_name",
        "unit_price_cup",
        "quantity",
        "line_total",
    )

    @admin.display(description="Subtotal CUP")
    def line_total(self, obj):
        return f"{obj.line_total_cup:,}"


class PaymentProofInline(admin.TabularInline):
    model = PaymentProof
    extra = 0
    can_delete = False
    fields = ("submitted_at", "private_image")
    readonly_fields = ("submitted_at", "private_image")

    @admin.display(description="Captura")
    def private_image(self, obj):
        return format_html(
            '<a href="/admin/store/order/private-proof/{}/" target="_blank">Abrir comprobante</a>',
            obj.pk,
        )


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "payment_method",
        "status",
        "total_cup",
        "created_at",
        "reservation_expires_at",
    )
    list_filter = ("status", "payment_method", "created_at")
    search_fields = ("=id", "user__email", "user__first_name", "user__last_name")
    readonly_fields = (
        "user",
        "payment_method",
        "status",
        "total_cup",
        "transaction_number",
        "customer_note",
        "created_at",
        "reservation_expires_at",
        "updated_at",
    )
    fields = (
        "user",
        "payment_method",
        "status",
        "total_cup",
        "transaction_number",
        "customer_note",
        "payment_rejection_reason",
        "created_at",
        "reservation_expires_at",
        "updated_at",
    )
    inlines = [OrderItemInline, PaymentProofInline]
    actions = (
        "confirm_selected_orders",
        "reject_selected_orders",
        "cancel_selected_orders",
        "mark_preparing",
        "mark_ready",
        "mark_completed",
    )

    def get_queryset(self, request):
        expire_stale_reservations()
        return super().get_queryset(request)

    def get_urls(self):
        return [
            path(
                "private-proof/<int:proof_id>/",
                self.admin_site.admin_view(self.proof_file),
                name="private-payment-proof",
            ),
            *super().get_urls(),
        ]

    def proof_file(self, request, proof_id):
        proof = PaymentProof.objects.get(pk=proof_id)
        response = FileResponse(
            proof.image.open("rb"),
            content_type=mimetypes.guess_type(proof.image.name)[0]
            or "application/octet-stream",
        )
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response

    @admin.action(description="Confirmar pedidos seleccionados (descuenta inventario)")
    def confirm_selected_orders(self, request, queryset):
        confirmed = 0
        failures = 0
        for order in queryset:
            try:
                confirm_order(order.pk)
                confirmed += 1
            except ValidationError as error:
                failures += 1
                self.message_user(
                    request,
                    f"Pedido #{order.pk}: {'; '.join(error.messages)}",
                    messages.ERROR,
                )
        if confirmed:
            self.message_user(request, f"{confirmed} pedido(s) confirmado(s).")
        if failures:
            self.message_user(request, f"{failures} pedido(s) no pudieron confirmarse.", messages.ERROR)

    @admin.action(description="Cancelar pedidos seleccionados y liberar reservas")
    def cancel_selected_orders(self, request, queryset):
        cancelled = 0
        failures = 0
        for order in queryset:
            try:
                cancel_order(order)
                cancelled += 1
            except ValidationError as error:
                failures += 1
                self.message_user(
                    request,
                    f"Pedido #{order.pk}: {'; '.join(error.messages)}",
                    messages.ERROR,
                )
        if cancelled:
            self.message_user(request, f"{cancelled} pedido(s) cancelado(s).")
        if failures:
            self.message_user(request, f"{failures} pedido(s) no pudieron cancelarse.", messages.ERROR)

    @admin.action(description="Rechazar comprobante(s) y permitir reenviar")
    def reject_selected_orders(self, request, queryset):
        if "apply" in request.POST:
            reason = request.POST.get("rejection_reason", "").strip()
            if not reason:
                self.message_user(
                    request, "Debes indicar el motivo del rechazo.", messages.ERROR
                )
                return None
            updated = queryset.filter(
                payment_method__in=[
                    Order.PaymentMethod.BPA,
                    Order.PaymentMethod.MOBILE,
                    Order.PaymentMethod.ZELLE,
                ],
                status__in=[
                    Order.Status.PENDING,
                    Order.Status.PROOF_SUBMITTED,
                    Order.Status.PAYMENT_REJECTED,
                ],
            ).update(
                status=Order.Status.PAYMENT_REJECTED,
                payment_rejection_reason=reason,
                updated_at=timezone.now(),
            )
            self.message_user(
                request,
                f"{updated} comprobante(s) rechazado(s). El cliente puede enviar otro.",
            )
            return None
        return TemplateResponse(
            request,
            "admin/reject_orders.html",
            {
                **self.admin_site.each_context(request),
                "opts": self.model._meta,
                "orders": queryset,
                "action_checkbox_name": admin.helpers.ACTION_CHECKBOX_NAME,
                "action_name": "reject_selected_orders",
            },
        )

    @admin.action(description="Marcar pedidos confirmados como preparando")
    def mark_preparing(self, request, queryset):
        count = queryset.filter(status=Order.Status.CONFIRMED).update(
            status=Order.Status.PREPARING, updated_at=timezone.now()
        )
        self.message_user(request, f"{count} pedido(s) en preparación.")

    @admin.action(description="Marcar pedidos en preparación como listos para recoger")
    def mark_ready(self, request, queryset):
        count = queryset.filter(status=Order.Status.PREPARING).update(
            status=Order.Status.READY, updated_at=timezone.now()
        )
        self.message_user(request, f"{count} pedido(s) listo(s) para recoger.")

    @admin.action(description="Marcar pedidos listos como completados")
    def mark_completed(self, request, queryset):
        count = queryset.filter(status=Order.Status.READY).update(
            status=Order.Status.COMPLETED, updated_at=timezone.now()
        )
        self.message_user(request, f"{count} pedido(s) completado(s).")


@admin.register(StoreSettings)
class StoreSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "store_name",
        "whatsapp_number",
        "bpa_card_number",
        "zelle_account",
    )

    def has_add_permission(self, request):
        return not StoreSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    add_form = StoreUserCreationForm
    form = UserChangeForm
    ordering = ("email",)
    list_display = (
        "email",
        "first_name",
        "last_name",
        "phone",
        "role",
        "email_verified",
        "is_staff",
    )
    search_fields = ("email", "first_name", "last_name", "phone")
    list_filter = ("role", "email_verified", "is_staff", "is_superuser")
    list_editable = ("role",)
    search_fields = ("email", "first_name", "last_name", "phone")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Datos personales", {"fields": ("first_name", "last_name", "phone")}),
        (
            "Permisos y rol",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "role",
                    "email_verified",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Fechas", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "first_name",
                    "last_name",
                    "phone",
                    "password1",
                    "password2",
                    "role",
                    "email_verified",
                ),
            },
        ),
    )


@admin.register(EmailVerification)
class EmailVerificationAdmin(admin.ModelAdmin):
    list_display = ("user", "expires_at", "created_at")
    readonly_fields = ("user", "token_hash", "expires_at", "created_at")
