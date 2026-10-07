import json
import os
import subprocess
import sys
from decimal import Decimal
from io import BytesIO
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from .models import (Category, Coupon, Order, OrderItem, Product, Review, Wishlist,
                     ProductVariant, BackInStockSubscription, GiftCard, GiftCardUse)
from .forms import BulkForm, CheckoutForm, ContactForm, CustomForm, normalize_pakistani_mobile
from .sitemaps import ProductSitemap


class AccountLoginTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.customer = user_model.objects.create_user(
            username="store-customer",
            email="customer@example.com",
            password="test-password-123",
        )
        self.staff = user_model.objects.create_user(
            username="store-staff",
            email="staff@example.com",
            password="test-password-123",
            is_staff=True,
        )

    def test_customer_login_redirects_to_storefront(self):
        response = self.client.post(reverse("store:account"), {
            "account_action": "login",
            "username": self.customer.email.upper(),
            "password": "test-password-123",
        })

        self.assertRedirects(response, reverse("store:home"))

    def test_staff_login_redirects_to_store_dashboard(self):
        response = self.client.post(reverse("store:account"), {
            "account_action": "login",
            "username": self.staff.email,
            "password": "test-password-123",
        })

        self.assertRedirects(response, reverse("store:dashboard"))

    def test_login_form_requests_an_email_address(self):
        response = self.client.get(reverse("store:account"))

        self.assertContains(response, "Email address")
        self.assertNotContains(response, "Username")

    def test_dashboard_link_is_only_shown_to_staff(self):
        home_url = reverse("store:home")

        self.client.force_login(self.customer)
        customer_response = self.client.get(home_url)
        self.assertNotContains(customer_response, reverse("store:dashboard"))
        self.assertNotContains(customer_response, reverse("store:my_orders"))

        self.client.force_login(self.staff)
        staff_response = self.client.get(home_url)
        self.assertContains(staff_response, reverse("store:dashboard"))

    def test_dashboard_is_accessible_to_staff_only(self):
        dashboard_url = reverse("store:dashboard")

        self.client.force_login(self.customer)
        customer_response = self.client.get(dashboard_url)
        self.assertEqual(customer_response.status_code, 302)
        self.assertIn("/admin/login/", customer_response.url)

        self.client.force_login(self.staff)
        staff_response = self.client.get(dashboard_url)
        self.assertEqual(staff_response.status_code, 200)
        self.assertContains(staff_response, "Store overview")


class StaffWorkspaceTests(TestCase):
    def setUp(self):
        self.media_dir = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(MEDIA_ROOT=self.media_dir.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.addCleanup(self.media_dir.cleanup)

        user_model = get_user_model()
        self.staff = user_model.objects.create_user(
            username="workspace-staff",
            password="test-password-123",
            is_staff=True,
        )
        self.category = Category.objects.create(name="Workspace category")
        self.client.force_login(self.staff)

    def test_workspace_and_all_store_sections_render(self):
        response = self.client.get(reverse("store:staff_workspace"))
        self.assertEqual(response.status_code, 200)

        for model_key in (
            "products", "categories", "orders", "custom-requests",
            "bulk-requests", "subscribers", "messages",
        ):
            with self.subTest(model_key=model_key):
                response = self.client.get(reverse("store:manage_model", args=[model_key]))
                self.assertEqual(response.status_code, 200)
                if model_key == "orders":
                    self.assertContains(response, reverse("store:dashboard"))
                    self.assertContains(response, "Back to dashboard")

    def test_customer_cannot_open_staff_workspace(self):
        customer = get_user_model().objects.create_user(
            username="workspace-customer",
            password="test-password-123",
        )
        self.client.force_login(customer)

        response = self.client.get(reverse("store:staff_workspace"))

        self.assertEqual(response.status_code, 302)

    def test_add_forms_render_for_all_addable_store_sections(self):
        for model_key in (
            "products", "categories", "orders", "custom-requests",
            "bulk-requests", "messages",
        ):
            with self.subTest(model_key=model_key):
                response = self.client.get(reverse("store:manage_create", args=[model_key]))
                self.assertEqual(response.status_code, 200)

    def test_product_can_be_created_edited_and_deleted(self):
        image_buffer = BytesIO()
        Image.new("RGB", (2, 2), color="white").save(image_buffer, format="PNG")
        image_content = image_buffer.getvalue()

        create_data = {
            "name": "Workspace tee",
            "slug": "workspace-tee",
            "category": self.category.pk,
            "collection": "men",
            "product_type": "plain",
            "badge": "",
            "description": "Test product",
            "price": "3500",
            "old_price": "",
            "rating": "4.5",
            "reviews": "0",
            "colors": "Black",
            "sizes": "S,M,L",
            "size_guide": "top",
            "stock_qty": "10",
            "customizable": "on",
            "featured": "on",
            "in_stock": "on",
            "active": "on",
            "image": SimpleUploadedFile("workspace.png", image_content, content_type="image/png"),
        }
        create_response = self.client.post(
            reverse("store:manage_create", args=["products"]), create_data,
        )
        product = Product.objects.get(slug="workspace-tee")
        self.assertRedirects(create_response, reverse("store:manage_model", args=["products"]))
        list_response = self.client.get(reverse("store:manage_model", args=["products"]))
        self.assertContains(list_response, product.image.url)
        self.assertContains(list_response, "staff-product-thumb")

        edit_response = self.client.post(
            reverse("store:manage_edit", args=["products", product.pk]),
            {**{key: value for key, value in create_data.items() if key != "image"}, "price": "4200"},
        )
        product.refresh_from_db()
        self.assertEqual(product.price, 4200)
        self.assertRedirects(edit_response, reverse("store:manage_model", args=["products"]))

        delete_response = self.client.post(
            reverse("store:manage_delete", args=["products", product.pk]),
        )
        self.assertFalse(Product.objects.filter(pk=product.pk).exists())
        self.assertRedirects(delete_response, reverse("store:manage_model", args=["products"]))

    def test_cart_has_a_back_to_shop_icon(self):
        response = self.client.get(reverse("store:cart"))

        self.assertContains(response, "cart-back-icon")
        self.assertContains(response, 'aria-label="Go back"')
        self.assertContains(response, "data-history-back")
        self.assertContains(response, f'href="{reverse("store:shop")}"')
        self.assertContains(response, reverse("store:my_orders"))

    def test_guest_can_see_my_orders_link_and_will_be_asked_to_sign_in(self):
        self.client.logout()

        response = self.client.get(reverse("store:cart"))

        self.assertContains(response, "My orders")
        orders_response = self.client.get(reverse("store:my_orders"))
        self.assertRedirects(
            orders_response,
            f'{reverse("store:account")}?next={reverse("store:my_orders")}',
        )

    def test_my_orders_only_shows_the_signed_in_users_orders(self):
        own_order = Order.objects.create(
            user=self.staff,
            full_name="Staff Customer",
            email=self.staff.email,
            phone="03001234567",
            address="1 Main Street",
            city="Lahore",
            total=3500,
        )
        other_user = get_user_model().objects.create_user(
            username="another-customer",
            password="test-password-123",
        )
        other_order = Order.objects.create(
            user=other_user,
            full_name="Other Customer",
            phone="03007654321",
            address="2 Main Street",
            city="Karachi",
            total=4200,
        )

        response = self.client.get(reverse("store:my_orders"))

        self.assertContains(response, own_order.number)
        self.assertNotContains(response, other_order.number)

    def test_my_orders_requires_login(self):
        self.client.logout()

        response = self.client.get(reverse("store:my_orders"))

        self.assertRedirects(
            response,
            f'{reverse("store:account")}?next={reverse("store:my_orders")}',
        )

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="orders@markx.example",
    )
    def test_checkout_emails_order_confirmation_with_order_details(self):
        image_buffer = BytesIO()
        Image.new("RGB", (2, 2), color="white").save(image_buffer, format="PNG")
        product = Product.objects.create(
            name="Confirmation tee",
            slug="confirmation-tee",
            category=self.category,
            price=1500,
            image=SimpleUploadedFile("confirmation.png", image_buffer.getvalue(), content_type="image/png"),
        )
        session = self.client.session
        session["markx_cart"] = {
            f"{product.pk}|M|Black": {"pid": product.pk, "size": "M", "color": "Black", "qty": 2},
        }
        session["verified_cod_phone"] = "03001234567"
        session.save()

        response = self.client.post(reverse("store:checkout"), {
            "full_name": "MarkX Customer",
            "phone": "03001234567",
            "email": "customer@example.com",
            "address": "1 Main Street",
            "city": "Lahore",
            "notes": "Leave at reception",
            "payment_method": "cod",
        })

        order = Order.objects.get(user=self.staff)
        self.assertRedirects(response, reverse("store:order_success", args=[order.number]))
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["customer@example.com"])
        self.assertIn(order.number, message.subject)
        self.assertIn(product.name, message.body)
        self.assertIn("2 x Confirmation tee", message.body)
        self.assertIn("Rs. 3,200", message.body)
        self.assertTrue(message.alternatives)
        self.assertIn(product.name, message.alternatives[0][0])
        self.assertIn("Deliver to: 1 Main Street, Lahore", message.body)
        self.assertIn("Cash on delivery", message.body)


