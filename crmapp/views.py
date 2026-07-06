import calendar
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import (
    Avg,
    Count,
    DecimalField,
    ExpressionWrapper,
    F,
    Q,
    Sum,
)
from django.db.models.functions import Coalesce, TruncDate, TruncMonth
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from openpyxl import Workbook
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import LOW_STOCK_THRESHOLD, Product, Sale, SaleItem, ShopTarget
from .serializers import ProductSerializer


def calculate_growth(current, previous):
    current = float(current or 0)
    previous = float(previous or 0)

    if previous == 0:
        return 100 if current > 0 else 0

    return round(((current - previous) / previous) * 100, 2)

@api_view(["GET"])
def dashboard_stats(request):
    today = timezone.localdate()
    yesterday = today - timedelta(days=1)

    # -------------------------------
    # Product Statistics
    # -------------------------------

    total_products = Product.objects.count()

    total_stock_units = Product.objects.aggregate(
        total=Coalesce(Sum("stock"), 0)
    )["total"]

    low_stock_count = Product.objects.filter(
        stock__gt=0,
        stock__lte=LOW_STOCK_THRESHOLD
    ).count()

    out_of_stock = Product.objects.filter(
        stock=0
    ).count()

    stock_value = Product.objects.aggregate(
        total=Coalesce(
            Sum(
                ExpressionWrapper(
                    F("sell_price") * F("stock"),
                    output_field=DecimalField(
                        max_digits=15,
                        decimal_places=2
                    )
                )
            ),
            Decimal("0.00")
        )
    )["total"]

    # -------------------------------
    # Today's Sales
    # -------------------------------

    today_sales = Sale.objects.filter(
        created_at__date=today
    ).aggregate(
        total=Coalesce(Sum("total"), Decimal("0.00"))
    )["total"]

    yesterday_sales = Sale.objects.filter(
        created_at__date=yesterday
    ).aggregate(
        total=Coalesce(Sum("total"), Decimal("0.00"))
    )["total"]

    today_bill_count = Sale.objects.filter(
        created_at__date=today
    ).count()

    average_bill = Sale.objects.filter(
        created_at__date=today
    ).aggregate(
        avg=Coalesce(Avg("total"), Decimal("0.00"))
    )["avg"]

    # -------------------------------
    # Monthly Revenue
    # -------------------------------

    monthly_revenue = Sale.objects.filter(
        created_at__year=today.year,
        created_at__month=today.month
    ).aggregate(
        total=Coalesce(Sum("total"), Decimal("0.00"))
    )["total"]

    if today.month == 1:
        prev_month = 12
        prev_year = today.year - 1
    else:
        prev_month = today.month - 1
        prev_year = today.year

    previous_month_revenue = Sale.objects.filter(
        created_at__year=prev_year,
        created_at__month=prev_month
    ).aggregate(
        total=Coalesce(Sum("total"), Decimal("0.00"))
    )["total"]

    # -------------------------------
    # Profit Calculation
    # -------------------------------

    today_profit = SaleItem.objects.filter(
        sale__created_at__date=today
    ).aggregate(
        total=Coalesce(
            Sum(
                ExpressionWrapper(
                    (F("price") - F("product__buy_price")) * F("quantity"),
                    output_field=DecimalField(
                        max_digits=15,
                        decimal_places=2
                    )
                )
            ),
            Decimal("0.00")
        )
    )["total"]

    monthly_profit = SaleItem.objects.filter(
        sale__created_at__year=today.year,
        sale__created_at__month=today.month
    ).aggregate(
        total=Coalesce(
            Sum(
                ExpressionWrapper(
                    (F("price") - F("product__buy_price")) * F("quantity"),
                    output_field=DecimalField(
                        max_digits=15,
                        decimal_places=2
                    )
                )
            ),
            Decimal("0.00")
        )
    )["total"]

    # -------------------------------
    # Growth
    # -------------------------------

    sales_growth = calculate_growth(
        today_sales,
        yesterday_sales
    )

    revenue_growth = calculate_growth(
        monthly_revenue,
        previous_month_revenue
    )

    product_growth = 0
    stock_growth = 0

    # -------------------------------
    # Response
    # -------------------------------

    return Response({
        "total_products": total_products,
        "stock_value": float(stock_value),
        "today_sales": float(today_sales),
        "revenue": float(monthly_revenue),

        "product_growth": product_growth,
        "stock_growth": stock_growth,
        "sales_growth": sales_growth,
        "revenue_growth": revenue_growth,

        "total_stock_units": total_stock_units,
        "low_stock_count": low_stock_count,
        "out_of_stock": out_of_stock,

        "today_bill_count": today_bill_count,
        "average_bill": float(average_bill),

        "today_profit": float(today_profit),
        "monthly_profit": float(monthly_profit),

        "last_updated": timezone.now().strftime("%I:%M %p"),
    })


@api_view(["GET"])
def revenue_chart(request):

    today = timezone.localdate()

    # Current month start
    current_month = date(today.year, today.month, 1)

    # Last 12 months labels
    months = []
    month_map = {}

    year = current_month.year
    month = current_month.month

    for i in range(11, -1, -1):
        m = month - i
        y = year

        while m <= 0:
            m += 12
            y -= 1

        month_start = date(y, m, 1)
        label = month_start.strftime("%b")

        months.append({
            "date": month_start,
            "month": label,
            "revenue": 0
        })

        month_map[(y, m)] = len(months) - 1

    # Revenue grouped by Month + Year
    revenue_data = (
        Sale.objects
        .annotate(month=TruncMonth("created_at"))
        .values("month")
        .annotate(
            revenue=Coalesce(
                Sum("total"),
                Decimal("0.00")
            )
        )
        .order_by("month")
    )

    # Fill revenues
    for row in revenue_data:

        month_date = row["month"].date()

        key = (
            month_date.year,
            month_date.month
        )

        if key in month_map:
            index = month_map[key]

            months[index]["revenue"] = float(
                row["revenue"]
            )

    chart = [
        {
            "month": item["month"],
            "revenue": item["revenue"]
        }
        for item in months
    ]

    # Totals
    total_revenue = float(
        Sale.objects.aggregate(
            total=Coalesce(
                Sum("total"),
                Decimal("0.00")
            )
        )["total"]
    )

    current_revenue = chart[-1]["revenue"]
    previous_revenue = chart[-2]["revenue"]

    if previous_revenue > 0:
        growth = round(
            (
                (current_revenue - previous_revenue)
                / previous_revenue
            ) * 100,
            1
        )
    elif current_revenue > 0:
        growth = 100
    else:
        growth = 0

    difference = current_revenue - previous_revenue

    return Response({
        "total_revenue": total_revenue,
        "current_month": current_revenue,
        "previous_month": previous_revenue,
        "difference": difference,
        "growth": growth,
        "chart": chart,
    })


