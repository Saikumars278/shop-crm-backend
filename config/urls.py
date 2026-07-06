from django.contrib import admin
from django.urls import path
from crmapp.views import (
    dashboard_stats, revenue_chart, weekly_sales, stock_overview,
    recent_sales, low_stock_products, shop_summary,
    product_header, export_products_excel, product_stats, product_list, products, product_detail,
    top_products, category_breakdown, today_performance,
    billing_products, create_sale, expiry_alerts, sales_page_data, reports_page_data,
    login_api, settings_api
)

urlpatterns = [
    path("admin/", admin.site.urls),

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

    path("api/products/header/", product_header),
    path("api/products/stats/", product_stats),
    path("api/products/list/", product_list),
    path("api/products/export/", export_products_excel),
    path("api/products/", products),
    path("api/products/<int:pk>/", product_detail),

    # Billing counter (BillingPage.jsx). Kept under /api/billing/ so these
    # can never collide with the product-management routes above —
    # `api/products/` is already taken by the `products` view.
    path("api/billing/products/", billing_products, name="billing-products"),
    path("api/billing/sales/", create_sale, name="billing-create-sale"),
    path("expiry-alerts/", expiry_alerts),
    path("api/sales/page-data/", sales_page_data),
    path("api/reports/page-data/", reports_page_data),
    path("api/login/", login_api),
    path("api/settings/", settings_api),
]