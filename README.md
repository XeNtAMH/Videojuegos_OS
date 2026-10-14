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

En el admin, el superusuario puede usar **Agregar pedido** para registrar una compra hecha por un cliente verificado. Debe seleccionar artículos y cantidades; el inventario se reserva como en un pedido normal. Los pagos electrónicos requieren captura; BPA y Zelle también requieren número de transacción. Para borrar pedidos, selecciónalos en la lista y elige **Eliminar pedidos seleccionados**; el admin pide confirmación, libera reservas activas y elimina los archivos de comprobante asociados. Los pedidos confirmados/completados no reponen automáticamente unidades ya descontadas del inventario.

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

La configuración del repositorio está preparada para este esquema gratuito: **React en Cloudflare Pages, Django en Render Free, PostgreSQL y almacenamiento privado de comprobantes en Supabase Free**. Los proveedores pueden cambiar sus límites y disponibilidad; consulta las restricciones actuales de cada plan antes de publicar. Render Free duerme servicios inactivos y pierde su disco local en reinicios, así que SQLite y `MEDIA_ROOT` local no se usan como almacenamiento de producción.

### 1. Preparar Supabase

1. En Supabase crea un proyecto en una región cercana a Render (por ejemplo, US East). Guarda la contraseña de PostgreSQL en un gestor seguro.
2. En **Connect**, copia la URI de **Session pooler**, que es compatible con Render por IPv4. En Render se configurará como `DATABASE_URL`. Sustituye el marcador de contraseña por la real; si contiene caracteres especiales, URL-codifícala. No publiques ni envíes esa URI.
3. Crea un bucket privado llamado `payment-proofs`.
4. En Storage, habilita la compatibilidad S3 y genera credenciales S3 de servidor. Copia el endpoint y región que presenta Supabase. Configúralos en Render como `SUPABASE_S3_ENDPOINT_URL`, `SUPABASE_S3_REGION`, `SUPABASE_S3_ACCESS_KEY_ID`, `SUPABASE_S3_SECRET_ACCESS_KEY` y `SUPABASE_STORAGE_BUCKET=payment-proofs`. Estas claves permiten acceso amplio al almacenamiento: guárdalas solo como secretos del servicio, nunca en React, GitHub o este chat.
5. La cuota gratuita de Storage es limitada; vigila el uso porque las capturas de pago ocupan espacio.

### 2. Publicar el backend Django en Render

1. En Render elige **New → Blueprint** y conecta `XeNtAMH/Videojuegos_OS`, rama `main`. Render leerá [`render.yaml`](./render.yaml) y configurará el servicio web gratuito. El archivo crea la API `videojuegos-os-api.onrender.com`, aplica migraciones e instala Gunicorn/WhiteNoise.
2. En la configuración del servicio, completa las variables marcadas como secretas:
   - `DATABASE_URL`: URI de Supabase **Session pooler**.
   - `BREVO_API_KEY`: crea una clave API v3 en Brevo (no es la contraseña SMTP ni la clave SMTP). El servicio usará la API HTTPS de Brevo, porque Render Free bloquea el SMTP saliente en el puerto 587.
   - Las cinco variables `SUPABASE_S3_*`/`SUPABASE_STORAGE_BUCKET` de la sección anterior. Son obligatorias en producción: si faltan, Django ya no arrancará usando accidentalmente el disco efímero de Render.
3. Conserva `DJANGO_SECRET_KEY` generada por Render y `DJANGO_DEBUG=0`. Cuando Cloudflare dé la URL final de Pages, establece `FRONTEND_URL` y `CORS_ALLOWED_ORIGINS` con ese origen exacto, por ejemplo `https://nombre.pages.dev` (sin ruta ni barra final).
4. Espera que el despliegue termine. Revisa **Logs** si falla. La dirección de comprobación de salud será `https://videojuegos-os-api.onrender.com/api/store-settings/`.
5. Espera a que los Logs confirmen que Render terminó `migrate`. Para crear el superusuario sin acceso al Shell de Render, ejecuta el comando desde tu computadora conectado temporalmente a la base de Supabase:

   ```powershell
   $secureDatabaseUrl = Read-Host "Pega DATABASE_URL de Supabase (Session pooler)" -AsSecureString
   $databaseUrlPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureDatabaseUrl)
   $previousDatabaseUrl = $env:DATABASE_URL
   $previousDebug = $env:DJANGO_DEBUG
   $previousSecretKey = $env:DJANGO_SECRET_KEY
   try {
       $env:DATABASE_URL = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($databaseUrlPointer)
       $env:DJANGO_DEBUG = "0"
       $env:DJANGO_SECRET_KEY = "temporary-cli-" + [guid]::NewGuid().ToString("N")
       .\.venv\Scripts\python.exe manage.py createsuperuser
   } finally {
       [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($databaseUrlPointer)
       if ($null -eq $previousDatabaseUrl) { Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue } else { $env:DATABASE_URL = $previousDatabaseUrl }
       if ($null -eq $previousDebug) { Remove-Item Env:DJANGO_DEBUG -ErrorAction SilentlyContinue } else { $env:DJANGO_DEBUG = $previousDebug }
       if ($null -eq $previousSecretKey) { Remove-Item Env:DJANGO_SECRET_KEY -ErrorAction SilentlyContinue } else { $env:DJANGO_SECRET_KEY = $previousSecretKey }
   }
   ```

   Ejecuta el bloque desde la carpeta del proyecto, con el entorno virtual y dependencias instalados. `DJANGO_DEBUG=0` hace que Django exija SSL en esta conexión; la clave temporal solo permite cargar los ajustes de producción durante ese comando y se elimina al terminar. La URI se solicita sin mostrarla ni guardarla en el historial de comandos. Django te pedirá correo, celular, nombre, apellidos y contraseña. Después inicia sesión en `/admin/` y asigna el rol **Dueño** a la cuenta del negocio. No uses la cuenta superusuario para operaciones cotidianas. No guardes la URI de Supabase en el repositorio ni la compartas.

