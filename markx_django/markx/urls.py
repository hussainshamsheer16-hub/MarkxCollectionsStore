from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path
from store.sitemaps import sitemaps
from store.views import robots_txt

admin.site.site_header = "MarkX Collections Admin"
admin.site.site_title = "MarkX Admin"
admin.site.index_title = "Store dashboard"

urlpatterns = [
    path("sitemap.xml", sitemap, {"sitemaps": sitemaps}, name="sitemap"),
    path("robots.txt", robots_txt, name="robots_txt"),
    path("admin/", admin.site.urls),
    path("", include("store.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