class CollectionBrowsingRemovalTests(TestCase):
    def test_homepage_has_no_collection_section_or_navigation(self):
        response = self.client.get(reverse("store:home"))

        self.assertNotContains(response, "Shop By Collection")
        self.assertNotContains(response, "#collections")
        self.assertNotContains(response, "EXPLORE OUR COLLECTIONS")

    def test_shop_has_no_collection_filter_or_collection_context(self):
        response = self.client.get(reverse("store:shop"), {"collection": "kids"})

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="collection"')
        self.assertNotIn("active_collection", response.context)


class MenOnlyCatalogTests(TestCase):
    def test_storefront_queryset_only_returns_active_men_products(self):
        category = Category.objects.create(name="Storefront category")
        active_men = Product.objects.create(
            name="Active men shirt", category=category, price=1000,
            image="products/active-men.jpg", collection="men", active=True,
        )
        Product.objects.create(
            name="Active women shirt", category=category, price=1000,
            image="products/active-women.jpg", collection="women", active=True,
        )
        Product.objects.create(
            name="Inactive men shirt", category=category, price=1000,
            image="products/inactive-men.jpg", collection="men", active=False,
        )

        storefront = Product.objects.storefront()
        self.assertIn(active_men, storefront)
        self.assertNotIn("Active women shirt", storefront.values_list("name", flat=True))
        self.assertNotIn("Inactive men shirt", storefront.values_list("name", flat=True))

    def test_shop_hides_categories_without_active_products(self):
        active_category = Category.objects.create(name="Active category")
        Category.objects.create(name="Empty category")
        Product.objects.create(
            name="Active tee", category=active_category, price=1000,
            image="products/active-tee.jpg", active=True,
        )

        response = self.client.get(reverse("store:shop"))

        self.assertContains(response, "Active category")
        self.assertNotContains(response, "Empty category")

    def test_product_staff_form_exposes_collection_and_defaults_to_men(self):
        staff = get_user_model().objects.create_user(username="collection-staff", is_staff=True)
        self.client.force_login(staff)
        response = self.client.get(reverse("store:manage_create", args=["products"]))

        self.assertContains(response, 'name="collection"')
        self.assertEqual(response.context["form"].fields["collection"].initial, "men")

    def test_non_men_products_are_hidden_from_customer_entry_points(self):
        men_category = Category.objects.create(name="Men shirts")
        women_category = Category.objects.create(name="Women only")
        men_product = Product.objects.create(
            name="Men catalog shirt", category=men_category, price=1000,
            image="products/men-shirt.jpg", collection="men", featured=True,
        )
        women_product = Product.objects.create(
            name="Women secret shirt", category=women_category, price=1000,
            image="products/women-shirt.jpg", collection="women", sizes="2Y",
            colors="Pink", featured=True,
        )

        home = self.client.get(reverse("store:home"))
        shop = self.client.get(reverse("store:shop"), {"q": "Men catalog shirt"})
        search = self.client.get(reverse("store:search"), {"q": "Women secret"})

        self.assertEqual(list(home.context["featured"]), [men_product])
        self.assertEqual(list(shop.context["products"]), [men_product])
        category_names = [category.name for category in shop.context["categories"]]
        self.assertIn("Men shirts", category_names)
        self.assertNotIn("Women only", category_names)
        self.assertNotIn("2Y", shop.context["sizes"])
        self.assertNotIn("Pink", shop.context["colors"])
        self.assertEqual(search.json()["results"], [])
        self.assertEqual(self.client.get(women_product.get_absolute_url()).status_code, 404)
        sitemap_products = ProductSitemap().items()
        self.assertIn(men_product, sitemap_products)
        self.assertNotIn(women_product, sitemap_products)
        self.assertEqual(
            self.client.post(reverse("store:cart_add", args=[women_product.pk]), {"size": "M", "color": "Pink"}).status_code,
            404,
        )

        wishlist_user = get_user_model().objects.create_user(username="storefront-wishlist")
        self.client.force_login(wishlist_user)
        Wishlist.objects.create(user=wishlist_user, product=women_product)
        wishlist = self.client.get(reverse("store:wishlist"))
        merge = self.client.post(
            reverse("store:wishlist_merge"),
            data=json.dumps({"ids": [women_product.pk]}),
            content_type="application/json",
        )
        self.assertNotContains(wishlist, "Women secret shirt")
        self.assertEqual(merge.json()["ids"], [])
        self.assertEqual(
            self.client.post(reverse("store:wishlist_toggle", args=[women_product.pk])).status_code,
            404,
        )

    def test_final_shop_routes_allow_only_the_three_menswear_groups(self):
        call_command("seed", verbosity=0)
        legacy_categories = {
            name: Category.objects.get_or_create(name=name)[0]
            for name in ("Women legacy", "Kids legacy", "Accessories", "Hoodies", "Jackets")
        }
        forbidden = [
            Product.objects.create(
                name="Women legacy item", category=legacy_categories["Women legacy"],
                price=1000, image="products/women-legacy.jpg", collection="women", active=False,
            ),
            Product.objects.create(
                name="Kids legacy item", category=legacy_categories["Kids legacy"],
                price=1000, image="products/kids-legacy.jpg", collection="kids", active=False,
            ),
            Product.objects.create(
                name="Accessories legacy item", category=legacy_categories["Accessories"],
                price=1000, image="products/accessories-legacy.jpg", collection="accessories", active=False,
            ),
            Product.objects.create(
                name="Legacy hoodie", category=legacy_categories["Hoodies"],
                price=1000, image="products/legacy-hoodie.jpg", collection="men", active=False,
            ),
            Product.objects.create(
                name="Legacy jacket", category=legacy_categories["Jackets"],
                price=1000, image="products/legacy-jacket.jpg", collection="men", active=False,
            ),
        ]

        for slug in ("oxford-casual-shirt", "cargo-pants", "core-fleece-tracksuit"):
            with self.subTest(slug=slug):
                product = Product.objects.get(slug=slug)
                self.assertEqual(self.client.get(product.get_absolute_url()).status_code, 200)

        shop = self.client.get(reverse("store:shop"))
        search = self.client.get(reverse("store:search"), {"q": "Legacy"})
        self.assertEqual(
            set(category.name for category in shop.context["categories"]),
            {"Shirts", "Trousers", "Tracksuits"},
        )
        self.assertEqual(search.json()["results"], [])
        for product in forbidden:
            with self.subTest(product=product.name):
                self.assertEqual(self.client.get(product.get_absolute_url()).status_code, 404)
                self.assertNotIn(product, ProductSitemap().items())

    def test_seed_keeps_and_deactivates_legacy_products_on_each_run(self):
        legacy_category = Category.objects.create(name="Legacy women category")
        legacy_women = Product.objects.create(
            name="Legacy women item", slug="legacy-women-item", category=legacy_category,
            price=1000, image="products/legacy-women.jpg", collection="women",
        )
        hoodie_category = Category.objects.create(name="Hoodies")
        legacy_hoodie = Product.objects.create(
            name="Legacy hoodie", slug="legacy-hoodie", category=hoodie_category,
            price=2000, image="products/legacy-hoodie.jpg",
        )

        call_command("seed", verbosity=0)
        legacy_women.refresh_from_db()
        legacy_hoodie.refresh_from_db()
        mens_product = Product.objects.get(slug="better-days-oversized-tee")
        seeded_hoodie = Product.objects.get(slug="essential-hoodie")
        self.assertTrue(Product.objects.filter(pk=legacy_women.pk).exists())
        self.assertFalse(legacy_women.active)
        self.assertFalse(legacy_hoodie.active)
        self.assertFalse(seeded_hoodie.active)
        self.assertTrue(mens_product.active)

        legacy_women.active = True
        legacy_women.save(update_fields=["active"])
        call_command("seed", verbosity=0)

        legacy_women.refresh_from_db()
        self.assertFalse(legacy_women.active)
        self.assertTrue(Category.objects.filter(name="Shirts").exists())

    def test_final_navigation_only_contains_the_three_active_product_groups(self):
        call_command("seed", verbosity=0)
        tracksuit_category = Category.objects.get(name="Tracksuits")
        Product.objects.create(
            name="Test tracksuit", category=tracksuit_category, product_type="tracksuit",
            price=4000, image="products/test-tracksuit.jpg",
        )

        response = self.client.get(reverse("store:shop"))

        self.assertEqual(
            set(category.name for category in response.context["categories"]),
            {"Shirts", "Trousers", "Tracksuits"},
        )

    def test_homepage_uses_menswear_copy_and_keeps_delivery_exchange_offers(self):
        response = self.client.get(reverse("store:home"))

        self.assertContains(response, "shirts, trousers and tracksuits")
        self.assertContains(response, "15% OFF WHEN YOU PAY BY CARD")
        self.assertContains(response, "7-day exchange")
        self.assertNotContains(response, "printed on demand")
        self.assertNotContains(response, "DTF")
        self.assertNotContains(response, "hoodies")

    def test_about_customize_and_bulk_pages_use_menswear_language(self):
        about = self.client.get(reverse("store:about"))
        customize = self.client.get(reverse("store:customize"))
        bulk = self.client.get(reverse("store:bulk"))

        self.assertContains(about, "MarkX brings together men's shirts, trousers and tracksuits")
        self.assertNotContains(about, "custom printing")
        self.assertContains(customize, "personalised shirt, trouser or tracksuit")
        self.assertNotContains(customize, "we print it")
        self.assertContains(bulk, "shirts, trousers and tracksuits")
        self.assertNotContains(bulk, "DTF")

    def test_seed_adds_tracksuit_samples_and_waist_sizes_for_trousers(self):
        call_command("seed", verbosity=0)

        tracksuits = Product.objects.filter(category__name="Tracksuits", product_type="tracksuit")
        trousers = Product.objects.filter(category__name="Trousers")

        self.assertEqual(tracksuits.count(), 3)
        self.assertTrue(tracksuits.filter(size_guide="set", sizes="S, M, L, XL, XXL").exists())
        self.assertTrue(trousers.exists())
        self.assertTrue(all(product.sizes == "28, 30, 32, 34, 36, 38" for product in trousers))


