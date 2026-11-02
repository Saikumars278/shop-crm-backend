from django.db import models, transaction
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.utils import timezone

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
        ("Failed", "Failed"),
    ]

    PAYMENT_CHOICES = [
        ("Cash", "Cash"),
        ("Card", "Card"),
        ("UPI", "UPI"),
        ("UPI QR", "UPI QR"),
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

    razorpay_qr_id = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    razorpay_payment_id = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    razorpay_order_id = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    qr_image_url = models.TextField(
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(
        default=timezone.now
    )

    def mark_as_paid(self, payment_id=None):
        """
        Confirms payment idempotently: updates status to Paid, attaches payment_id,
        and deducts product stock for all items in this bill exactly once.
        Protected against race conditions and duplicate deductions via select_for_update.
        """
        with transaction.atomic():
            locked_sale = Sale.objects.select_for_update().get(pk=self.pk)
            if locked_sale.status == "Paid":
                # Already marked Paid and stock already deducted; prevent double-deduction
                self.status = "Paid"
                if payment_id and not locked_sale.razorpay_payment_id:
                    locked_sale.razorpay_payment_id = payment_id
                    locked_sale.save(update_fields=["razorpay_payment_id"])
                    self.razorpay_payment_id = payment_id
                return

            locked_sale.status = "Paid"
            if payment_id:
                locked_sale.razorpay_payment_id = payment_id
            locked_sale.save(update_fields=["status", "razorpay_payment_id"])

            # Deduct product stock atomically
            for item in locked_sale.items.select_related("product").all():
                prod = Product.objects.select_for_update().get(pk=item.product.pk)
                prod.stock = max(0, prod.stock - item.quantity)
                prod.save(update_fields=["stock"])

            self.status = "Paid"
            if payment_id:
                self.razorpay_payment_id = payment_id

    def mark_as_failed(self):
        """
        Marks payment as Failed. Stock is never deducted.
        """
        with transaction.atomic():
            locked_sale = Sale.objects.select_for_update().get(pk=self.pk)
            if locked_sale.status != "Paid":
                locked_sale.status = "Failed"
                locked_sale.save(update_fields=["status"])
                self.status = "Failed"

    def __str__(self):
        return f"{self.bill_no} ({self.status})"


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
            # If the sale is already Paid (Cash or Card), deduct stock immediately.
            # If the sale is Pending (UPI QR awaiting customer scan), do NOT deduct stock yet.
            if self.sale and self.sale.status == "Paid":
                self.product.stock -= self.quantity
                if self.product.stock < 0:
                    self.product.stock = 0
                self.product.save()
        else:
            old_qty = SaleItem.objects.only("quantity").get(pk=self.pk).quantity
            diff = self.quantity - old_qty

            if diff != 0 and self.sale and self.sale.status == "Paid":
                self.product.stock -= diff
                if self.product.stock < 0:
                    self.product.stock = 0
                self.product.save()

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.sale.bill_no} - {self.product.name}"


class ShopSettings(models.Model):
    shop_name = models.CharField(max_length=255, default="Sai General Store")
    shop_email = models.EmailField(default="admin@saigeneralstore.com")
    shop_address = models.TextField(default="12, Main Road, Nagercoil - 629001")
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
    cascade when its parent Sale is deleted/voided — ONLY if it was paid
    and had stock deducted.
    """
    if instance.sale and instance.sale.status == "Paid":
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


class PasswordResetOTP(models.Model):
    email = models.EmailField()
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(default=timezone.now)
    is_verified = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def is_expired(self):
        # 10 minute expiration window
        return (timezone.now() - self.created_at).total_seconds() > 600

    def __str__(self):
        return f"{self.email} - {self.otp}"
