# MarkX Collections — Django store

## Local setup

```bash
python -m venv venv && source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed
python manage.py createsuperuser
python manage.py runserver
```

The seed command creates men's catalog products. Active men's products appear in the storefront; products from other collections and products in the Hoodies or Jackets categories remain in the database but are inactive. Add and activate eligible inventory through Django Admin. Seeded stock starts at 10 units per product; update actual inventory in Admin before taking orders.

- Store: http://127.0.0.1:8000/
- Admin: http://127.0.0.1:8000/admin/
- Staff dashboard: http://127.0.0.1:8000/dashboard/
- Sitemap: http://127.0.0.1:8000/sitemap.xml
- Robots: http://127.0.0.1:8000/robots.txt

## Store features

- Shop filters for category, size, color, and sorting, with pagination.
- Product fit, fabric, care, size guides, availability, and related product suggestions.
- Cart and checkout with stock validation, order confirmation, status emails, and order tracking by order number and Pakistani phone number.
- Newsletter signup coupons and checkout coupon codes. Coupon discounts are compared with the card payment discount; they do not stack.
- Customer accounts, wishlists, and purchase verified reviews. Reviews require staff approval before appearing or changing the product rating.
- Product/category and order management in Admin; low stock appears on the staff dashboard.

## Images

Admin → Products → open a product → upload `image` (main), `image2` (hover/back), and optionally `image3`. Replace demo/placeholder art with approved product photography before launch.

## Email

Order status, order confirmation, and newsletter coupon emails use Django's configured email backend. For SMTP, set `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` or `EMAIL_USE_SSL`, and `DEFAULT_FROM_EMAIL` in the environment. Keep credentials out of source control. Delivery failures are logged; they do not cancel an order.

## Production configuration

Set `DJANGO_DEBUG=0`, `DJANGO_SECRET_KEY`, and comma-separated `DJANGO_ALLOWED_HOSTS`. Production enables HTTPS redirects, secure session/CSRF cookies, and HSTS by default. Configure HTTPS at the hosting proxy and review the related Django security settings for that deployment. Static files should be collected with `python manage.py collectstatic`; serve media through the chosen web server or object storage.

SQLite is used by default. To use PostgreSQL, install `psycopg[binary]` and set `DB_ENGINE=postgresql`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, and `DB_PORT` (or the matching `POSTGRES_*` variables).

## Database and checks

Apply schema changes with `python manage.py migrate`. Run the full automated suite with `python manage.py test`; verify configuration with `python manage.py check` and `python manage.py makemigrations --check`.

## Customer features and deployment setup

- The storefront language control is in the header. English is the default; Urdu uses a right-to-left layout. Product descriptions and customer-entered content remain as entered.
- COD checkout requires a verified phone when SMS OTP settings are configured. The SMS endpoint must accept JSON `{ "to": "...", "message": "..." }` with a Bearer token.
- Back-in-stock email uses Django's configured email backend. WhatsApp sends the generic JSON payload `{ "to": "...", "text": "...", "customer_name": "..." }` with a Bearer token; adapt the payload to the provider's API.
- Loyalty points are earned on delivered orders, can be redeemed in checkout, and referral rewards trigger when a referred account's first order is delivered. Gift cards are managed in Django Admin.
- Staff can preview and import inventory CSVs from Dashboard → Staff workspace → Import inventory CSV. Required columns: `product_slug,size,color,stock_qty`; `sku` is optional. Product/order/variant CSV exports and invoice/packing-slip PDF actions are available in Django Admin.
- Abandoned-cart email reminders are one-shot and only sent to logged-in customers with email. Schedule `python manage.py send_abandoned_cart_reminders` at an interval appropriate for `ABANDONED_CART_HOURS` (default 24); for example, run it hourly with the host's scheduler.

Additional environment settings:

| Setting | Purpose |
| --- | --- |
| `OTP_SMS_API_URL`, `OTP_SMS_TOKEN` | SMS endpoint and bearer token for COD OTP |
| `WHATSAPP_PROVIDER`, `WHATSAPP_TOKEN`, `WHATSAPP_API_URL`, `WHATSAPP_OWNER_PHONE` | WhatsApp provider endpoint, token, and store-owner notification number |
| `ABANDONED_CART_HOURS` | Minimum cart age before reminders (default `24`) |
| `LOYALTY_POINTS_PER_1000`, `LOYALTY_RUPEES_PER_POINT`, `REFERRAL_REWARD_POINTS` | Loyalty and referral reward values |

Install the updated `requirements.txt` to add ReportLab for PDF documents, then apply migrations in the deployment environment. The JazzCash, Easypaisa, and card classes remain configuration scaffolding; merchant credentials alone do not enable live transactions. Implement and sandbox-test the provider-specific request, signature, return, and webhook flows before enabling live payments.