@api_view(["GET"])
def weekly_sales(request):
    today = timezone.localdate()
    start_date = today - timedelta(days=6)
    prev_start_date = start_date - timedelta(days=7)
    prev_end_date = start_date - timedelta(days=1)

    sales = (
        Sale.objects
        .filter(created_at__date__gte=start_date, created_at__date__lte=today)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(sales=Sum("total"))
        .order_by("day")
    )

    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    chart = []

    for item in sales:
        chart.append({
            "day": day_names[item["day"].weekday()],
            "sales": float(item["sales"] or 0),
        })

    total_sales = sum(item["sales"] for item in chart)

    if chart:
        highest_sale = max(chart, key=lambda x: x["sales"])
    else:
        highest_sale = {
            "day": "-",
            "sales": 0,
        }

    # Real week-over-week growth instead of a hardcoded value.
    previous_week_total = float(
        Sale.objects.filter(
            created_at__date__gte=prev_start_date,
            created_at__date__lte=prev_end_date,
        ).aggregate(total=Coalesce(Sum("total"), Decimal("0.00")))["total"]
    )

    if previous_week_total > 0:
        growth = round(
            ((total_sales - previous_week_total) / previous_week_total) * 100,
            1,
        )
    else:
        growth = 100 if total_sales > 0 else 0

    return Response({
        "total_sales": total_sales,
        "highest_sale": highest_sale,
        "growth": growth,
        "chart": chart,
    })


@api_view(["GET"])
def stock_overview(request):
    available = Product.objects.filter(stock__gt=LOW_STOCK_THRESHOLD).count()
    low_stock = Product.objects.filter(stock__gt=0, stock__lte=LOW_STOCK_THRESHOLD).count()
    out_of_stock = Product.objects.filter(stock=0).count()

    total_stock = Product.objects.aggregate(
        total=Sum("stock")
    )["total"] or 0

    total_products = Product.objects.count()

    utilization = round(
        (available / total_products) * 100, 1
    ) if total_products else 0

    stock_alert = low_stock + out_of_stock

    chart = [
        {"name": "Available", "value": available},
        {"name": "Low Stock", "value": low_stock},
        {"name": "Out of Stock", "value": out_of_stock},
    ]

    return Response({
        "available": available,
        "low_stock": low_stock,
        "out_of_stock": out_of_stock,
        "total_stock": total_stock,
        "utilization": utilization,
        "stock_alert": stock_alert,
        "status": "Healthy Inventory" if utilization >= 80 else "Low Inventory",
        "chart": chart,
    })


@api_view(["GET"])
def recent_sales(request):

    today = timezone.localdate()

    search = request.GET.get("search", "")
    sort = request.GET.get("sort", "date_desc")
    page = int(request.GET.get("page", 1))
    per_page = 5

    # CURRENT MONTH SALES ONLY
    sales = Sale.objects.filter(
        created_at__year=today.year,
        created_at__month=today.month
    ).prefetch_related("items__product")

    # Search
    if search:
        sales = sales.filter(
            Q(bill_no__icontains=search) |
            Q(items__product__name__icontains=search) |
            Q(status__icontains=search) |
            Q(payment_method__icontains=search)
        ).distinct()

    # Sorting
    if sort == "date_desc":
        sales = sales.order_by("-created_at")
    elif sort == "date_asc":
        sales = sales.order_by("created_at")
    elif sort == "amount_desc":
        sales = sales.order_by("-total")
    elif sort == "amount_asc":
        sales = sales.order_by("total")
    elif sort == "status":
        sales = sales.order_by("status")
    else:
        sales = sales.order_by("-created_at")

    # Summary
    total_bills = sales.count()

    total_revenue = (
        sales.aggregate(total=Sum("total"))["total"]
        or Decimal("0.00")
    )

    pending_payments = (
        sales.filter(status="Pending")
        .aggregate(total=Sum("total"))["total"]
        or Decimal("0.00")
    )

    average_bill = (
        total_revenue / total_bills
        if total_bills > 0
        else Decimal("0.00")
    )

    # Pagination
    total_pages = (total_bills + per_page - 1) // per_page

    start = (page - 1) * per_page
    end = start + per_page

    paginated_sales = sales[start:end]

    result = []

    for sale in paginated_sales:

        items = list(sale.items.all())

        if items:
            product_name = items[0].product.name

            if len(items) > 1:
                product_name += f" + {len(items)-1} more"

        else:
            product_name = ""

        item_list = [
            {
                "name": item.product.name,
                "qty": item.quantity,
                "price": float(item.price),
            }
            for item in items
        ]

        total_qty = sum(item.quantity for item in items)

        result.append({
            "id": sale.bill_no,
            "product": product_name,
            "items": item_list,
            "qty": total_qty,
            "amount": float(sale.total),
            "status": sale.status,
            "payment_method": sale.payment_method,
            "date": sale.created_at.strftime("%d-%m-%Y"),
            "time": sale.created_at.strftime("%I:%M %p"),
        })

    return Response({
        "summary": {
            "total_bills": total_bills,
            "total_revenue": float(total_revenue),
            "average_bill": float(average_bill),
            "pending_payments": float(pending_payments),
        },
        "sales": result,
        "pagination": {
            "current_page": page,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        }
    })


