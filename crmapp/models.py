from django.db import models
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.utils import timezone

# Single source of truth for the "low stock" cutoff.
# Use this constant everywhere instead of hardcoding 10 / <=10 / <10 in views.
LOW_STOCK_THRESHOLD = 10


class Product(models.Model):
    STATUS_CHOICES = [
        ("In Stock", "In Stock"),
        ("Low Stock", "Low Stock"),
        ("Out of Stock", "Out of Stock"),
    ]

    CATEGORY_CHOICES = [
        ("Fruits", "Fruits"),
        ("Vegetables", "Vegetables"),
        ("Rice", "Rice"),
        ("Flour", "Flour"),
        ("Pulses", "Pulses"),
        ("Spices", "Spices"),
        ("Oil & Ghee", "Oil & Ghee"),
        ("Sugar & Salt", "Sugar & Salt"),
        ("Tea & Coffee", "Tea & Coffee"),
        ("Milk", "Milk"),
        ("Curd", "Curd"),
        ("Butter & Cheese", "Butter & Cheese"),
        ("Eggs", "Eggs"),
        ("Meat", "Meat"),
        ("Chicken", "Chicken"),
        ("Fish", "Fish"),
        ("Frozen Foods", "Frozen Foods"),
        ("Bakery", "Bakery"),
        ("Biscuits", "Biscuits"),
        ("Snacks", "Snacks"),
        ("Chocolates", "Chocolates"),
        ("Ice Cream", "Ice Cream"),
        ("Soft Drinks", "Soft Drinks"),
        ("Juices", "Juices"),
        ("Water", "Water"),
        ("Instant Foods", "Instant Foods"),
        ("Noodles & Pasta", "Noodles & Pasta"),
        ("Breakfast", "Breakfast"),
        ("Dry Fruits", "Dry Fruits"),
        ("Pickles", "Pickles"),
        ("Sauces & Ketchup", "Sauces & Ketchup"),
        ("Baby Care", "Baby Care"),
        ("Personal Care", "Personal Care"),
        ("Health Care", "Health Care"),
        ("Cleaning", "Cleaning"),
        ("Detergents", "Detergents"),
        ("Home Care", "Home Care"),
        ("Stationery", "Stationery"),
        ("Pet Food", "Pet Food"),
        ("Others", "Others"),
    ]

    UNIT_CHOICES = [
        ("pcs", "Pieces"),
        ("kg", "Kilogram"),
        ("g", "Gram"),
        ("ltr", "Litre"),
        ("ml", "Milli Litre"),
        ("pack", "Pack"),
        ("box", "Box"),
        ("dozen", "Dozen"),
    ]

    name = models.CharField(max_length=200)
    company = models.CharField(max_length=200)

    category = models.CharField(
        max_length=50,
        choices=CATEGORY_CHOICES,
        default="Others"
    )

    buy_price = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    sell_price = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    stock = models.PositiveIntegerField(default=0)

    unit = models.CharField(
        max_length=20,
        choices=UNIT_CHOICES,
        default="pcs"
    )

    # NOTE: on Postgres/MySQL, multiple rows with barcode="" will violate a
    # unique constraint (only NULL is exempt, not empty string). Always save
    # this as None, never "", when the barcode is blank.
    barcode = models.CharField(
        max_length=100,
        unique=True,
        blank=True,
        null=True
    )

    expiry_date = models.DateField(
        blank=True,
        null=True
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="In Stock"
    )

    created_at = models.DateTimeField(
        default=timezone.now
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def save(self, *args, **kwargs):
        # Normalize blank barcode to None so the unique constraint behaves.
        if self.barcode == "":
            self.barcode = None

        if self.stock == 0:
            self.status = "Out of Stock"
        elif self.stock <= LOW_STOCK_THRESHOLD:
            self.status = "Low Stock"
        else:
            self.status = "In Stock"

        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Sale(models.Model):
    STATUS_CHOICES = [
        ("Paid", "Paid"),
        ("Pending", "Pending"),
    ]

    PAYMENT_CHOICES = [
        ("Cash", "Cash"),
    ]

    bill_no = models.CharField(
        max_length=30,
        unique=True
    )

    total = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    discount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    gst = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_CHOICES,
        default="Cash"
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="Paid"
    )

    created_at = models.DateTimeField(
        default=timezone.now
    )

    def __str__(self):
        return self.bill_no


class SaleItem(models.Model):
    sale = models.ForeignKey(
        Sale,
        related_name="items",
        on_delete=models.CASCADE
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE
    )

    quantity = models.PositiveIntegerField(
        default=1
    )

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    @property
    def subtotal(self):
        return self.quantity * self.price

    def save(self, *args, **kwargs):
        if self.pk is None:
            # New sale item -> deduct stock.
            self.product.stock -= self.quantity
            if self.product.stock < 0:
                self.product.stock = 0
            self.product.save()
        else:
            # Existing sale item being edited -> adjust stock by the
            # difference between the new and old quantity, instead of
            # silently ignoring the change.
            old_qty = SaleItem.objects.only("quantity").get(pk=self.pk).quantity
            diff = self.quantity - old_qty  # positive = selling more, negative = selling less

            if diff != 0:
                self.product.stock -= diff
                if self.product.stock < 0:
                    self.product.stock = 0
                self.product.save()

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.sale.bill_no} - {self.product.name}"


class ShopSettings(models.Model):
    shop_name = models.CharField(max_length=255, default="My Supermarket")
    shop_email = models.EmailField(default="admin@mysupermarket.com")
    shop_address = models.TextField(default="123 Main St, City")
    gstin = models.CharField(max_length=50, default="29ABCDE1234F1Z5")
    default_tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=18.00)
    pricing_strategy = models.CharField(max_length=50, default="Tax Inclusive")
    
    def save(self, *args, **kwargs):
        # Ensure only one record exists
        if self.__class__.objects.count():
            self.pk = self.__class__.objects.first().pk
        super().save(*args, **kwargs)
        
    def __str__(self):
        return self.shop_name


@receiver(pre_delete, sender=SaleItem)
def restore_stock_on_delete(sender, instance, **kwargs):
    """
    Restore product stock when a SaleItem is deleted directly, or via
    cascade when its parent Sale is deleted/voided.
    """
    Product.objects.filter(pk=instance.product_id).update(
        stock=models.F("stock") + instance.quantity
    )


class ShopTarget(models.Model):
    product_target = models.PositiveIntegerField(default=500)

    stock_target = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=500000
    )

    daily_sales_target = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=20000
    )

    monthly_revenue_target = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=800000
    )

    monthly_bill_target = models.PositiveIntegerField(
        default=750
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Shop Target"
        verbose_name_plural = "Shop Target"

    def save(self, *args, **kwargs):
        # Keep only one row
        self.pk = 1
        super().save(*args, **kwargs)

    def __str__(self):
        return "Shop Dashboard Targets"