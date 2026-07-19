# Stripe Payment Patterns
Core flow: create a Checkout Session or PaymentIntent on your backend, redirect/render the client to complete payment, listen for webhook events to confirm and fulfill.
Never trust the client to confirm payment success — only a verified webhook event (e.g. checkout.session.completed) should trigger fulfillment (granting access, sending confirmation).
Webhook setup: verify the signature using the webhook secret before processing any event, to prevent spoofed requests.
Test mode uses sk_test_/pk_test_ keys; always test the full webhook flow locally with the Stripe CLI before going live.
