"""Razorpay Standard Checkout: create an order, verify the signed callback."""
from fastapi import APIRouter

from models.schemas import CreateOrderIn, VerifyPaymentIn
from services import payments as payments_service
from utils.deps import CurrentUser

router = APIRouter(prefix="/payments", tags=["payments"])


@router.get("/products")
async def list_products(user: CurrentUser):
    return payments_service.PRODUCTS


@router.post("/create-order")
async def create_order(body: CreateOrderIn, user: CurrentUser):
    return await payments_service.create_order(user["user_id"], body.product_id)


@router.post("/verify")
async def verify_payment(body: VerifyPaymentIn, user: CurrentUser):
    return await payments_service.verify_and_grant(
        user["user_id"], body.razorpay_order_id, body.razorpay_payment_id, body.razorpay_signature
    )
