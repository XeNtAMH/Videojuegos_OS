from django.core.management.base import BaseCommand

from backend.store.services import expire_stale_reservations


class Command(BaseCommand):
    help = "Libera el inventario de pedidos cuya reserva de 24 horas venció."

    def handle(self, *args, **options):
        expired_count = expire_stale_reservations()
        self.stdout.write(f"Reservas vencidas y liberadas: {expired_count}")