@api_view(["GET"])
def low_stock_products(request):
    page = int(request.GET.get("page", 1))
    per_page = 5

    products_qs = Product.objects.filter(stock__lte=LOW_STOCK_THRESHOLD).order_by("stock")

    all_data = []
    critical_count = 0

    for product in products_qs:
        item_status = "Critical" if product.stock <= 5 else "Low"

        if item_status == "Critical":
            critical_count += 1

        # Suggested restock qty: top back up to just above the threshold.
        suggested_restock = max(LOW_STOCK_THRESHOLD + 5 - product.stock, 1)

        all_data.append({
            "id": product.id,
            "name": product.name,
            "category": product.category,
            "stock": product.stock,
            "status": item_status,
            "unit": product.unit,
            "sell_price": float(product.sell_price),
            "buy_price": float(product.buy_price),
            "suggested_restock": suggested_restock,
        })

    total = len(all_data)
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1
    start = (page - 1) * per_page
    end = start + per_page
    paginated = all_data[start:end]

    return Response({
        "total": total,
        "critical": critical_count,
        "products": paginated,
        "pagination": {
            "current_page": page,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        }
    })


@api_view(["GET"])
def shop_summary(request):
    today = timezone.localdate()

    total_products = Product.objects.count()

    available_stock = Product.objects.aggregate(
        total=Sum("stock")
    )["total"] or 0

    low_stock_items = Product.objects.filter(stock__lte=LOW_STOCK_THRESHOLD).count()

    # "today_bills" now actually means today's bills, not all-time count.
    today_bills = Sale.objects.filter(created_at__date=today).count()

    total_revenue = Sale.objects.aggregate(
        total=Sum("total")
    )["total"] or 0

    return Response({
        "total_products": total_products,
        "available_stock": available_stock,
        "low_stock_items": low_stock_items,
        "today_bills": today_bills,
        "total_revenue": total_revenue,
    })


@api_view(["GET"])
def product_header(request):
    total_products = Product.objects.count()

    last_product = Product.objects.order_by("-id").first()

    if last_product:
        next_id = f"PRD{last_product.id + 1:03d}"
    else:
        next_id = "PRD001"

    return Response({
        "total_products": total_products,
        "next_id": next_id,
    })


def export_products_excel(request):
    wb = Workbook()
    ws = wb.active
    ws.title = "Products"

    ws.append([
        "ID",
        "Product Name",
        "Category",
        "Buy Price",
        "Sell Price",
        "Stock",
        "Created At",
    ])

    products_qs = Product.objects.all().order_by("id")

    for product in products_qs:
        ws.append([
            product.id,
            product.name,
            product.category,
            float(product.buy_price),
            float(product.sell_price),
            product.stock,
            product.created_at.strftime("%d-%m-%Y %H:%M"),
        ])

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = 'attachment; filename="products.xlsx"'

    wb.save(response)
    return response


@api_view(["GET"])
def product_stats(request):
    # Total Products
    total_products = Product.objects.count()

    # Available Products (In Stock) - now consistent with LOW_STOCK_THRESHOLD
    available_products = Product.objects.filter(
        status="In Stock"
    ).count()

    # Total Available Stock Quantity
    available_stock = (
        Product.objects.filter(status="In Stock")
        .aggregate(total=Sum("stock"))["total"] or 0
    )

    # Low Stock Products
    low_stock = Product.objects.filter(
        status="Low Stock"
    ).count()

    # Out of Stock Products
    out_of_stock = Product.objects.filter(
        status="Out of Stock"
    ).count()

    # Total Stock Quantity
    total_stock = (
        Product.objects.aggregate(total=Sum("stock"))["total"] or 0
    )

    # Progress Calculations
    product_progress = round(
        (available_products / total_products) * 100, 1
    ) if total_products else 0

    stock_progress = round(
        (available_stock / total_stock) * 100, 1
    ) if total_stock else 0

    low_progress = round(
        (low_stock / total_products) * 100, 1
    ) if total_products else 0

    out_progress = round(
        (out_of_stock / total_products) * 100, 1
    ) if total_products else 0

    return Response({
        "stats": [
            {
                "title": "Total Products",
                "value": total_products,
                "subtitle": "Inventory Items",
                "growth": f"{total_products} Products",
                "progress": f"{product_progress}%",
                "gradient": "from-blue-500 to-cyan-500",
                "light": "bg-blue-50",
                "text": "text-blue-600",
            },
            {
                "title": "Available Stock",
                "value": available_stock,
                "subtitle": "Ready to Sell",
                "growth": f"{available_products} Products",
                "progress": f"{stock_progress}%",
                "gradient": "from-green-500 to-emerald-500",
                "light": "bg-green-50",
                "text": "text-green-600",
            },
            {
                "title": "Low Stock",
                "value": low_stock,
                "subtitle": "Need Restocking",
                "growth": f"{low_stock} Products",
                "progress": f"{low_progress}%",
                "gradient": "from-orange-500 to-yellow-500",
                "light": "bg-orange-50",
                "text": "text-orange-600",
            },
            {
                "title": "Out of Stock",
                "value": out_of_stock,
                "subtitle": "Unavailable",
                "growth": f"{out_of_stock} Products",
                "progress": f"{out_progress}%",
                "gradient": "from-red-500 to-pink-500",
                "light": "bg-red-50",
                "text": "text-red-600",
            },
        ]
    })


