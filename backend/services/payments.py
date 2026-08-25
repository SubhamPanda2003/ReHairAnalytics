"""Razorpay Standard Checkout: order creation, payment-signature verification,
and credit-granting on confirmed payment.

Price and credit count are fixed server-side by PRODUCTS, never trusted from
the client -- the client only ever picks a product_id. verify_and_grant
re-reads the stored order (not anything the client claims) to know what to
grant, and is idempotent against a repeated verify call for the same order
(the frontend's success handler can legitimately fire more than once)."""
import uuid
from datetime import datetime, timezone

import razorpay
from fastapi import HTTPException

from models.database import db
from services import quota as quota_service
from utils import config

_client = razorpay.Client(auth=(config.RAZORPAY_KEY_ID, config.RAZORPAY_KEY_SECRET))

# Amount in paise (Razorpay's smallest INR unit) -- 10000 paise = Rs 100.
PRODUCTS = {
    "starter_pack": {"name": "Starter Pack", "credits": 20, "amount": 10000, "currency": "INR"},
}


async def create_order(user_id: str, product_id: str) -> dict:
    product = PRODUCTS.get(product_id)
    if not product:
        raise HTTPException(status_code=400, detail="Unknown product")

    receipt = f"{product_id}-{uuid.uuid4().hex[:12]}"
    order = _client.order.create({
        "amount": product["amount"],
        "currency": product["currency"],
        "receipt": receipt,
        "notes": {"user_id": user_id, "product_id": product_id},
    })

    await db.payment_orders.insert_one({
        "id": order["id"],
        "user_id": user_id,
        "product_id": product_id,
        "credits": product["credits"],
        "amount": product["amount"],
        "currency": product["currency"],
        "status": "created",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    return {
        "order_id": order["id"],
        "amount": product["amount"],
        "currency": product["currency"],
        "key_id": config.RAZORPAY_KEY_ID,
        "name": product["name"],
    }


async def verify_and_grant(user_id: str, razorpay_order_id: str, razorpay_payment_id: str, razorpay_signature: str) -> dict:
    order = await db.payment_orders.find_one({"id": razorpay_order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order["user_id"] != user_id:
        # IDOR guard -- an order id from someone else's checkout session
        # should never be verifiable/creditable by this user.
        raise HTTPException(status_code=403, detail="Order does not belong to this user")

    if order["status"] == "paid":
        user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
        return await quota_service.quota_for(user)

    try:
        _client.utility.verify_payment_signature({
            "razorpay_order_id": razorpay_order_id,
            "razorpay_payment_id": razorpay_payment_id,
            "razorpay_signature": razorpay_signature,
        })
    except razorpay.errors.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Payment verification failed")

    await db.payment_orders.update_one(
        {"id": razorpay_order_id},
        {"$set": {
            "status": "paid",
            "payment_id": razorpay_payment_id,
            "paid_at": datetime.now(timezone.utc).isoformat(),
        }},
    )

    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    current_limit = await quota_service.effective_limit(user)
    # A top-up is additive on top of whatever they currently have (global
    # default or their own override) -- deliberately does NOT touch
    # credits_reset_at the way admin_set_scan_limit does, since buying more
    # credits shouldn't erase usage already counted against the old limit,
    # only raise the ceiling. A user who's already unlimited (current_limit
    # is None) is left alone -- adding a finite number on top of "no limit"
    # would shrink their access, not grow it.
    if current_limit is not None:
        new_limit = current_limit + order["credits"]
        await db.users.update_one({"user_id": user_id}, {"$set": {"scan_limit": new_limit}})
        user["scan_limit"] = new_limit

    return await quota_service.quota_for(user)
