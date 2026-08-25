import React, { useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { loadRazorpayScript } from "@/lib/razorpay";
import { toast } from "sonner";
import { Loader2, Sparkles } from "lucide-react";

/** Razorpay Standard Checkout for the credit top-up flow. Order creation and
 * signature verification both happen server-side (services/payments.py) --
 * this component only ever sees a Razorpay-hosted modal and the resulting
 * order_id/payment_id/signature triple to hand back for verification. */
export default function BuyCreditsButton({ productId = "starter_pack", label, className, variant, onSuccess }) {
  const { user, refreshQuota } = useAuth();
  const [busy, setBusy] = useState(false);

  const buy = async () => {
    setBusy(true);
    try {
      const ready = await loadRazorpayScript();
      if (!ready) {
        toast.error("Could not load the payment gateway. Check your connection and try again.");
        setBusy(false);
        return;
      }

      const { data: order } = await api.post("/payments/create-order", { product_id: productId });

      const rzp = new window.Razorpay({
        key: order.key_id,
        amount: order.amount,
        currency: order.currency,
        name: "ReHairAnalytics",
        description: order.name,
        order_id: order.order_id,
        prefill: { name: user?.name, email: user?.email },
        theme: { color: "#111111" },
        handler: async (response) => {
          try {
            await api.post("/payments/verify", {
              razorpay_order_id: response.razorpay_order_id,
              razorpay_payment_id: response.razorpay_payment_id,
              razorpay_signature: response.razorpay_signature,
            });
            await refreshQuota();
            toast.success("Credits added — you're good to go.");
            onSuccess?.();
          } catch (e) {
            toast.error("Payment went through but we couldn't confirm it. Contact us with your payment ID and we'll sort it out.");
          } finally {
            setBusy(false);
          }
        },
        modal: { ondismiss: () => setBusy(false) },
      });
      rzp.on("payment.failed", () => {
        toast.error("Payment failed — you were not charged.");
        setBusy(false);
      });
      rzp.open();
    } catch (e) {
      toast.error("Could not start checkout. Try again.");
      setBusy(false);
    }
  };

  return (
    <Button onClick={buy} disabled={busy} className={className} variant={variant} data-testid="buy-credits-btn">
      {busy ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Sparkles className="w-4 h-4 mr-2" />}
      {label || "Buy 20 credits — ₹100"}
    </Button>
  );
}