@api_view(["GET"])
def product_list(request):
    """
    Full filterable/paginated product listing — used by the Product
    Management page (search, category filter, status filter, sorting).
    NOT the endpoint the billing page uses; see billing_products below.
    """
    search = request.GET.get("search", "")
    category = request.GET.get("category", "")
    status_filter = request.GET.get("status", "")
    sort = request.GET.get("sort", "Newest First")

    products_qs = Product.objects.all()

    # Search
    if search:
        products_qs = products_qs.filter(
            Q(name__icontains=search) |
            Q(category__icontains=search)
        )

    # Category
    if category and category != "All Categories":
        products_qs = products_qs.filter(category=category)

    # Status - uses the same threshold as the Product.save() status field
    if status_filter == "In Stock":
        products_qs = products_qs.filter(stock__gt=LOW_STOCK_THRESHOLD)

    elif status_filter == "Low Stock":
        products_qs = products_qs.filter(
            stock__gt=0,
            stock__lte=LOW_STOCK_THRESHOLD
        )

    elif status_filter == "Out of Stock":
        products_qs = products_qs.filter(stock=0)

    # Sorting
    if sort == "Newest First":
        products_qs = products_qs.order_by("-id")

    elif sort == "Oldest First":
        products_qs = products_qs.order_by("id")

    elif sort == "Name A-Z":
        products_qs = products_qs.order_by("name")

    elif sort == "Stock High-Low":
        products_qs = products_qs.order_by("-stock")

    elif sort == "Price High-Low":
        products_qs = products_qs.order_by("-sell_price")

    data = []

    for product in products_qs:

        if product.stock == 0:
            product_status = "Out of Stock"

        elif product.stock <= LOW_STOCK_THRESHOLD:
            product_status = "Low Stock"

        else:
            product_status = "In Stock"

        data.append({
            "id": product.id,
            "product_id": f"PRD{product.id:03d}",
            "name": product.name,
            "category": product.category,
            "buy_price": float(product.buy_price),
            "sell_price": float(product.sell_price),
            "stock": product.stock,
            "status": product_status,
            "unit": product.unit,
            "expiry_date": str(product.expiry_date) if product.expiry_date else None,
            "barcode": product.barcode,
            "created_at": product.created_at.strftime("%d-%m-%Y"),
        })

    categories = list(
        Product.objects.values_list(
            "category",
            flat=True
        ).distinct()
    )

    return Response({
        "count": len(data),
        "categories": categories,
        "products": data,
    })


@api_view(["GET", "POST"])
def products(request):

    # ---------------- GET PRODUCTS ----------------

    if request.method == "GET":

        search = request.GET.get("search", "")

        queryset = Product.objects.all().order_by("-id")

        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(category__icontains=search)
            )

        serializer = ProductSerializer(queryset, many=True)
        return Response(serializer.data)

    # ---------------- ADD PRODUCT ----------------

    data = request.data.copy()

    # Convert React field names
    if "buyPrice" in data:
        data["buy_price"] = data.pop("buyPrice")

    if "sellPrice" in data:
        data["sell_price"] = data.pop("sellPrice")

    serializer = ProductSerializer(data=data)

    if serializer.is_valid():
        serializer.save()

        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED
        )

    return Response(
        serializer.errors,
        status=status.HTTP_400_BAD_REQUEST
    )


@api_view(["GET", "PUT", "DELETE"])
def product_detail(request, pk):

    try:
        product = Product.objects.get(pk=pk)

    except Product.DoesNotExist:
        return Response(
            {"error": "Product not found"},
            status=status.HTTP_404_NOT_FOUND
        )

    # ---------------- GET ONE PRODUCT ----------------

    if request.method == "GET":
        serializer = ProductSerializer(product)
        return Response(serializer.data)

    # ---------------- UPDATE PRODUCT ----------------

    if request.method == "PUT":

        data = request.data.copy()

        if "buyPrice" in data:
            data["buy_price"] = data.pop("buyPrice")

        if "sellPrice" in data:
            data["sell_price"] = data.pop("sellPrice")

        serializer = ProductSerializer(
            product,
            data=data,
            partial=True
        )

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )

    # ---------------- DELETE PRODUCT ----------------

    product.delete()

    return Response(
        {"message": "Product deleted successfully"},
        status=status.HTTP_204_NO_CONTENT
    )


# ============================================================
# DASHBOARD WIDGETS
# ============================================================

@api_view(["GET"])
def top_products(request):

    today = timezone.localdate()

    results = (
        SaleItem.objects.filter(
            sale__created_at__year=today.year,
            sale__created_at__month=today.month
        )
        .values(
            "product__id",
            "product__name",
        )
        .annotate(
            total_qty=Sum("quantity"),
            total_revenue=Sum(
                ExpressionWrapper(
                    F("quantity") * F("price"),
                    output_field=DecimalField(
                        max_digits=15,
                        decimal_places=2
                    )
                )
            )
        )
        .order_by("-total_revenue")[:8]
    )

    if not results:
        return Response({"products": []})

    max_revenue = max(float(item["total_revenue"]) for item in results)

    products = []

    for index, item in enumerate(results, start=1):
        revenue = float(item["total_revenue"])

        products.append({
            "rank": index,
            "name": item["product__name"],
            "qty": item["total_qty"],
            "revenue": revenue,
            "bar_pct": round((revenue / max_revenue) * 100, 1),
        })

    return Response({
        "month": today.strftime("%B %Y"),
        "products": products
    })


@api_view(["GET"])
def category_breakdown(request):
    """Inventory value and count broken down by product category."""
    categories = (
        Product.objects
        .values("category")
        .annotate(
            count=Count("id"),
            stock_qty=Sum("stock"),
            inv_value=Sum(
                ExpressionWrapper(
                    F("sell_price") * F("stock"),
                    output_field=DecimalField(max_digits=15, decimal_places=2)
                )
            )
        )
        .order_by("-inv_value")
    )

    total_value = sum(c["inv_value"] or 0 for c in categories)

    colors = [
        "#10b981", "#3b82f6", "#f59e0b",
        "#ec4899", "#8b5cf6", "#14b8a6",
        "#6366f1", "#f43f5e"
    ]

    data = []
    for i, c in enumerate(categories):
        val = c["inv_value"] or 0
        data.append({
            "name": c["category"] or "Unknown",
            "count": c["count"],
            "stock_qty": c["stock_qty"] or 0,
            "inv_value": val,
            "pct": round((val / total_value) * 100, 1) if total_value else 0,
            "color": colors[i % len(colors)],
        })

    return Response({
        "categories": data,
        "total_value": total_value,
    })


