# Tienda Gamer Cuba

Tienda online MVP con React/Vite y Django REST Framework. La interfaz y los mensajes están en español; los precios se publican en CUP.

## Reglas implementadas

- Para comprar se necesita una cuenta verificada por correo.
- Iniciar sesión solo pide correo y contraseña. Hay que iniciar sesión para agregar productos al carrito o crear pedidos; al registrarse sí se solicitan nombre, apellidos, celular, correo y contraseña.
- Los pagos disponibles son efectivo CUP, transferencia BPA y saldo móvil. Zelle se habilita si el carrito contiene al menos un artículo de las categorías «Consola» o «Disco de Ps5»; su importe se coordina por WhatsApp.
- Para crear cualquier pedido con pago electrónico (BPA, saldo móvil o Zelle) se exige adjuntar la captura JPG, PNG o WEBP de hasta 5 MB en el mismo envío del pedido. Efectivo no requiere captura. BPA y Zelle requieren número de transacción. El dueño revisa y confirma manualmente desde el panel.
- El dueño puede renombrar o eliminar categorías desde el panel. Al eliminar una categoría, los productos permanecen en el inventario sin categoría y deben reasignarse a una categoría activa antes de poder editarse.
- Al crear un pedido se reserva el inventario durante 24 horas. La confirmación convierte la reserva en venta; cancelación o vencimiento liberan el stock.
- La recogida se coordina caso por caso por WhatsApp. Las capturas de pago se almacenan sin URL pública y solo son accesibles para el cliente del pedido y el personal administrador.
- Cambios y devoluciones: no aceptados, según la política inicial acordada para el MVP.

## Requisitos

- Python 3.10 o posterior
- Node.js 18 o posterior y npm

## Ejecutar localmente en Windows

En una terminal de PowerShell, desde la carpeta del proyecto:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py makemigrations store
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

En otra terminal:

```powershell
cd frontend
npm install
npm run dev
```

Si la API se ejecuta en otra dirección, define `VITE_API_URL` en `frontend/.env.local` (por ejemplo `VITE_API_URL=http://localhost:8000/api`).

Abre `http://localhost:5173`. El panel de gestión está en `http://localhost:8000/admin/` y requiere iniciar sesión con la cuenta de superusuario; el enlace de administración no se muestra a los clientes. Crea las categorías desde Categorías y selecciónalas al crear cada producto. En Fotos del producto, pega un enlace HTTP/HTTPS a la imagen y agrega texto alternativo si lo deseas. Configura el nombre de tienda, WhatsApp, número de tarjeta BPA, cuenta Zelle, instrucciones y datos de recogida en Configuración de tienda. Los datos de pago y WhatsApp nuevos tienen valores ficticios de ejemplo; cámbialos por los reales antes de aceptar pedidos.

Las rutas del sitio son `/home`, `/login`, `/register`, `/cart`, `/orders`, `/product/<id>` y `/owner`; la navegación del navegador Atrás/Adelante cambia de página dentro de la tienda.

### Roles y panel del negocio

Hay tres perfiles: cliente, dueño y superusuario. El superusuario se crea con `createsuperuser` y puede gestionar la tienda desde `/owner` o administrar cuentas desde `/admin/`. Para dar acceso al dueño, el superusuario puede crear su usuario desde **Autenticación y autorización → Usuarios** en `/admin/`, asignarle el rol **Dueño** y marcar el correo como verificado. También puede promover una cuenta de cliente ya verificada. El dueño inicia sesión por `/login` y será dirigido al panel `/owner`, donde gestiona categorías, productos, imágenes por enlace, inventario, pedidos, comprobantes y datos de pago/contacto. Los clientes no pueden acceder a las API de gestión.

### Correo de verificación

El proyecto usa Brevo por SMTP de forma predeterminada; no cambia silenciosamente al modo consola. El servidor, puerto, login y remitente predeterminados son `smtp-relay.brevo.com`, `587`, `be14bc001@smtp-brevo.com` y `Tienda Gamer <pedroglzzz08@gmail.com>`. El remitente debe estar verificado en Brevo. No guardes el password SMTP en el código ni en el repositorio. Para usarlo localmente sin escribirlo en el historial de comandos, abre una terminal PowerShell en la carpeta del proyecto, detén cualquier servidor Django anterior (`Ctrl+C`), pega este bloque y escribe la clave cuando PowerShell la solicite:

```powershell
$securePassword = Read-Host "Pega la clave SMTP de Brevo" -AsSecureString
$passwordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
try {
    $env:EMAIL_HOST_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPointer)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPointer)
}
.\.venv\Scripts\python.exe manage.py runserver
```

Mantén Django ejecutándose en esa misma ventana de PowerShell: la clave se configura solo para ese proceso/terminal. Si cierras la ventana, repite el bloque. Después de crear una cuenta, el cliente puede solicitar otro enlace desde la pestaña **Crear cuenta**. El reenvío tiene un intervalo mínimo de dos minutos. En despliegues, configura `EMAIL_HOST_PASSWORD` como secreto del servidor.

En el entorno web local, si el servidor no tiene la clave, el registro y el reenvío ahora mostrarán un error explícito de configuración en lugar de confirmar el registro usando un enlace de consola. Si Brevo rechaza la clave, falla la conexión o el remitente no está permitido, la respuesta indicará que el envío falló; el registro no se completará y podrás volver a intentarlo cuando se corrija la configuración. El modo consola solo se activa si se configura explícitamente `DJANGO_EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend`.

### Diagnóstico de errores de correo

Si la web indica que Brevo no pudo enviar el mensaje, revisa la terminal donde corre Django: ahora registra la causa SMTP concreta (por ejemplo, autenticación rechazada, remitente no autorizado o conexión fallida). No compartas credenciales ni pegues aquí la clave. Confirma que estás usando la **clave SMTP** vigente de Brevo (no la API key), que `EMAIL_HOST_USER` es el login SMTP, que el remitente coincide exactamente con el verificado en Brevo y que la terminal del servidor se inició después de establecer `EMAIL_HOST_PASSWORD`. Tras corregirlo, vuelve a iniciar Django y solicita el reenvío del enlace.

## Configuración de despliegue

Antes de publicar:

- Define `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=0`, `DJANGO_ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS` y `FRONTEND_URL`.
- Configura correo SMTP; verifica el proceso de verificación de cuentas y la entrega de mensajes.
- El MVP viene configurado con SQLite; adapta `DATABASES` a una base de datos administrada antes de alojarlo en producción.
- Configura almacenamiento durable para fotos de productos y almacenamiento privado para comprobantes. No expongas `MEDIA_ROOT` ni la carpeta `private/payment-proofs` como contenido estático.
- Configura el servidor web para servir la aplicación React y devolver su `index.html` para rutas como `/login`, `/register`, `/cart` y `/orders` (fallback de SPA).
- Sirve HTTPS y define copias de seguridad y retención/borrado de comprobantes conforme a las reglas aplicables.

El stock reservado vencido se libera al consultar productos/pedidos y antes de aceptar nuevas compras. En producción, configura una tarea programada (por ejemplo, una vez por minuto) para ejecutar `python manage.py expire_orders` y liberar reservas puntualmente incluso cuando no haya visitantes.
