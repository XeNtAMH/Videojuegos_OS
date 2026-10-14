from django.contrib import admin
from django.conf import settings
from django.urls import include, path
from django.views.static import serve

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("backend.store.urls")),
]

if settings.DEBUG:
    urlpatterns += [
        path(
            "media/products/<path:path>",
            serve,
            {"document_root": settings.MEDIA_ROOT / "products"},
        ),
    ]