# ============================================================
# MONTHLY TARGETS
# ============================================================

MONTHLY_REVENUE_TARGET = Decimal("800000.00")   # ₹8 Lakhs
MONTHLY_BILLS_TARGET = 750


from django.db.models import Sum, Count, Max, ExpressionWrapper, F, DecimalField
from django.db.models.functions import Coalesce
from decimal import Decimal
import calendar
from datetime import timedelta
from django.utils import timezone


@api_view(["GET"])
def today_performance(request):

    today = timezone.localdate()
    yesterday = today - timedelta(days=1)

    # =====================================================
    # SHOP TARGETS
    # =====================================================

    target, _ = ShopTarget.objects.get_or_create(pk=1)

    monthly_revenue_target = target.monthly_revenue_target
    monthly_bills_target = target.monthly_bill_target

    # =====================================================
    # MONTH DETAILS
    # =====================================================

    month_start = today.replace(day=1)

    days_in_month = calendar.monthrange(
        today.year,
        today.month
    )[1]

    remaining_days = max(
        days_in_month - today.day + 1,
        1
    )

    # =====================================================
    # MONTH PROGRESS
    # =====================================================

    month_progress = Sale.objects.filter(
        created_at__date__gte=month_start,
        created_at__date__lt=today
    ).aggregate(

        revenue=Coalesce(
            Sum("total"),
            Decimal("0.00")
        ),

        bills=Count("id")

    )

    month_revenue_done = month_progress["revenue"]
    month_bills_done = month_progress["bills"]

    # =====================================================
    # REMAINING TARGET
    # =====================================================

    remaining_revenue = max(
        monthly_revenue_target - month_revenue_done,
        Decimal("0.00")
    )

    remaining_bills = max(
        monthly_bills_target - month_bills_done,
        1
    )

    # =====================================================
    # DAILY TARGET
    # =====================================================

    daily_revenue_target = (
        remaining_revenue /
        Decimal(remaining_days)
    ).quantize(
        Decimal("0.01")
    )

    daily_bills_target = max(
        1,
        round(
            remaining_bills /
            remaining_days
        )
    )

    daily_avg_bill_target = (
        daily_revenue_target /
        Decimal(daily_bills_target)
    ).quantize(
        Decimal("0.01")
    )

    # =====================================================
    # TODAY SALES
    # =====================================================

    today_sales = Sale.objects.filter(
        created_at__date=today
    )

    today_data = today_sales.aggregate(

        revenue=Coalesce(
            Sum("total"),
            Decimal("0.00")
        ),

        bills=Count("id")

    )

    today_revenue = today_data["revenue"]
    today_bills = today_data["bills"]

    # =====================================================
    # YESTERDAY SALES
    # =====================================================

    yesterday_sales = Sale.objects.filter(
        created_at__date=yesterday
    )

    yesterday_data = yesterday_sales.aggregate(

        revenue=Coalesce(
            Sum("total"),
            Decimal("0.00")
        ),

        bills=Count("id")

    )

    yesterday_revenue = yesterday_data["revenue"]
    yesterday_bills = yesterday_data["bills"]

    # =====================================================
    # AVERAGE BILL
    # =====================================================

    if today_bills > 0:
        today_avg_bill = (
            today_revenue /
            Decimal(today_bills)
        )
    else:
        today_avg_bill = Decimal("0.00")

    if yesterday_bills > 0:
        yesterday_avg_bill = (
            yesterday_revenue /
            Decimal(yesterday_bills)
        )
    else:
        yesterday_avg_bill = Decimal("0.00")

    # =====================================================
    # PROFIT
    # =====================================================

    today_profit = SaleItem.objects.filter(
        sale__created_at__date=today
    ).aggregate(

        total=Coalesce(

            Sum(

                ExpressionWrapper(

                    (
                        F("price") -
                        F("product__buy_price")
                    ) *
                    F("quantity"),

                    output_field=DecimalField(
                        max_digits=15,
                        decimal_places=2
                    )

                )

            ),

            Decimal("0.00")

        )

    )["total"]

    # =====================================================
    # ITEMS SOLD
    # =====================================================

    items_sold = SaleItem.objects.filter(
        sale__created_at__date=today
    ).aggregate(

        total=Coalesce(
            Sum("quantity"),
            0
        )

    )["total"]

    # =====================================================
    # COMPLETED BILLS
    # =====================================================

    completed_bills = today_sales.filter(
        status="Paid"
    ).count()

    # =====================================================
    # HIGHEST BILL
    # =====================================================

    highest_bill = today_sales.aggregate(

        total=Coalesce(
            Max("total"),
            Decimal("0.00")
        )

    )["total"]

    # =====================================================
    # LAST BILL
    # =====================================================

    last_bill = today_sales.order_by(
        "-created_at"
    ).first()
     # =====================================================
    # PROGRESS FUNCTION
    # =====================================================

    def progress(current, target):

        current = Decimal(current)
        target = Decimal(target)

        if target <= 0:
            return 0

        value = (current / target) * Decimal("100")

        if value > 100:
            value = Decimal("100")

        return round(float(value), 1)

    revenue_pct = progress(
        today_revenue,
        daily_revenue_target
    )

    bills_pct = progress(
        today_bills,
        daily_bills_target
    )

    avg_bill_pct = progress(
        today_avg_bill,
        daily_avg_bill_target
    )

    # =====================================================
    # GROWTH FUNCTION
    # =====================================================

    def growth(current, previous):

        current = float(current)
        previous = float(previous)

        if previous == 0:
            return 100 if current > 0 else 0

        return round(
            ((current - previous) / previous) * 100,
            1
        )

    revenue_delta = growth(
        today_revenue,
        yesterday_revenue
    )

    bills_delta = growth(
        today_bills,
        yesterday_bills
    )

    avg_bill_delta = growth(
        today_avg_bill,
        yesterday_avg_bill
    )

    # =====================================================
    # MONTH PROGRESS %
    # =====================================================

    month_revenue_pct = progress(
        month_revenue_done,
        monthly_revenue_target
    )

    month_bills_pct = progress(
        month_bills_done,
        monthly_bills_target
    )

    # =====================================================
    # DAILY STATUS
    # =====================================================

    if revenue_pct >= 100:
        revenue_status = "Target Achieved"

    elif revenue_pct >= 75:
        revenue_status = "Excellent"

    elif revenue_pct >= 50:
        revenue_status = "Good"

    elif revenue_pct >= 25:
        revenue_status = "Average"

    else:
        revenue_status = "Low"

    if bills_pct >= 100:
        bill_status = "Target Achieved"

    elif bills_pct >= 75:
        bill_status = "Excellent"

    elif bills_pct >= 50:
        bill_status = "Good"

    elif bills_pct >= 25:
        bill_status = "Average"

    else:
        bill_status = "Low"

    # =====================================================
    # LAST BILL DETAILS
    # =====================================================

    if last_bill:

        last_bill_no = last_bill.bill_no

        last_bill_amount = float(last_bill.total)

        last_bill_time = timezone.localtime(
            last_bill.created_at
        ).strftime("%I:%M %p")

    else:

        last_bill_no = "--"

        last_bill_amount = 0

        last_bill_time = "--"

    # =====================================================
    # OVERALL PERFORMANCE SCORE
    # =====================================================

    performance_score = round(

        (
            revenue_pct +
            bills_pct +
            avg_bill_pct
        ) / 3,

        1

    )

    # =====================================================
    # PERFORMANCE LABEL
    # =====================================================

    if performance_score >= 90:

        performance_label = "Excellent"

    elif performance_score >= 70:

        performance_label = "Very Good"

    elif performance_score >= 50:

        performance_label = "Good"

    elif performance_score >= 30:

        performance_label = "Average"

    else:

        performance_label = "Poor"

    # =====================================================
    # LIVE TIME
    # =====================================================

    last_updated = timezone.now().strftime(
        "%d-%m-%Y %I:%M %p"
    )
        # =====================================================
    # RESPONSE
    # =====================================================

    return Response({

        # -------------------------------------------------
        # DATE
        # -------------------------------------------------

        "today_day": today.strftime("%A"),
        "today_date": today.strftime("%d-%m-%Y"),
        "last_updated": last_updated,

        # -------------------------------------------------
        # TODAY
        # -------------------------------------------------

        "today_revenue": float(today_revenue),
        "today_bills": today_bills,
        "today_avg_bill": float(today_avg_bill),

        # -------------------------------------------------
        # TARGETS
        # -------------------------------------------------

        "daily_revenue_target": float(daily_revenue_target),
        "daily_bills_target": daily_bills_target,
        "daily_avg_bill_target": float(daily_avg_bill_target),

        "monthly_revenue_target": float(monthly_revenue_target),
        "monthly_bills_target": monthly_bills_target,

        # -------------------------------------------------
        # MONTH PROGRESS
        # -------------------------------------------------

        "month_revenue_done": float(month_revenue_done),
        "month_bills_done": month_bills_done,

        "remaining_revenue": float(remaining_revenue),
        "remaining_bills": remaining_bills,

        "days_in_month": days_in_month,
        "remaining_days": remaining_days,

        # -------------------------------------------------
        # PROGRESS
        # -------------------------------------------------

        "revenue_pct": revenue_pct,
        "bills_pct": bills_pct,
        "avg_bill_pct": avg_bill_pct,

        "month_revenue_pct": month_revenue_pct,
        "month_bills_pct": month_bills_pct,

        # -------------------------------------------------
        # STATUS
        # -------------------------------------------------

        "revenue_status": revenue_status,
        "bill_status": bill_status,

        # -------------------------------------------------
        # GROWTH
        # -------------------------------------------------

        "revenue_delta": revenue_delta,
        "bills_delta": bills_delta,
        "avg_bill_delta": avg_bill_delta,

        # -------------------------------------------------
        # EXTRA DASHBOARD DATA
        # -------------------------------------------------

        "profit": float(today_profit),

        "completed": completed_bills,

        "items_sold": items_sold,

        "highest_bill": float(highest_bill),

        "last_bill": last_bill_no,

        "last_bill_amount": last_bill_amount,

        "last_bill_time": last_bill_time,

        # -------------------------------------------------
        # PERFORMANCE
        # -------------------------------------------------

        "performance_score": performance_score,

        "performance_label": performance_label,

        # -------------------------------------------------
        # OPTIONAL
        # -------------------------------------------------

        "customers": 0,

    })


