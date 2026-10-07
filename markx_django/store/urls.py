from django.urls import path

from . import views

app_name = "store"

urlpatterns = [
    path("language/", views.set_language, name="set_language"),
    path("", views.home, name="home"),
    path("shop/", views.shop, name="shop"),
    path("product/<slug:slug>/", views.product_detail, name="product"),
    path("product/<slug:slug>/review/", views.submit_review, name="submit_review"),
    path("product/<int:pk>/stock-alert/", views.stock_alert_subscribe, name="stock_alert"),
    path("search/", views.search_api, name="search"),
    path("cart/", views.cart_view, name="cart"),
    path("my-orders/", views.my_orders, name="my_orders"),
    path("cart/add/<int:pk>/", views.cart_add, name="cart_add"),
    path("cart/update/", views.cart_update, name="cart_update"),
    path("cart/remove/", views.cart_remove, name="cart_remove"),
    path("checkout/", views.checkout, name="checkout"),
    path("checkout/otp/", views.checkout_otp, name="checkout_otp"),
    path("order/<str:number>/", views.order_success, name="order_success"),
    path("track/", views.track_order, name="track_order"),
    path("wishlist/", views.wishlist_page, name="wishlist"),
    path("wishlist/toggle/<int:pk>/", views.wishlist_toggle, name="wishlist_toggle"),
    path("wishlist/merge/", views.wishlist_merge, name="wishlist_merge"),
    path("customize/", views.customize, name="customize"),
    path("bulk-order/", views.bulk_order, name="bulk"),
    path("about/", views.about, name="about"),
    path("about/comment/", views.leave_comment, name="leave_comment"),
    path("contact/", views.contact, name="contact"),
    path("newsletter/", views.newsletter, name="newsletter"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("dashboard/manage/", views.staff_workspace, name="staff_workspace"),
    path("dashboard/inventory-import/", views.inventory_csv_import, name="inventory_import"),
    path("dashboard/manage/<slug:model_key>/", views.staff_model_list, name="manage_model"),
    path("dashboard/manage/<slug:model_key>/new/", views.staff_model_edit, name="manage_create"),
    path("dashboard/manage/<slug:model_key>/<int:pk>/edit/", views.staff_model_edit, name="manage_edit"),
    path("dashboard/manage/<slug:model_key>/<int:pk>/delete/", views.staff_model_delete, name="manage_delete"),
    path("profile/", views.account, name="account"),
    path("profile/loyalty/", views.loyalty, name="loyalty"),
    path("profile/edit/", views.profile_edit, name="profile_edit"),
    path("profile/logout/", views.account_logout, name="account_logout"),
]