class ProductDetailEnhancementTests(TestCase):
    def create_product(self, name, category, **kwargs):
        return Product.objects.create(
            name=name, category=category, price=1500,
            image="products/test-product.jpg", **kwargs,
        )

    def test_details_and_top_size_guide_render_on_product_page(self):
        category = Category.objects.get(name="Shirts")
        product = self.create_product(
            "Test Shirt", category, fit="regular", fabric="Cotton poplin",
            care="Machine wash cold", size_guide="top",
        )

        response = self.client.get(product.get_absolute_url())

        self.assertContains(response, "Details")
        self.assertContains(response, "Cotton poplin")
        self.assertContains(response, "Chest")
        self.assertContains(response, "Length")
        self.assertContains(response, "approx. inches")

    def test_back_in_stock_subscription_is_for_an_exact_variant(self):
        product = self.create_product("Alert Shirt", Category.objects.get(name="Shirts"), colors="Black", sizes="M")
        variant = ProductVariant.objects.create(product=product, size="M", color="Black", stock_qty=0)
        response = self.client.post(reverse("store:stock_alert", args=[product.pk]), {
            "size": "M", "color": "Black", "email": "alert@example.com",
        })
        self.assertRedirects(response, product.get_absolute_url())
        self.assertEqual(BackInStockSubscription.objects.filter(variant=variant, email="alert@example.com").count(), 1)

    def test_size_recommender_uses_valid_customer_measurements(self):
        product = self.create_product("Recommend Shirt", Category.objects.get(name="Shirts"))
        response = self.client.get(product.get_absolute_url(), {"height": 170, "weight": 70, "fit": "regular"})

        self.assertContains(response, "Recommended size:")
        self.assertContains(response, "<b>M</b>")

    def test_language_choice_persists_and_rejects_external_redirect(self):
        response = self.client.post(reverse("store:set_language"), {"language": "ur", "next": "https://evil.example"})

        self.assertRedirects(response, reverse("store:home"))
        self.assertEqual(self.client.session["site_language"], "ur")
        page = self.client.get(reverse("store:home"))
        self.assertContains(page, 'lang="ur" dir="rtl"')

    def test_urdu_homepage_translates_hero_and_faq_copy(self):
        session = self.client.session
        session["site_language"] = "ur"
        session.save()

        response = self.client.get(reverse("store:home"))

        self.assertContains(response, "اپنے لیے")
        self.assertContains(response, "اکثر پوچھے گئے سوالات")
        self.assertContains(response, "آرڈر کی ترسیل میں کتنا وقت لگتا ہے؟")
        self.assertContains(response, "6,000 روپے سے زیادہ کے آرڈرز پر ڈیلیوری مفت ہے۔")
        self.assertNotContains(response, "What is your exchange policy?")

    def test_shirt_size_guide_includes_collar_chest_and_sleeve_length(self):
        category = Category.objects.get(name="Shirts")
        product = self.create_product("Guide Shirt", category, product_type="shirt", size_guide="shirt")

        response = self.client.get(product.get_absolute_url())

        self.assertContains(response, "Collar")
        self.assertContains(response, "Chest")
        self.assertContains(response, "Sleeve length")

    def test_trouser_size_guide_and_complete_the_look_suggest_tops(self):
        trouser_category = Category.objects.get(name="Trousers")
        shirt_category = Category.objects.get(name="Shirts")
        trouser = self.create_product("Test Trouser", trouser_category, product_type="trousers", size_guide="bottom")
        self.create_product("Test Shirt", shirt_category, product_type="shirt")

        response = self.client.get(trouser.get_absolute_url())

        self.assertContains(response, "Waist")
        self.assertContains(response, "Inseam")
        self.assertContains(response, "Complete the look")
        self.assertContains(response, "Test Shirt")

    def test_shirts_and_tracksuits_suggest_trousers_or_shirts(self):
        shirt_category = Category.objects.get(name="Shirts")
        trouser_category = Category.objects.get(name="Trousers")
        tracksuit_category = Category.objects.get(name="Tracksuits")
        shirt = self.create_product("Pairing Shirt", shirt_category, product_type="shirt")
        trouser = self.create_product("Pairing Trouser", trouser_category, product_type="trousers")
        tracksuit = self.create_product("Pairing Tracksuit", tracksuit_category, product_type="tracksuit")

        shirt_response = self.client.get(shirt.get_absolute_url())
        trouser_response = self.client.get(trouser.get_absolute_url())
        tracksuit_response = self.client.get(tracksuit.get_absolute_url())

        self.assertContains(shirt_response, "Pairing Trouser")
        self.assertContains(trouser_response, "Pairing Shirt")
        self.assertContains(tracksuit_response, "Pairing Shirt")

    def test_tracksuit_is_one_size_set_and_labelled_in_product_and_cart(self):
        tracksuit = self.create_product(
            "Matched Tracksuit", Category.objects.get(name="Tracksuits"),
            product_type="tracksuit", size_guide="set", sizes="S,M,L,XL,XXL",
        )

        product_response = self.client.get(tracksuit.get_absolute_url())
        session = self.client.session
        session["markx_cart"] = {
            f"{tracksuit.pk}|M|Black": {"pid": tracksuit.pk, "size": "M", "color": "Black", "qty": 1},
        }
        session.save()
        cart_response = self.client.get(reverse("store:cart"))

        self.assertContains(product_response, "Jacket + trousers set")
        self.assertContains(product_response, "Jacket chest")
        self.assertContains(product_response, "Trouser waist")
        self.assertEqual(product_response.content.count(b'data-group="size"'), 1)
        self.assertContains(cart_response, "Jacket + trousers set")

    def test_top_suggests_trousers_and_other_products_fall_back_to_category(self):
        shirt_category = Category.objects.get(name="Shirts")
        trouser_category = Category.objects.get(name="Trousers")
        jacket_category = Category.objects.create(name="Jackets")
        shirt = self.create_product("Test Shirt", shirt_category)
        self.create_product("Test Trouser", trouser_category, product_type="trousers")
        jacket = self.create_product("Test Jacket", jacket_category, product_type="jacket")
        self.create_product("Second Jacket", jacket_category, product_type="jacket")

        shirt_response = self.client.get(shirt.get_absolute_url())
        jacket_response = self.client.get(jacket.get_absolute_url())

        self.assertContains(shirt_response, "Test Trouser")
        self.assertContains(jacket_response, "Related")
        self.assertContains(jacket_response, "Second Jacket")


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class StockManagementTests(TestCase):
    def setUp(self):
        self.customer = get_user_model().objects.create_user(
            username="stock-customer", email="stock@example.com", password="test-password-123",
        )
        self.category = Category.objects.create(name="Stock test category")
        self.product = Product.objects.create(
            name="Stock test tee", category=self.category, price=1000,
            image="products/stock-test.jpg", stock_qty=5,
        )

    def add_to_cart(self, qty, size="M", color="Black"):
        session = self.client.session
        session["markx_cart"] = {
            f"{self.product.pk}|{size}|{color}": {
                "pid": self.product.pk, "size": size, "color": color, "qty": qty,
            },
        }
        session.save()

    def post_checkout(self):
        session = self.client.session
        session["verified_cod_phone"] = "03001234567"
        session.save()
        return self.client.post(reverse("store:checkout"), {
            "full_name": "Stock Customer", "phone": "03001234567",
            "email": "stock@example.com", "address": "1 Main Street",
            "city": "Lahore", "payment_method": "cod",
        })

    def test_cart_add_rejects_out_of_stock_and_invalid_options(self):
        self.product.stock_qty = 0
        self.product.save(update_fields=["stock_qty"])
        response = self.client.post(
            reverse("store:cart_add", args=[self.product.pk]),
            {"size": "M", "color": "Black"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])

        self.product.stock_qty = 5
        self.product.save(update_fields=["stock_qty"])
        response = self.client.post(
            reverse("store:cart_add", args=[self.product.pk]),
            {"size": "XXL", "color": "Red"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])

    def test_cart_quantity_is_clamped_to_available_stock(self):
        self.product.stock_qty = 3
        self.product.save(update_fields=["stock_qty"])
        self.client.post(reverse("store:cart_add", args=[self.product.pk]), {
            "size": "M", "color": "Black", "qty": "8",
        })
        self.assertEqual(self.client.session["markx_cart"][f"{self.product.pk}|M|Black"]["qty"], 3)

    def test_checkout_decrements_stock_and_rejects_short_stock(self):
        self.client.force_login(self.customer)
        self.add_to_cart(3)
        response = self.post_checkout()
        self.assertEqual(response.status_code, 302)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_qty, 2)
        self.assertEqual(Order.objects.count(), 1)

        self.product.stock_qty = 1
        self.product.save(update_fields=["stock_qty"])
        self.add_to_cart(2, size="L")
        response = self.post_checkout()
        self.assertRedirects(response, reverse("store:checkout"))
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_qty, 1)
        self.assertEqual(Order.objects.count(), 1)

    def test_cancelling_order_restores_stock_only_once(self):
        order = Order.objects.create(
            user=self.customer, full_name="Stock Customer", phone="03001234567",
            email="stock@example.com", address="1 Main Street", city="Lahore",
        )
        OrderItem.objects.create(
            order=order, product=self.product, name=self.product.name,
            size="M", color="Black", price=1000, qty=2,
        )
        self.product.stock_qty = 3
        self.product.save(update_fields=["stock_qty"])

        order.status = "cancelled"
        order.save(update_fields=["status"])
        order.status = "pending"
        order.save(update_fields=["status"])
        order.status = "cancelled"
        order.save(update_fields=["status"])

        self.product.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(self.product.stock_qty, 5)
        self.assertTrue(order.stock_restored)


class ShopFilterPaginationTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Filter category")

    def create_product(self, name, sizes, colors, price=1500):
        return Product.objects.create(
            name=name, category=self.category, price=price, sizes=sizes,
            colors=colors, image="products/filter-test.jpg",
        )

    def test_size_and_colour_filters_match_exact_tokens_and_combine(self):
        matching = self.create_product("Exact option product", "S, L", "Black, Red")
        self.create_product("Substring decoy", "XS, XL", "Dark Red")

        size_response = self.client.get(reverse("store:shop"), {"category": self.category.slug, "size": "L"})
        color_response = self.client.get(reverse("store:shop"), {"category": self.category.slug, "color": "Red"})
        combined_response = self.client.get(reverse("store:shop"), {
            "category": self.category.slug, "size": "L", "color": "Red", "max": "2000",
        })

        self.assertEqual(list(size_response.context["products"]), [matching])
        self.assertEqual(list(color_response.context["products"]), [matching])
        self.assertEqual(list(combined_response.context["products"]), [matching])

    def test_pagination_has_twelve_products_and_preserves_query_filters(self):
        for index in range(13):
            self.create_product(f"Paginator tee {index:02d}", "M", "Blue", 1200 + index)
        params = {
            "category": self.category.slug, "q": "Paginator", "max": "6000",
            "size": "M", "color": "Blue", "sort": "low",
        }

        first = self.client.get(reverse("store:shop"), params)

        self.assertEqual(first.context["page_obj"].paginator.count, 13)
        self.assertEqual(len(first.context["products"]), 12)
        next_url = first.context["query_string"] + "&page=2"
        second = self.client.get(f"{reverse('store:shop')}?{next_url}")
        self.assertEqual(second.context["page_obj"].number, 2)
        self.assertEqual(second.context["page_obj"].paginator.count, 13)
        context_values = {
            "active_cat": params["category"], "q": params["q"],
            "max_price": params["max"], "active_size": params["size"],
            "active_color": params["color"], "sort": params["sort"],
        }
        for name, value in context_values.items():
            self.assertEqual(second.context[name], value)