def _billing_product_dict(product):
    return {
        "id": str(product.id),
        "name": product.name,
        "category": product.category,
        "sellPrice": float(product.sell_price),
        "stock": product.stock,
        "unit": product.unit,
    }


@api_view(["GET"])
def billing_products(request):
    """
    GET /api/billing/products/

    Full, unpaginated list of every product for the billing counter's
    product grid. No demo/dummy data — reads straight from the database.
    """
    products_qs = Product.objects.all().order_by("name")
    return Response({
        "products": [_billing_product_dict(p) for p in products_qs]
    })


def _generate_bill_no():
    count = Sale.objects.count() + 1
    return f"INV-{count:06d}"


@api_view(["POST"])
def create_sale(request):
    payload = request.data
    items = payload.get("items") or []

    if not items:
        return Response({"error": "Cart is empty."}, status=status.HTTP_400_BAD_REQUEST)

    discount_pct = float(payload.get("discountPct") or 0)
    payment_method_in = str(payload.get("payment", "cash")).capitalize()
    amount_paid_in = payload.get("amountPaid")
    cashier_name = payload.get("cashierName", "")

    try:
        with transaction.atomic():
            subtotal = 0.0
            resolved_items = []

            for entry in items:
                try:
                    product = Product.objects.select_for_update().get(pk=entry["id"])
                    qty = int(entry["qty"])
                except (Product.DoesNotExist, KeyError, ValueError, TypeError):
                    return Response(
                        {"error": "One of the items in the cart is invalid or no longer exists."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                if qty <= 0:
                    return Response(
                        {"error": f"Invalid quantity for {product.name}."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if qty > product.stock:
                    return Response(
                        {
                            "error": f"Not enough stock for {product.name}. "
                                     f"Only {product.stock} left."
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                price = float(product.sell_price)
                subtotal += price * qty
                resolved_items.append((product, qty, price))

            discount_amt = subtotal * min(100, max(0, discount_pct)) / 100
            taxable = subtotal - discount_amt
            tax = taxable * 0.05
            total = taxable + tax
            sale = Sale.objects.create(
                bill_no=_generate_bill_no(),
                total=total,
                discount=discount_amt,
                gst=tax,
                payment_method="Cash",
                status="Paid",
            )

            for product, qty, price in resolved_items:
                # SaleItem.save() deducts product.stock automatically.
                SaleItem.objects.create(
                    sale=sale,
                    product=product,
                    quantity=qty,
                    price=price,
                )

            if payment_method_in == "Cash":
                amount_paid = (
                    float(amount_paid_in) if amount_paid_in not in (None, "") else total
                )
            else:
                amount_paid = total
            balance = max(0.0, amount_paid - total)

    except Exception:
        return Response(
            {"error": "Something went wrong while recording the sale."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    receipt = {
        "id": sale.bill_no,
        "date": timezone.localtime(sale.created_at).strftime("%d-%m-%Y, %I:%M %p"),
        "items": [
            {"id": str(product.id), "name": product.name, "qty": qty, "price": price}
            for product, qty, price in resolved_items
        ],
        "subtotal": round(subtotal, 2),
        "discountAmt": round(discount_amt, 2),
        "tax": round(tax, 2),
        "total": round(total, 2),
        "payment": payment_method_in.lower(),
        "amountPaid": round(amount_paid, 2),
        "balance": round(balance, 2),
        "cashierName": cashier_name,
    }

    return Response({"receipt": receipt}, status=status.HTTP_201_CREATED)


from datetime import timedelta

from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Product


@api_view(["GET"])
def expiry_alerts(request):

    today = timezone.localdate()

    products = []

    for product in Product.objects.exclude(
        expiry_date=None
    ).order_by("expiry_date"):

        days_left = (product.expiry_date - today).days

        if days_left < 0:
            status = "Expired"
        elif days_left <= 10:
            status = "Expiring Soon"
        else:
            status = "Fresh"

        # Only surface items that actually need attention on this widget.
        if status != "Fresh":
            products.append({
                "id": product.id,
                "name": product.name,
                "category": product.category,
                "expiry_date": product.expiry_date.strftime("%Y-%m-%d"),
                "days_left": days_left,
                "status": status,
            })

    expired = sum(1 for p in products if p["status"] == "Expired")
    expiring_soon = sum(1 for p in products if p["status"] == "Expiring Soon")

    return Response({
        "expired": expired,
        "expiring_soon": expiring_soon,
        "products": products,
    })


@api_view(["GET"])
def sales_page_data(request):
    today = timezone.localdate()
    
    # 1. Revenue Data (Last 7 Days)
    revenue_data = []
    for i in range(6, -1, -1):
        target_date = today - timedelta(days=i)
        daily_sales = Sale.objects.filter(created_at__date=target_date, status="Paid")
        revenue = daily_sales.aggregate(total=Coalesce(Sum('total'), Decimal(0)))['total']
        orders = daily_sales.count()
        revenue_data.append({
            "name": target_date.strftime("%a"),
            "revenue": float(revenue),
            "orders": orders
        })

    # 2. Payment Data
    payment_data = []
    for method in Sale.PAYMENT_CHOICES:
        method_name = method[0]
        amount = Sale.objects.filter(payment_method=method_name, status="Paid").aggregate(
            total=Coalesce(Sum('total'), Decimal(0))
        )['total']
        if amount > 0:
            payment_data.append({
                "name": method_name,
                "amount": float(amount),
                "fill": "#215CF6" if method_name == "Cash" else "#10B981"
            })

    # 3. Top Products
    top_items = SaleItem.objects.filter(sale__status="Paid").values(
        'product__id', 'product__name'
    ).annotate(
        sold=Sum('quantity'),
        revenue=Sum(F('quantity') * F('price'), output_field=DecimalField())
    ).order_by('-revenue')[:4]

    top_products = []
    for item in top_items:
        top_products.append({
            "id": item['product__id'],
            "name": item['product__name'],
            "sold": item['sold'],
            "revenue": float(item['revenue'])
        })

    # 4. Sales List
    sales = Sale.objects.all().order_by('-created_at')
    sales_list = []
    for sale in sales:
        items_count = sale.items.aggregate(total=Coalesce(Sum('quantity'), 0))['total']
        sales_list.append({
            "id": sale.bill_no,
            "date": timezone.localtime(sale.created_at).strftime("%Y-%m-%d"),
            "items": items_count,
            "total": float(sale.total),
            "payment": sale.payment_method,
            "status": sale.status,
            "cashier": "Admin"  # Hardcoded for now
        })

    return Response({
        "revenue_data": revenue_data,
        "payment_data": payment_data,
        "top_products": top_products,
        "sales_list": sales_list,
    })


@api_view(["GET"])
def reports_page_data(request):
    today = timezone.localdate()

    # ------------------------------------------------------------------ #
    # 1.  Summary KPI cards
    # ------------------------------------------------------------------ #
    total_sales = Sale.objects.filter(status="Paid").count()

    total_revenue = Sale.objects.filter(status="Paid").aggregate(
        total=Coalesce(Sum("total"), Decimal(0))
    )["total"]

    # Estimated profit: sell_price - buy_price per unit sold
    total_profit = SaleItem.objects.filter(sale__status="Paid").annotate(
        item_profit=ExpressionWrapper(
            (F("price") - F("product__buy_price")) * F("quantity"),
            output_field=DecimalField()
        )
    ).aggregate(total=Coalesce(Sum("item_profit"), Decimal(0)))["total"]

    total_bills = Sale.objects.count()

    # ------------------------------------------------------------------ #
    # 2.  Revenue vs Profit chart (last 7 days)
    # ------------------------------------------------------------------ #
    revenue_data = []
    for i in range(6, -1, -1):
        target_date = today - timedelta(days=i)
        day_items = SaleItem.objects.filter(
            sale__created_at__date=target_date, sale__status="Paid"
        )
        day_revenue = day_items.aggregate(
            total=Coalesce(
                Sum(F("quantity") * F("price"), output_field=DecimalField()),
                Decimal(0)
            )
        )["total"]
        day_profit = day_items.annotate(
            item_profit=ExpressionWrapper(
                (F("price") - F("product__buy_price")) * F("quantity"),
                output_field=DecimalField()
            )
        ).aggregate(total=Coalesce(Sum("item_profit"), Decimal(0)))["total"]

        revenue_data.append({
            "name": target_date.strftime("%a"),
            "revenue": float(day_revenue),
            "profit": float(day_profit),
        })

    # ------------------------------------------------------------------ #
    # 3.  Most Profitable products (top 3 by profit)
    # ------------------------------------------------------------------ #
    top_products = list(
        SaleItem.objects.filter(sale__status="Paid")
        .values("product__id", "product__name")
        .annotate(
            profit=Sum(
                ExpressionWrapper(
                    (F("price") - F("product__buy_price")) * F("quantity"),
                    output_field=DecimalField()
                )
            )
        )
        .order_by("-profit")[:3]
        .values("product__id", "product__name", "profit")
    )
    top_products_out = [
        {
            "id": r["product__id"],
            "name": r["product__name"],
            "profit": float(r["profit"] or 0),
        }
        for r in top_products
    ]

    # ------------------------------------------------------------------ #
    # 4.  Low Stock Alerts
    # ------------------------------------------------------------------ #
    low_stock_qs = Product.objects.filter(
        stock__gt=0, stock__lte=LOW_STOCK_THRESHOLD
    ).order_by("stock")[:5]
    low_stock_out = [
        {"id": p.id, "name": p.name, "stock": p.stock, "threshold": LOW_STOCK_THRESHOLD}
        for p in low_stock_qs
    ]

    # ------------------------------------------------------------------ #
    # 5.  Expiry Alerts (expired or expiring within 10 days)
    # ------------------------------------------------------------------ #
    expiry_qs = Product.objects.exclude(expiry_date=None).filter(
        expiry_date__lte=today + timedelta(days=10)
    ).order_by("expiry_date")[:5]
    expiry_out = []
    for p in expiry_qs:
        days_left = (p.expiry_date - today).days
        expiry_out.append({
            "id": p.id,
            "name": p.name,
            "days": days_left,
        })

    # ------------------------------------------------------------------ #
    # 6.  Reports table  (one row per Sale, categorised as "Sales")
    # ------------------------------------------------------------------ #
    sales_qs = Sale.objects.all().order_by("-created_at")
    reports_list = []
    for sale in sales_qs:
        reports_list.append({
            "id": f"RPT-{sale.bill_no}",
            "date": timezone.localtime(sale.created_at).strftime("%Y-%m-%d"),
            "category": "Sales",
            "generatedBy": "Admin",
            "status": "Ready" if sale.status == "Paid" else "Pending",
        })

    return Response({
        "summary": {
            "total_sales": total_sales,
            "total_revenue": float(total_revenue),
            "total_profit": float(total_profit),
            "total_bills": total_bills,
        },
        "revenue_data": revenue_data,
        "top_products": top_products_out,
        "low_stock": low_stock_out,
        "expiry_alerts": expiry_out,
        "reports_list": reports_list,
    })

from django.contrib.auth import authenticate

@api_view(["POST"])
def login_api(request):
    print("REQUEST DATA:", request.data)
    username = request.data.get("username")
    password = request.data.get("password")
    print(f"USERNAME RECEIVED: '{username}'")
    print(f"PASSWORD RECEIVED: '{password}'")
    
    if not username or not password:
        return Response({"success": False, "message": "Username and password are required"}, status=400)
        
    user = authenticate(username=username, password=password)
    print("AUTH RESULT:", user)
    
    if user is not None:
        if user.is_superuser:
            return Response({"success": True, "message": "Logged in as superuser"})
        else:
            return Response({"success": True, "message": "Logged in successfully"})
    else:
        return Response({"success": False, "message": "Invalid username or password"}, status=401)

from crmapp.models import ShopSettings

@api_view(["GET", "POST"])
def settings_api(request):
    settings, created = ShopSettings.objects.get_or_create(id=1)
    
    if request.method == "POST":
        settings.shop_name = request.data.get("shop_name", settings.shop_name)
        settings.shop_email = request.data.get("shop_email", settings.shop_email)
        settings.shop_address = request.data.get("shop_address", settings.shop_address)
        settings.gstin = request.data.get("gstin", settings.gstin)
        settings.default_tax_rate = request.data.get("default_tax_rate", settings.default_tax_rate)
        settings.pricing_strategy = request.data.get("pricing_strategy", settings.pricing_strategy)
        settings.save()
        return Response({"success": True, "message": "Settings updated"})
        
    return Response({
        "shop_name": settings.shop_name,
        "shop_email": settings.shop_email,
        "shop_address": settings.shop_address,
        "gstin": settings.gstin,
        "default_tax_rate": settings.default_tax_rate,
        "pricing_strategy": settings.pricing_strategy,
    })