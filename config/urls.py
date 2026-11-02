from django.contrib import admin
from django.urls import path
from crmapp.views import (
    dashboard_stats, revenue_chart, weekly_sales, stock_overview,
    recent_sales, low_stock_products, shop_summary,
    product_header, export_products_excel, product_stats, product_list, products, product_detail, product_by_barcode,
    top_products, category_breakdown, today_performance, ai_recommendations,
    billing_products, create_sale, check_payment_status, simulate_test_payment, cancel_pending_sale, razorpay_webhook,
    expiry_alerts, sales_page_data, reports_page_data,
    login_api, settings_api,
    request_otp_api, verify_otp_api, reset_password_api,
    chatbot_api, ai_forecast_api
)

urlpatterns = [
    path("admin/", admin.site.urls),

    path("api/chatbot/", chatbot_api, name="chatbot-api"),
    path("api/ai-forecast/", ai_forecast_api, name="ai-forecast-api"),
    path("api/dashboard/", dashboard_stats),
    path("api/revenue-chart/", revenue_chart),
    path("api/weekly-sales/", weekly_sales),
    path("api/stock-overview/", stock_overview),
    path("api/dashboard/recent-sales/", recent_sales),
    path("api/dashboard/low-stock/", low_stock_products),
    path("api/dashboard/shop-summary/", shop_summary),
    path("api/dashboard/top-products/", top_products),
    path("api/dashboard/category-breakdown/", category_breakdown),
    path("api/dashboard/today-performance/", today_performance),
    path("api/dashboard/ai-recommendations/", ai_recommendations),

    path("api/products/header/", product_header),
    path("api/products/stats/", product_stats),
    path("api/products/list/", product_list),
    path("api/products/export/", export_products_excel),
    path("api/products/barcode/<str:barcode>/", product_by_barcode),
    path("api/products/barcode/", product_by_barcode),
    path("api/products/", products),
    path("api/products/<int:pk>/", product_detail),

    # Billing & Razorpay QR Payments
    path("api/billing/products/", billing_products, name="billing-products"),
    path("api/billing/sales/", create_sale, name="billing-create-sale"),
    path("api/billing/check-payment/<str:bill_no>/", check_payment_status, name="billing-check-payment"),
    path("api/billing/simulate-payment/", simulate_test_payment, name="billing-simulate-payment"),
    path("api/billing/cancel-sale/", cancel_pending_sale, name="billing-cancel-sale"),
    path("api/billing/razorpay-webhook/", razorpay_webhook, name="billing-razorpay-webhook"),

    path("expiry-alerts/", expiry_alerts),
    path("api/sales/page-data/", sales_page_data),
    path("api/reports/page-data/", reports_page_data),
    path("api/login/", login_api),
    path("api/settings/", settings_api),

    # Password Reset & Email OTP Routes
    path("api/password-reset/request-otp/", request_otp_api),
    path("api/password-reset/verify-otp/", verify_otp_api),
    path("api/password-reset/confirm/", reset_password_api),
]
