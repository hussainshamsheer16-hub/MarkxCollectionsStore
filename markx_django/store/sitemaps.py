from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from .models import Product


class StaticViewSitemap(Sitemap):
    priority = 0.6
    changefreq = "weekly"

    def items(self):
        return ("store:home", "store:shop", "store:about", "store:contact", "store:customize", "store:bulk", "store:track_order")

    def location(self, item):
        return reverse(item)


class ProductSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.8

    def items(self):
        return Product.objects.storefront()

    def lastmod(self, item):
        return item.created


sitemaps = {"static": StaticViewSitemap, "products": ProductSitemap}
