import uuid

from django.test import TestCase

from .models import Product, ProductVariant


class VariantAndSizingFeatureTests(TestCase):
    def setUp(self):
        self.category = self._create_category()
        self.product = Product.objects.create(
            name=f"Variant Tee {uuid.uuid4().hex[:6]}",
            slug=f"variant-tee-{uuid.uuid4().hex[:8]}",
            category=self.category,
            price=2500,
            old_price=3000,
            colors="Black, White",
            sizes="S, M, L",
            stock_qty=10,
            active=True,
            image="products/test-tee.jpg",
        )

    @staticmethod
    def _create_category():
        from .models import Category

        unique = uuid.uuid4().hex[:8]
        return Category.objects.create(name=f"Shirts {unique}", slug=f"shirts-{unique}")

    def test_product_variant_creation_and_lookup(self):
        variant = ProductVariant.objects.create(
            product=self.product,
            size="M",
            color="Black",
            stock_qty=5,
            active=True,
            sku="VT-TEE-M-BLK",
        )

        self.assertEqual(self.product.get_variant("M", "Black"), variant)
        self.assertEqual(self.product.get_available_stock("M", "Black"), 5)
        self.assertEqual(self.product.get_available_stock("M", "White"), self.product.stock_qty)

    def test_size_recommender_returns_recommendation_for_common_measurements(self):
        self.assertEqual(self.product.recommend_size(height=176, weight=70, fit="regular"), "M")