La verificación del correo del sitio no requiere SMTP: Render llama a `https://api.brevo.com` usando `BREVO_API_KEY`. En Brevo debe seguir verificado `pedroglzzz08@gmail.com` como remitente. Registra una cuenta de prueba y mira el mensaje en **Logs** del servicio si falla; no compartas la clave. Una primera petición tras inactividad puede tardar cerca de un minuto mientras Render despierta.

### 3. Publicar React en Cloudflare Pages

1. En Cloudflare abre **Workers & Pages → Create → Pages → Connect to Git** y conecta el mismo repositorio y rama `main`.
2. Configura el directorio raíz como `frontend`, el comando de compilación `npm ci && npm run build` y el directorio de salida `dist`.
3. En variables de entorno de **Production** añade `VITE_API_URL=https://videojuegos-os-api.onrender.com/api`. Si luego cambia el nombre del servicio Render, actualiza esta URL y vuelve a compilar.
4. Cloudflare publicará una URL `https://<nombre>.pages.dev`. Pon ese origen en `FRONTEND_URL` y `CORS_ALLOWED_ORIGINS` del backend Render y redepliega/reinicia el servicio.
5. El archivo `frontend/public/_redirects` habilita rutas SPA como `/login`, `/orders` y `/owner`. Comprueba la página desde una conexión de Cuba antes de anunciarla a clientes.

### 4. Probar antes de anunciar la tienda

- Abre `https://videojuegos-os-api.onrender.com/api/store-settings/` y confirma respuesta JSON.
- Abre el dominio Pages y comprueba catálogo, registro, login, carrito y acceso del dueño.
- Registra una cuenta con un correo controlado por ti; verifica que llega el correo de Brevo y revisa spam. Si no llega, revisa el estado y los Logs de Brevo y los Logs de Render.
- Crea un producto de prueba y un pedido con comprobante; confirma que el comprobante puede abrirse solo tras autenticarte como cliente o dueño.
- Elimina los datos de prueba desde el panel si corresponde. Antes de cargar productos/clientes reales, completa y prueba el respaldo descrito abajo.

La base SQLite local (`db.sqlite3`) y el directorio local `media/` están excluidos de Git. El despliegue empieza con el esquema vacío de Supabase: los productos, usuarios, pedidos y comprobantes locales **no se copian solos**. Puedes volver a crear catálogo y cuentas en producción; si necesitas conservar registros locales, planifica una migración de datos y archivos antes de abrir la tienda. No cargues un fixture con datos de clientes en GitHub.

En producción, `DATABASE_URL` dirige los registros de clientes, contraseñas cifradas, catálogo, inventario, configuración, pedidos y referencias a los comprobantes a PostgreSQL de Supabase. Las capturas de pago son archivos y se guardan en el bucket privado indicado por `SUPABASE_STORAGE_BUCKET`, no dentro de PostgreSQL. Las fotos de producto se guardan como enlaces externos: la base contiene la URL, pero no una copia de la imagen. Si el sitio que aloja una foto deja de servirla, habrá que actualizar ese enlace.

### Pausa y respaldos de Supabase Free

