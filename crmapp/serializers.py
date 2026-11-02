from rest_framework import serializers
from .models import Product, Sale, SaleItem


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = "__all__"


class SaleItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(
        source="product.name",
        read_only=True
    )

    subtotal = serializers.SerializerMethodField()

    class Meta:
        model = SaleItem
        fields = [
            "id",
            "sale",
            "product",
            "product_name",
            "quantity",
            "price",
            "subtotal",
        ]

    def get_subtotal(self, obj):
        return obj.quantity * obj.price


class SaleSerializer(serializers.ModelSerializer):
    items = SaleItemSerializer(
        many=True,
        read_only=True
    )

    class Meta:
        model = Sale
        fields = [
            "id",
            "bill_no",
            "total",
            "discount",
            "gst",
            "payment_method",
            "status",
            "razorpay_qr_id",
            "razorpay_payment_id",
            "qr_image_url",
            "created_at",
            "items",
        ]
