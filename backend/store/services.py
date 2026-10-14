from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import Order, OrderItem, Product

RESERVATION_HOURS = 24
ZELLE_CATEGORIES = {"disco de ps5", "consola"}
ACTIVE_RESERVATION_STATUSES = (
    Order.Status.PENDING,
    Order.Status.PROOF_SUBMITTED,
    Order.Status.PAYMENT_REJECTED,
)


def expire_stale_reservations():
    stale_orders = Order.objects.filter(
        status__in=ACTIVE_RESERVATION_STATUSES,
        reservation_expires_at__lte=timezone.now(),
    )
    expired_count = 0
    for order_id in stale_orders.values_list("id", flat=True).iterator():
        with transaction.atomic():
            order = Order.objects.select_for_update().filter(pk=order_id).first()
            if (
                order is None
                or order.status not in ACTIVE_RESERVATION_STATUSES
                or order.reservation_expires_at > timezone.now()
            ):
                continue
            items = list(order.items.select_related("product"))
            for item in items:
                product = Product.objects.select_for_update().get(pk=item.product_id)
                product.reserved_stock = max(
                    0, product.reserved_stock - item.quantity
                )
                product.save(update_fields=["reserved_stock"])
            order.status = Order.Status.EXPIRED
            order.save(update_fields=["status", "updated_at"])
            expired_count += 1
    return expired_count


@transaction.atomic
def create_order(*, user, items, payment_method, transaction_number="", customer_note=""):
    if not items:
        raise ValidationError({"items": "El carrito está vacío."})
    if payment_method not in Order.PaymentMethod.values:
        raise ValidationError({"payment_method": "Selecciona un método válido."})
    transaction_number = str(transaction_number or "").strip()
    if (
        payment_method in (Order.PaymentMethod.BPA, Order.PaymentMethod.ZELLE)
        and not transaction_number
    ):
        raise ValidationError(
            {"transaction_number": "El número de transacción es obligatorio para BPA y Zelle."}
        )

    quantities = {}
    for row in items:
        try:
            product_id = int(row["product_id"])
            quantity = int(row["quantity"])
        except (KeyError, TypeError, ValueError):
            raise ValidationError({"items": "Cada artículo requiere id y cantidad válida."})
        if quantity < 1 or quantity > 50:
            raise ValidationError({"items": "La cantidad debe estar entre 1 y 50."})
        quantities[product_id] = quantities.get(product_id, 0) + quantity
    if any(quantity > 50 for quantity in quantities.values()):
        raise ValidationError({"items": "La cantidad máxima por artículo es 50."})

    products = {
        product.pk: product
        for product in Product.objects.select_for_update()
        .filter(pk__in=quantities, is_active=True)
        .order_by("pk")
    }
    if len(products) != len(quantities):
        raise ValidationError({"items": "Uno o más artículos ya no están disponibles."})
    zelle_is_eligible = False
    total = 0
    for product_id, quantity in quantities.items():
        product = products[product_id]
        if product.available_stock < quantity:
            raise ValidationError(
                {"items": f"No hay suficiente inventario de {product.name}."}
            )
        zelle_is_eligible = zelle_is_eligible or (
            product.category_id
            and product.category.name.strip().casefold() in ZELLE_CATEGORIES
        )
        total += product.price_cup * quantity
    if payment_method == Order.PaymentMethod.ZELLE and not zelle_is_eligible:
        raise ValidationError(
            {"payment_method": "Zelle solo está disponible si el carrito contiene una consola o disco de PS5 elegible."}
        )

    order = Order.objects.create(
        user=user,
        payment_method=payment_method,
        total_cup=total,
        transaction_number=transaction_number[:100],
        customer_note=customer_note.strip(),
        reservation_expires_at=timezone.now() + timedelta(hours=RESERVATION_HOURS),
    )
    for product_id, quantity in quantities.items():
        product = products[product_id]
        product.reserved_stock += quantity
        product.save(update_fields=["reserved_stock"])
        product_image = product.images.order_by("sort_order", "id").first()
        product_image_url = ""
        if product_image:
            product_image_url = product_image.image_url or (
                product_image.image.url if product_image.image else ""
            )
        OrderItem.objects.create(
            order=order,
            product=product,
            product_name=product.name,
            category_name=product.category.name if product.category_id else "Sin categoría",
            product_image_url=product_image_url,
            unit_price_cup=product.price_cup,
            quantity=quantity,
        )
    return order


@transaction.atomic
def confirm_order(order_id):
    order = Order.objects.select_for_update().get(pk=order_id)
    if order.status not in ACTIVE_RESERVATION_STATUSES:
        raise ValidationError({"status": "Este pedido no se puede confirmar en su estado actual."})
    if (
        order.payment_method in (Order.PaymentMethod.BPA, Order.PaymentMethod.ZELLE)
        and not order.transaction_number.strip()
    ):
        raise ValidationError(
            {"transaction_number": "El pedido no tiene número de transacción."}
        )
    if (
        order.payment_method != Order.PaymentMethod.CASH
        and order.status != Order.Status.PROOF_SUBMITTED
    ):
        raise ValidationError(
            {"proof": "Revisa el comprobante más reciente antes de confirmar el pago."}
        )
    if order.reservation_expires_at <= timezone.now():
        raise ValidationError({"status": "La reserva venció; no se puede confirmar."})
    for item in order.items.all():
        product = Product.objects.select_for_update().get(pk=item.product_id)
        if product.stock < item.quantity or product.reserved_stock < item.quantity:
            raise ValidationError({"inventory": f"Inventario inconsistente para {product.name}."})
        product.stock -= item.quantity
        product.reserved_stock -= item.quantity
        product.save(update_fields=["stock", "reserved_stock"])
    order.status = Order.Status.CONFIRMED
    order.payment_rejection_reason = ""
    order.save(update_fields=["status", "payment_rejection_reason", "updated_at"])
    return order


@transaction.atomic
def cancel_order(order, status=Order.Status.CANCELLED):
    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.status not in ACTIVE_RESERVATION_STATUSES:
        raise ValidationError({"status": "Este pedido ya no se puede cancelar."})
    for item in order.items.all():
        product = Product.objects.select_for_update().get(pk=item.product_id)
        product.reserved_stock = max(0, product.reserved_stock - item.quantity)
        product.save(update_fields=["reserved_stock"])
    order.status = status
    order.save(update_fields=["status", "updated_at"])
    return order