Supabase Free puede **pausar el proyecto por inactividad** (consulta el límite vigente en su [página de precios](https://supabase.com/pricing)). Pausado no significa que se borren inmediatamente las filas, pero la tienda no podrá consultar usuarios, productos ni pedidos hasta que reanudes el proyecto desde su panel. Entra al dashboard, abre el proyecto pausado y elige **Resume/Restore** si aparece; espera a que esté activo y luego vuelve a probar la URL de la API. No cuentes con que una visita a la tienda reactive por sí sola una base pausada.

Un respaldo es una copia independiente para recuperar los registros ante borrado accidental, fallo o pérdida del proyecto. **No impide la pausa y no equivale a garantía de permanencia eterna.** En Free no presupongas que tendrás copias automáticas descargables con retención; conserva copias propias. `pg_dump` incluye las filas y referencias de PostgreSQL, pero no los archivos del bucket, por lo que hay que respaldar ambas cosas.

Frecuencia recomendada: respalda **cada semana** tanto PostgreSQL como Storage, y también inmediatamente antes de cambios de esquema/importaciones o antes de cerrar una cuenta/proyecto. Guarda una copia cifrada adicional en otro dispositivo o ubicación bajo tu control. Una vez al mes, prueba restaurar la base y revisar/abrir archivos en una ubicación de prueba.

#### Respaldo de PostgreSQL

El script [`scripts/backup-supabase.ps1`](./scripts/backup-supabase.ps1) usa `pg_dump` y guarda un archivo personalizado fuera del repositorio en `Documentos\VideoG_TO-backups`:

1. Instala PostgreSQL Command Line Tools en tu computadora para disponer de `pg_dump`.
2. En Supabase, abre **Connect** y copia host, puerto, usuario y base de datos de Session pooler (o usa Direct connection si tu red admite IPv6).
3. Desde PowerShell en la carpeta del proyecto ejecuta, sustituyendo esos cuatro datos por los de tu panel:

   ```powershell
   .\scripts\backup-supabase.ps1 -DbHost "HOST_DEL_POOLER" -Port 5432 -DbUser "USUARIO_DEL_POOLER" -Database "postgres"
   ```

4. Cuando se solicite, escribe la contraseña de la base; no se muestra en pantalla. Comprueba que aparece `Respaldo creado` y que el archivo `.dump` existe. Copia ese archivo a otra ubicación bajo tu control, preferiblemente cifrada y separada de la computadora.
5. Conserva varias copias recientes y prueba periódicamente restaurar una en un proyecto/base de prueba. Un archivo no probado puede no servir al necesitarlo. El archivo contiene datos personales: protege la cuenta/disco de Windows y guarda copias adicionales únicamente en un medio cifrado; no compartas ni subas el `.dump` sin cifrar.

#### Respaldo de comprobantes (Supabase Storage)

El script [`scripts/backup-supabase-storage.py`](./scripts/backup-supabase-storage.py) descarga todos los objetos del bucket a una carpeta fechada en el mismo directorio de respaldos. Usa las credenciales S3 de servidor de Supabase; no uses la `service_role` de la API ni las credenciales de la base de datos:

1. En Supabase, abre la configuración de **Storage / S3** y ten a mano el endpoint S3, región y credenciales S3. Confirma el nombre del bucket privado que usa la tienda (por ejemplo, `payment-proofs`).
2. Desde PowerShell en la carpeta del proyecto, ejecuta:

   ```powershell
   .\.venv\Scripts\python.exe scripts\backup-supabase-storage.py
   ```

3. Introduce endpoint, región, bucket, access key ID y secret access key cuando se soliciten. Las claves se piden sin mostrarse y no se guardan en el script. Comprueba que informa el número de objetos y la ruta del respaldo. Si aparece un error, el respaldo no está completo: corrige el acceso y vuelve a ejecutarlo.
4. Copia también esa carpeta fuera de la computadora o a un medio cifrado. El directorio contiene imágenes privadas de comprobantes y datos personales; limita quién puede acceder.

Los scripts no programan ni envían copias automáticamente. Ejecuta ambos cada semana o configura un recordatorio semanal; no guardes contraseñas, claves ni `.dump` sin cifrar en GitHub o en una carpeta pública.

Las reservas vencidas se liberan cuando se consultan productos/pedidos o antes de nuevas compras. En producción conviene configurar una tarea programada para `python manage.py expire_orders`; en Render Free no hay un trabajador gratuito siempre activo, así que las reservas pueden liberarse al siguiente acceso si no hubo visitas durante el vencimiento.

Referencias: [Planes Supabase](https://supabase.com/pricing), [conexiones PostgreSQL Supabase](https://supabase.com/docs/guides/database/connecting-to-postgres), [S3 de Supabase Storage](https://supabase.com/docs/guides/storage/s3/authentication), [límites gratuitos Render](https://render.com/docs/free), [despliegue Django en Render](https://render.com/docs/deploy-django) y [configuración Cloudflare Pages](https://developers.cloudflare.com/pages/configuration/build-configuration/).