class PakistaniPhoneValidationTests(TestCase):
    def test_request_fields_and_processing_status_use_updated_labels(self):
        self.assertEqual(CustomForm().fields["tshirt_type"].label, "Item type")
        self.assertEqual(BulkForm().fields["tshirt_type"].label, "Item type")
        self.assertEqual(dict(Order.STATUS)["printing"], "Processing")
        self.assertEqual(Order(status="printing").status, "printing")

    def test_size_field_help_explains_waist_sizing(self):
        self.assertIn("waist sizes 28, 30, 32, 34, 36, 38", Product._meta.get_field("sizes").help_text)

    def test_local_and_international_numbers_normalize_to_local_format(self):
        self.assertEqual(normalize_pakistani_mobile("03001234567"), "03001234567")
        self.assertEqual(normalize_pakistani_mobile("+923001234567"), "03001234567")

    def test_all_customer_forms_validate_and_normalize_phone(self):
        forms = [
            CheckoutForm(data={"full_name": "Customer", "phone": "+923001234567", "email": "a@example.com", "address": "1 Road", "city": "Lahore", "payment_method": "cod"}),
            CustomForm(data={"name": "Customer", "phone": "+923001234567", "quantity": "1"}),
            BulkForm(data={"organization": "Team", "contact_person": "Customer", "phone": "+923001234567", "email": "a@example.com", "order_type": "Uniforms"}),
            ContactForm(data={"name": "Customer", "email": "a@example.com", "phone": "+923001234567", "message": "Hello"}),
        ]
        for form in forms:
            with self.subTest(form=form.__class__.__name__):
                self.assertTrue(form.is_valid(), form.errors)
                self.assertEqual(form.cleaned_data["phone"], "03001234567")

    def test_optional_contact_phone_can_be_empty_and_invalid_mobile_is_rejected(self):
        contact = ContactForm(data={"name": "Customer", "email": "a@example.com", "phone": "", "message": "Hello"})
        invalid = CheckoutForm(data={"full_name": "Customer", "phone": "12345", "email": "a@example.com", "address": "1 Road", "city": "Lahore", "payment_method": "cod"})

        self.assertTrue(contact.is_valid(), contact.errors)
        self.assertEqual(contact.cleaned_data["phone"], "")
        self.assertIn("phone", invalid.errors)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class OrderTrackingAndStatusEmailTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user(
            username="order-staff", password="test-password-123", is_staff=True,
        )
        self.order = Order.objects.create(
            full_name="Track Customer", phone="03001234567", email="track@example.com",
            address="1 Main Street", city="Lahore",
        )

    def test_track_order_matches_number_and_normalized_phone(self):
        self.order.status = "shipped"
        self.order.save(update_fields=["status"])
        response = self.client.post(reverse("store:track_order"), {
            "order_number": self.order.number.lower(), "phone": "+923001234567",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Shipped")

        mismatch = self.client.post(reverse("store:track_order"), {
            "order_number": self.order.number, "phone": "03009999999",
        })
        self.assertContains(mismatch, "could not find an order")

    def test_status_email_is_sent_for_status_change(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.order.status = "confirmed"
            self.order.save(update_fields=["status"])

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("confirmed", mail.outbox[0].subject.lower())
        self.assertIn("Pending", mail.outbox[0].body)
        self.assertTrue(mail.outbox[0].alternatives)

    def test_status_change_from_staff_workspace_sends_email(self):
        self.client.force_login(self.staff)
        url = reverse("store:manage_edit", args=["orders", self.order.pk])
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(url, {"status": "delivered", "notes": ""})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("delivered", mail.outbox[0].subject.lower())

    def test_django_admin_status_save_sends_email(self):
        from django.contrib import admin
        from django.test import RequestFactory

        self.order.status = "shipped"
        request = RequestFactory().post("/admin/store/order/")
        request.user = self.staff
        with self.captureOnCommitCallbacks(execute=True):
            admin.site._registry[Order].save_model(request, self.order, form=None, change=True)

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("shipped", mail.outbox[0].subject.lower())

    def test_generated_order_number_retries_a_unique_collision(self):
        first = Order.objects.create(full_name="First", phone="03001234567", address="Road", city="Lahore")
        second = Order(full_name="Second", phone="03001234567", address="Road", city="Lahore")
        with patch("random.randint", side_effect=[int(first.number[-4:]), int(first.number[-4:]), 9876]):
            second.save()
        self.assertNotEqual(first.number, second.number)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class CouponAndNewsletterTests(TestCase):
    def setUp(self):
        self.customer = get_user_model().objects.create_user(
            username="coupon-customer", email="coupon@example.com", password="test-password-123",
        )
        self.category = Category.objects.create(name="Coupon test category")
        self.product = Product.objects.create(
            name="Coupon tee", category=self.category, price=3000,
            image="products/coupon-tee.jpg", stock_qty=10,
        )

    def add_to_cart(self, qty=1):
        session = self.client.session
        session["markx_cart"] = {
            f"{self.product.pk}|M|Black": {"pid": self.product.pk, "size": "M", "color": "Black", "qty": qty},
        }
        session.save()

    def checkout(self, payment, code):
        self.add_to_cart()
        if payment == "cod":
            session = self.client.session
            session["verified_cod_phone"] = "03001234567"
            session.save()
        return self.client.post(reverse("store:checkout"), {
            "full_name": "Coupon Customer", "phone": "03001234567", "email": "coupon@example.com",
            "address": "1 Main Street", "city": "Lahore", "payment_method": payment,
            "promo_code": code,
        })

    def test_gift_card_balance_is_locked_and_applied_to_order(self):
        self.client.force_login(self.customer)
        self.add_to_cart()
        gift = GiftCard.objects.create(code="MX-GIFT-1", initial_balance=500, balance=500)
        session = self.client.session
        session["verified_cod_phone"] = "03001234567"
        session.save()
        response = self.client.post(reverse("store:checkout"), {
            "full_name": "Coupon Customer", "phone": "03001234567", "email": "coupon@example.com",
            "address": "1 Main Street", "city": "Lahore", "payment_method": "cod",
            "gift_card_code": gift.code,
        })
        order = Order.objects.get(user=self.customer)
        gift.refresh_from_db()
        self.assertRedirects(response, reverse("store:order_success", args=[order.number]))
        self.assertEqual(gift.balance, 0)
        self.assertEqual(GiftCardUse.objects.get(order=order).amount, 500)

    def test_newsletter_signup_creates_unique_single_use_coupon_and_emails_it(self):
        response = self.client.post(
            reverse("store:newsletter"), {"email": "subscriber@example.com"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        payload = response.json()
        coupon = Coupon.objects.get(code=payload["coupon_code"])

        self.assertTrue(payload["ok"])
        self.assertEqual(coupon.percent, 15)
        self.assertTrue(coupon.single_use)
        self.assertTrue(coupon.is_usable)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(coupon.code, mail.outbox[0].body)

        self.client.post(reverse("store:newsletter"), {"email": "another@example.com"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(Coupon.objects.count(), 2)
        self.assertEqual(Coupon.objects.values_list("code", flat=True).distinct().count(), 2)

    def test_larger_coupon_discount_wins_without_stacking_and_is_stored(self):
        self.client.force_login(self.customer)
        coupon = Coupon.objects.create(code="big-save", percent=20)

        response = self.checkout("card", "BIG-SAVE")
        order = Order.objects.get(user=self.customer)

        self.assertRedirects(response, reverse("store:order_success", args=[order.number]))
        self.assertEqual(order.discount, 600)
        self.assertEqual(order.coupon_code, "BIG-SAVE")
        self.assertEqual(coupon.__class__.objects.get(pk=coupon.pk).used_count, 1)
        self.assertIn("Promo code BIG-SAVE", mail.outbox[0].body)

    def test_card_discount_wins_and_single_use_coupon_is_not_consumed(self):
        self.client.force_login(self.customer)
        coupon = Coupon.objects.create(code="small-save", percent=10)

        response = self.checkout("card", "SMALL-SAVE")
        order = Order.objects.get(user=self.customer)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(order.discount, 450)
        self.assertEqual(order.coupon_code, "")
        coupon.refresh_from_db()
        self.assertEqual(coupon.used_count, 0)

    def test_coupon_expiry_and_single_use_are_checked(self):
        from django.utils import timezone
        from datetime import timedelta

        expired = Coupon.objects.create(code="expired", expires_at=timezone.now() - timedelta(days=1))
        used = Coupon.objects.create(code="used", used_count=1, single_use=True)
        self.assertFalse(expired.is_usable)
        self.assertFalse(used.is_usable)
        from django.contrib import admin
        self.assertIn(Coupon, admin.site._registry)

    def test_invalid_or_used_coupon_is_rejected_by_checkout_form(self):
        from .forms import CheckoutForm

        Coupon.objects.create(code="already-used", used_count=1)
        form = CheckoutForm(data={
            "full_name": "Coupon Customer", "phone": "03001234567", "email": "coupon@example.com",
            "address": "1 Main Street", "city": "Lahore", "payment_method": "cod",
            "promo_code": "already-used",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("promo_code", form.errors)


class ReviewAndWishlistTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.customer = user_model.objects.create_user(
            username="review-customer", email="review@example.com", password="test-password-123",
        )
        self.other_customer = user_model.objects.create_user(
            username="other-customer", password="test-password-123",
        )
        self.category = Category.objects.create(name="Review test category")
        self.product = Product.objects.create(
            name="Review tee", category=self.category, price=1200,
            image="products/review-tee.jpg", rating="4.2", reviews=17,
        )

    def delivered_order(self, user):
        order = Order.objects.create(
            user=user, full_name="Review Customer", phone="03001234567",
            address="1 Road", city="Lahore", status="delivered",
        )
        OrderItem.objects.create(
            order=order, product=self.product, name=self.product.name,
            size="M", color="Black", price=1200, qty=1,
        )
        return order

    def test_only_delivered_buyers_can_submit_one_review_and_approval_updates_rating(self):
        self.client.force_login(self.customer)
        url = reverse("store:submit_review", args=[self.product.slug])
        response = self.client.post(url, {"rating": "5", "comment": "Great quality"})
        self.assertRedirects(response, self.product.get_absolute_url())
        self.assertFalse(Review.objects.exists())

        self.delivered_order(self.customer)
        self.client.post(url, {"rating": "5", "comment": "Great quality"})
        review = Review.objects.get(product=self.product, user=self.customer)
        self.product.refresh_from_db()
        self.assertFalse(review.approved)
        self.assertEqual(self.product.rating, Decimal("4.2"))
        self.assertEqual(self.product.reviews, 17)
        self.assertNotContains(self.client.get(self.product.get_absolute_url()), "Great quality")

        review.approved = True
        review.save()
        self.product.refresh_from_db()
        self.assertEqual(self.product.rating, Decimal("5.0"))
        self.assertEqual(self.product.reviews, 1)
        self.assertContains(self.client.get(self.product.get_absolute_url()), "Great quality")

        self.client.post(url, {"rating": "4", "comment": "Second review"})
        self.assertEqual(Review.objects.filter(product=self.product, user=self.customer).count(), 1)

    def test_removing_last_approved_review_restores_manual_product_rating(self):
        self.delivered_order(self.customer)
        review = Review.objects.create(product=self.product, user=self.customer, rating=3, comment="Okay")
        review.approved = True
        review.save()
        review.delete()
        self.product.refresh_from_db()
        self.assertEqual(self.product.rating, Decimal("4.2"))
        self.assertEqual(self.product.reviews, 17)

    def test_wishlist_toggle_page_and_guest_merge_use_account_storage(self):
        self.client.force_login(self.customer)
        toggle_url = reverse("store:wishlist_toggle", args=[self.product.pk])
        added = self.client.post(toggle_url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertTrue(added.json()["in_wishlist"])
        self.assertTrue(Wishlist.objects.filter(user=self.customer, product=self.product).exists())
        page = self.client.get(reverse("store:wishlist"))
        self.assertContains(page, "Review tee")
        self.assertContains(page, "data-authenticated=\"true\"")

        merged = self.client.post(
            reverse("store:wishlist_merge"), data=json.dumps({"ids": [self.product.pk, self.product.pk, 999]}),
            content_type="application/json",
        )
        self.assertTrue(merged.json()["ok"])
        self.assertEqual(Wishlist.objects.filter(user=self.customer, product=self.product).count(), 1)

        removed = self.client.post(toggle_url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertFalse(removed.json()["in_wishlist"])
        self.assertFalse(Wishlist.objects.filter(user=self.customer, product=self.product).exists())

    def test_wishlist_is_private_and_requires_login(self):
        Wishlist.objects.create(user=self.customer, product=self.product)
        self.client.force_login(self.other_customer)
        response = self.client.get(reverse("store:wishlist"))
        self.assertNotContains(response, "Review tee")

        self.client.logout()
        response = self.client.get(reverse("store:wishlist"))
        self.assertEqual(response.status_code, 302)


class ProductionAndSeoTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="SEO category")
        self.product = Product.objects.create(
            name="SEO Tee", category=self.category, price=1800,
            image="products/seo-tee.jpg", active=True, stock_qty=3,
        )

    def test_sitemap_and_robots_include_public_routes_and_active_products(self):
        hidden = Product.objects.create(
            name="Hidden Tee", category=self.category, price=900,
            image="products/hidden-tee.jpg", active=False,
        )
        sitemap = self.client.get(reverse("sitemap"))
        self.assertEqual(sitemap.status_code, 200)
        self.assertContains(sitemap, self.product.get_absolute_url())
        self.assertNotContains(sitemap, hidden.get_absolute_url())
        self.assertContains(sitemap, "/about/")

        robots = self.client.get(reverse("robots_txt"))
        self.assertEqual(robots.status_code, 200)
        self.assertEqual(robots["Content-Type"].split(";")[0], "text/plain")
        self.assertContains(robots, "/sitemap.xml")
        self.assertContains(robots, "Disallow: /admin/")

    def test_product_page_has_open_graph_and_product_json_ld(self):
        response = self.client.get(self.product.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'property="og:image"')
        self.assertContains(response, '"priceCurrency": "PKR"')
        self.assertContains(response, "schema.org/InStock")
        self.assertContains(response, '"@type": "Product"')

    def test_cart_and_newsletter_reject_external_redirect_targets(self):
        cart_response = self.client.post(reverse("store:cart_add", args=[self.product.pk]), {
            "size": "M", "color": "Black", "next": "https://evil.example/",
        })
        self.assertRedirects(cart_response, reverse("store:cart"))

        with self.settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
            newsletter_response = self.client.post(
                reverse("store:newsletter"), {"email": "seo@example.com"},
                HTTP_REFERER="https://evil.example/path",
            )
        self.assertRedirects(newsletter_response, reverse("store:home"))

    def _run_settings(self, overrides):
        env = os.environ.copy()
        for key in ("DJANGO_SECRET_KEY", "DJANGO_ALLOWED_HOSTS", "DJANGO_DEBUG", "SECURE_SSL_REDIRECT",
                    "SESSION_COOKIE_SECURE", "CSRF_COOKIE_SECURE", "SECURE_HSTS_SECONDS", "DB_ENGINE",
                    "DB_NAME", "DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT"):
            env.pop(key, None)
        env.update(overrides)
        code = "import json, runpy; s=runpy.run_path('markx/settings.py'); print(json.dumps({'hosts': s['ALLOWED_HOSTS'], 'ssl': s['SECURE_SSL_REDIRECT'], 'session': s['SESSION_COOKIE_SECURE'], 'csrf': s['CSRF_COOKIE_SECURE'], 'hsts': s['SECURE_HSTS_SECONDS'], 'validators': len(s['AUTH_PASSWORD_VALIDATORS']), 'engine': s['DATABASES']['default']['ENGINE'], 'name': str(s['DATABASES']['default'].get('NAME'))}))"
        return subprocess.run(
            [sys.executable, "-c", code], cwd=os.path.dirname(os.path.dirname(__file__)),
            env=env, text=True, capture_output=True,
        )

    def test_production_requires_secret_and_explicit_allowed_hosts(self):
        missing_secret = self._run_settings({"DJANGO_DEBUG": "0"})
        self.assertNotEqual(missing_secret.returncode, 0)
        self.assertIn("DJANGO_SECRET_KEY is required", missing_secret.stderr)

        missing_hosts = self._run_settings({"DJANGO_DEBUG": "0", "DJANGO_SECRET_KEY": "test-secret"})
        self.assertNotEqual(missing_hosts.returncode, 0)
        self.assertIn("DJANGO_ALLOWED_HOSTS", missing_hosts.stderr)

    def test_production_security_defaults_and_optional_postgres_settings(self):
        configured = self._run_settings({
            "DJANGO_DEBUG": "0", "DJANGO_SECRET_KEY": "test-secret", "DJANGO_ALLOWED_HOSTS": "shop.example, www.shop.example",
        })
        self.assertEqual(configured.returncode, 0, configured.stderr)
        values = json.loads(configured.stdout)
        self.assertEqual(values["hosts"], ["shop.example", "www.shop.example"])
        self.assertTrue(values["ssl"] and values["session"] and values["csrf"])
        self.assertGreater(values["hsts"], 0)
        self.assertEqual(values["validators"], 4)

        postgres = self._run_settings({
            "DJANGO_DEBUG": "1", "DB_ENGINE": "postgresql", "DB_NAME": "markx",
            "DB_USER": "markx", "DB_PASSWORD": "secret", "DB_HOST": "db", "DB_PORT": "5432",
        })
        self.assertEqual(postgres.returncode, 0, postgres.stderr)
        db_values = json.loads(postgres.stdout)
        self.assertEqual(db_values["engine"], "django.db.backends.postgresql")
        self.assertEqual(db_values["name"], "markx")
