from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    LoginView,
    CurrentUserView,
    ManagedCategoryViewSet,
    ManagedOrderViewSet,
    ManagedProductViewSet,
    ManagedStoreSettingsView,
    OrderViewSet,
    PaymentProofFileView,
    ProductListView,
    RegisterView,
    ResendEmailVerificationView,
    StoreSettingsView,
    VerifyEmailView,
)

router = DefaultRouter()
router.register("orders", OrderViewSet, basename="order")

owner_router = DefaultRouter()
owner_router.register("owner/products", ManagedProductViewSet, basename="owner-product")
owner_router.register("owner/categories", ManagedCategoryViewSet, basename="owner-category")
owner_router.register("owner/orders", ManagedOrderViewSet, basename="owner-order")

urlpatterns = [
    path("auth/register/", RegisterView.as_view(), name="register"),
    path("auth/login/", LoginView.as_view(), name="login"),
    path(
        "auth/resend-verification/",
        ResendEmailVerificationView.as_view(),
        name="resend-verification",
    ),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("auth/verify-email/", VerifyEmailView.as_view(), name="verify-email"),
    path("auth/me/", CurrentUserView.as_view(), name="current-user"),
    path("products/", ProductListView.as_view(), name="products"),
    path("store-settings/", StoreSettingsView.as_view(), name="store-settings"),
    path(
        "owner/settings/",
        ManagedStoreSettingsView.as_view(),
        name="owner-settings",
    ),
    path(
        "orders/<int:order_id>/proofs/<int:proof_id>/",
        PaymentProofFileView.as_view(),
        name="payment-proof-file",
    ),
    path("", include(router.urls)),
    path("", include(owner_router.urls)),
]
